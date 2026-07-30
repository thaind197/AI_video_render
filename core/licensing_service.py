"""
Veo Studio AI PRO - Licensing & Subscription Backend Service

Supports PostgreSQL (via psycopg2 / asyncpg / sqlalchemy) with SQLite fallback.
Handles Authentication, License Key Validation, MAC ID Binding, Daily Quota,
Audit Logging, and Prompt History Logging.
"""

import os
import sys
import json
import time
import uuid
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from config.settings import BASE_DIR, STORAGE_DIR
from core.hardware import get_mac_address

logger = logging.getLogger("LicensingService")


# Optional PostgreSQL library support
try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

# Fallback SQLite DB path for local development / offline server
LICENSING_DB_PATH = STORAGE_DIR / "licensing.db"


def hash_password(password: str) -> str:
    """Hash password using SHA-256 with salt"""
    salt = "VeoStudioAIProSalt2026"
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


class LicensingService:
    """Central Licensing, Authentication & Admin Service.
    
    Supports PostgreSQL connection via `POSTGRES_URL` env or local SQLite fallback.
    """

    def __init__(self, postgres_url: str = None):
        from config.settings import resolve_postgres_url
        self.postgres_url = resolve_postgres_url(postgres_url or os.getenv("POSTGRES_URL", os.getenv("DATABASE_URL", "")))
        self.use_postgres = bool(self.postgres_url and HAS_PSYCOPG2)
        if self.use_postgres:
            try:
                test_conn = psycopg2.connect(self.postgres_url, connect_timeout=3)
                test_conn.close()
            except Exception as e:
                logger.warning(f"[LicensingService] PostgreSQL URL không thể kết nối ({e}). Chuyển sang SQLite local.")
                self.use_postgres = False
        self._init_db()

    def _get_connection(self):
        if self.use_postgres:
            try:
                from core.db import PgConnectionWrapper
                raw_conn = psycopg2.connect(self.postgres_url, cursor_factory=psycopg2.extras.RealDictCursor, connect_timeout=3)
                return PgConnectionWrapper(raw_conn)
            except Exception as e:
                logger.warning(f"[LicensingService] Lỗi kết nối PostgreSQL: {e}. Fallback sang SQLite local.")
                self.use_postgres = False
                import sqlite3
                conn = sqlite3.connect(LICENSING_DB_PATH)
                conn.row_factory = sqlite3.Row
                return conn
        else:
            import sqlite3
            conn = sqlite3.connect(LICENSING_DB_PATH)
            conn.row_factory = sqlite3.Row
            return conn

    def _init_db(self):
        """Create tables if they don't exist"""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.use_postgres:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id VARCHAR(36) PRIMARY KEY,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        password_hash VARCHAR(255) NOT NULL,
                        full_name VARCHAR(255),
                        role VARCHAR(50) DEFAULT 'user',
                        status VARCHAR(50) DEFAULT 'active',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS licenses (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
                        license_key VARCHAR(100) UNIQUE NOT NULL,
                        tier VARCHAR(50) DEFAULT 'pro',
                        max_devices INT DEFAULT 2,
                        daily_video_quota INT DEFAULT 500,
                        valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        valid_until TIMESTAMP NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE
                    );
                    CREATE TABLE IF NOT EXISTS activated_devices (
                        id VARCHAR(36) PRIMARY KEY,
                        license_id VARCHAR(36) REFERENCES licenses(id) ON DELETE CASCADE,
                        mac_id VARCHAR(100) NOT NULL,
                        device_name VARCHAR(255),
                        ip_address VARCHAR(50),
                        last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id SERIAL PRIMARY KEY,
                        actor_id VARCHAR(36),
                        action VARCHAR(100) NOT NULL,
                        details TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS prompt_history (
                        id SERIAL PRIMARY KEY,
                        user_id VARCHAR(36),
                        license_id VARCHAR(36),
                        mac_id VARCHAR(100),
                        source_topic TEXT,
                        veo_prompt TEXT NOT NULL,
                        aspect_ratio VARCHAR(20),
                        duration INT,
                        model VARCHAR(50),
                        status VARCHAR(50) DEFAULT 'SUCCESS',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
            else:
                cur.executescript("""
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        email TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        full_name TEXT,
                        role TEXT DEFAULT 'user',
                        status TEXT DEFAULT 'active',
                        created_at TEXT
                    );
                    CREATE TABLE IF NOT EXISTS licenses (
                        id TEXT PRIMARY KEY,
                        user_id TEXT,
                        license_key TEXT UNIQUE NOT NULL,
                        tier TEXT DEFAULT 'pro',
                        max_devices INTEGER DEFAULT 2,
                        daily_video_quota INTEGER DEFAULT 500,
                        valid_from TEXT,
                        valid_until TEXT NOT NULL,
                        is_active INTEGER DEFAULT 1
                    );
                    CREATE TABLE IF NOT EXISTS activated_devices (
                        id TEXT PRIMARY KEY,
                        license_id TEXT,
                        mac_id TEXT NOT NULL,
                        device_name TEXT,
                        ip_address TEXT,
                        last_active_at TEXT,
                        activated_at TEXT
                    );
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        actor_id TEXT,
                        action TEXT NOT NULL,
                        details TEXT,
                        created_at TEXT
                    );
                    CREATE TABLE IF NOT EXISTS prompt_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        license_id TEXT,
                        mac_id TEXT,
                        source_topic TEXT,
                        veo_prompt TEXT NOT NULL,
                        aspect_ratio TEXT,
                        duration INTEGER,
                        model TEXT,
                        status TEXT DEFAULT 'SUCCESS',
                        created_at TEXT
                    );
                """)
            conn.commit()
            # Migration check for allowed_modules column
            try:
                if self.use_postgres:
                    cur.execute("ALTER TABLE licenses ADD COLUMN IF NOT EXISTS allowed_modules TEXT DEFAULT '[\"veo_generate\",\"tiktok_clone\",\"video_library\",\"social_autopost\",\"engine_settings\"]';")
                else:
                    cur.execute("PRAGMA table_info(licenses)")
                    cols = [r[1] for r in cur.fetchall()]
                    if "allowed_modules" not in cols:
                        cur.execute("ALTER TABLE licenses ADD COLUMN allowed_modules TEXT DEFAULT '[\"veo_generate\",\"tiktok_clone\",\"video_library\",\"social_autopost\",\"engine_settings\"]';")
                conn.commit()
            except Exception:
                pass

            logger.info(f"[LicensingService] DB Initialized ({'PostgreSQL' if self.use_postgres else 'SQLite'})")
            self._ensure_seed_admin(cur, conn)
        except Exception as e:
            logger.error(f"[LicensingService] Lỗi tạo DB Schema: {e}")
            conn.rollback()
        finally:
            conn.close()

    def _ensure_seed_admin(self, cur, conn):
        """Create default Admin user & License if no admin exists"""
        try:
            if self.use_postgres:
                cur.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'admin'")
                res = cur.fetchone()
                cnt = res['cnt'] if res else 0
            else:
                cur.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'admin'")
                cnt = cur.fetchone()[0]

            if cnt == 0:
                admin_id = str(uuid.uuid4())
                pwd_hash = hash_password("admin123")
                now_str = datetime.now().isoformat()
                valid_until = (datetime.now() + timedelta(days=365*10)).isoformat()

                if self.use_postgres:
                    cur.execute("""
                        INSERT INTO users (id, email, password_hash, full_name, role, status, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """, (admin_id, "admin@veostudio.ai", pwd_hash, "System Admin", "admin", "active"))
                    
                    lic_id = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO licenses (id, user_id, license_key, tier, max_devices, daily_video_quota, valid_until, is_active)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
                    """, (lic_id, admin_id, "VEO-PRO-ADMIN-8888-9999", "enterprise", 100, 9999, valid_until))
                else:
                    cur.execute("""
                        INSERT INTO users (id, email, password_hash, full_name, role, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (admin_id, "admin@veostudio.ai", pwd_hash, "System Admin", "admin", "active", now_str))
                    
                    lic_id = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO licenses (id, user_id, license_key, tier, max_devices, daily_video_quota, valid_until, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """, (lic_id, admin_id, "VEO-PRO-ADMIN-8888-9999", "enterprise", 100, 9999, valid_until))

                conn.commit()
                logger.info("🔑 Seed Admin Created: email=admin@veostudio.ai, pass=admin123, key=VEO-PRO-ADMIN-8888-9999")
        except Exception as ex:
            logger.warning(f"Lỗi seed admin: {ex}")

    def authenticate_admin(self, email: str, password: str) -> dict:
        """Validate Admin Web Panel Login (Requires only Email and Password)."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            email_clean = email.strip().lower()
            pwd_h = hash_password(password.strip())

            if self.use_postgres:
                cur.execute("SELECT * FROM users WHERE LOWER(email) = %s", (email_clean,))
            else:
                cur.execute("SELECT * FROM users WHERE LOWER(email) = ?", (email_clean,))
            user = cur.fetchone()
            if not user:
                return {"status": "error", "message": "Tài khoản Admin không tồn tại!"}

            user_dict = dict(user)
            if user_dict['password_hash'] != pwd_h:
                return {"status": "error", "message": "Mật khẩu Admin không chính xác!"}

            if user_dict.get('role') != 'admin' and email_clean != 'admin@veostudio.ai':
                return {"status": "error", "message": "Tài khoản không có quyền Admin!"}

            token_payload = f"admin:{user_dict['id']}:{int(time.time())}"
            token = hashlib.sha256(f"ADMIN_SECRET_SALT_2026:{token_payload}".encode("utf-8")).hexdigest()

            return {
                "status": "success",
                "message": "Đăng nhập Admin thành công!",
                "token": token,
                "user": {
                    "id": user_dict['id'],
                    "email": user_dict['email'],
                    "full_name": user_dict['full_name'],
                    "role": user_dict.get('role', 'admin')
                }
            }
        except Exception as e:
            logger.exception(f"Lỗi authenticate_admin: {e}")
            return {"status": "error", "message": f"Lỗi đăng nhập Admin: {e}"}
        finally:
            conn.close()

    def is_mac_registered(self, mac_id: str) -> bool:
        """Check if a hardware MAC ID is registered in activated_devices"""
        if not mac_id:
            return False
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.use_postgres:
                cur.execute("SELECT 1 FROM activated_devices WHERE mac_id = %s LIMIT 1", (mac_id,))
            else:
                cur.execute("SELECT 1 FROM activated_devices WHERE mac_id = ? LIMIT 1", (mac_id,))
            return cur.fetchone() is not None
        except Exception:
            return False
        finally:
            conn.close()

    def authenticate_client(self, email: str, password: str, license_key: str = "", mac_id: str = "", device_name: str = "", ip_address: str = "") -> dict:
        """Validate Client Login & MAC Binding.
        
        Returns dict with status, token, user info & license details.
        """
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            email_clean = email.strip().lower()
            key_clean = (license_key or "").strip().upper()
            pwd_h = hash_password(password.strip())

            # 1. Fetch User
            if self.use_postgres:
                cur.execute("SELECT * FROM users WHERE LOWER(email) = %s", (email_clean,))
            else:
                cur.execute("SELECT * FROM users WHERE LOWER(email) = ?", (email_clean,))
            user = cur.fetchone()
            if not user:
                return {"status": "error", "message": "Tài khoản không tồn tại trên hệ thống."}

            user_dict = dict(user)
            if user_dict['status'] != 'active':
                return {"status": "error", "message": "Tài khoản của bạn đã bị khóa hoặc tạm dừng bởi Admin!"}

            if user_dict['password_hash'] != pwd_h:
                return {"status": "error", "message": "Mật khẩu không chính xác."}

            # 2. Fetch License
            lic = None
            if key_clean:
                if self.use_postgres:
                    cur.execute("SELECT * FROM licenses WHERE LOWER(license_key) = %s AND user_id = %s", (key_clean.lower(), user_dict['id']))
                else:
                    cur.execute("SELECT * FROM licenses WHERE LOWER(license_key) = ? AND user_id = ?", (key_clean.lower(), user_dict['id']))
                lic = cur.fetchone()
                if not lic:
                    return {"status": "error", "message": "Mã License Key không đúng hoặc không thuộc tài khoản này."}
            else:
                # License key not supplied: Auto-lookup via mac_id binding or user's active license
                if mac_id:
                    if self.use_postgres:
                        cur.execute("""
                            SELECT l.* FROM licenses l
                            JOIN activated_devices d ON l.id = d.license_id
                            WHERE d.mac_id = %s AND l.user_id = %s AND l.is_active = TRUE
                            ORDER BY l.valid_until DESC LIMIT 1
                        """, (mac_id, user_dict['id']))
                    else:
                        cur.execute("""
                            SELECT l.* FROM licenses l
                            JOIN activated_devices d ON l.id = d.license_id
                            WHERE d.mac_id = ? AND l.user_id = ? AND l.is_active = 1
                            ORDER BY l.valid_until DESC LIMIT 1
                        """, (mac_id, user_dict['id']))
                    lic = cur.fetchone()

                if not lic:
                    # Search for any active unexpired license of this user
                    if self.use_postgres:
                        cur.execute("SELECT * FROM licenses WHERE user_id = %s AND is_active = TRUE ORDER BY valid_until DESC LIMIT 1", (user_dict['id'],))
                    else:
                        cur.execute("SELECT * FROM licenses WHERE user_id = ? AND is_active = 1 ORDER BY valid_until DESC LIMIT 1", (user_dict['id'],))
                    lic = cur.fetchone()

                if not lic:
                    return {"status": "error", "message": "Tài khoản chưa có License Key. Vui lòng nhập Mã License Key để kích hoạt lần đầu!"}

            lic_dict = dict(lic)
            if not lic_dict.get('is_active', True):
                return {"status": "error", "message": "Mã License Key này đang bị vô hiệu hóa!"}

            # Check expiration date
            valid_until_dt = lic_dict['valid_until']
            if isinstance(valid_until_dt, str):
                try:
                    valid_until_dt = datetime.fromisoformat(valid_until_dt)
                except Exception:
                    valid_until_dt = datetime.now() + timedelta(days=1)

            if datetime.now() > valid_until_dt:
                return {"status": "error", "message": f"License Key đã hết hạn vào ngày {valid_until_dt.strftime('%d/%m/%Y')}!"}

            # 3. Check MAC ID Binding & Device Count Limit
            if self.use_postgres:
                cur.execute("SELECT * FROM activated_devices WHERE license_id = %s", (lic_dict['id'],))
            else:
                cur.execute("SELECT * FROM activated_devices WHERE license_id = ?", (lic_dict['id'],))
            devices = [dict(r) for r in cur.fetchall()]

            existing_device = next((d for d in devices if d['mac_id'] == mac_id), None)
            now_iso = datetime.now().isoformat()

            if not existing_device:
                max_devs = lic_dict.get('max_devices', 1)
                if len(devices) >= max_devs:
                    return {
                        "status": "error",
                        "message": f"Mã License đã đạt giới hạn tối đa {max_devs} thiết bị ({len(devices)}/{max_devs}). Vui lòng liên hệ Admin để reset MAC ID cũ!"
                    }
                # Register new device
                new_dev_id = str(uuid.uuid4())
                if self.use_postgres:
                    cur.execute("""
                        INSERT INTO activated_devices (id, license_id, mac_id, device_name, ip_address, last_active_at, activated_at)
                        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """, (new_dev_id, lic_dict['id'], mac_id, device_name or "Desktop-PC", ip_address or "127.0.0.1"))
                else:
                    cur.execute("""
                        INSERT INTO activated_devices (id, license_id, mac_id, device_name, ip_address, last_active_at, activated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (new_dev_id, lic_dict['id'], mac_id, device_name or "Desktop-PC", ip_address or "127.0.0.1", now_iso, now_iso))
            else:
                # Update last active
                if self.use_postgres:
                    cur.execute("UPDATE activated_devices SET last_active_at = CURRENT_TIMESTAMP, ip_address = %s WHERE id = %s", (ip_address, existing_device['id']))
                else:
                    cur.execute("UPDATE activated_devices SET last_active_at = ?, ip_address = ? WHERE id = ?", (now_iso, ip_address, existing_device['id']))

            # Log audit
            self._log_audit(cur, user_dict['id'], "CLIENT_LOGIN_SUCCESS", json.dumps({"mac_id": mac_id, "device": device_name}))
            conn.commit()

            # Create Auth Token
            token_payload = f"{user_dict['id']}:{lic_dict['id']}:{mac_id}:{int(time.time())}"
            token = hashlib.sha256(f"VEO_SECRET_SALT_2026:{token_payload}".encode("utf-8")).hexdigest()

            # Parse allowed_modules JSON
            raw_mods = lic_dict.get('allowed_modules')
            try:
                allowed_mods = json.loads(raw_mods) if raw_mods else ["veo_generate", "tiktok_clone", "video_library", "social_autopost", "engine_settings"]
            except Exception:
                allowed_mods = ["veo_generate", "tiktok_clone", "video_library", "social_autopost", "engine_settings"]

            return {
                "status": "success",
                "message": "Xác thực đăng nhập thành công!",
                "token": token,
                "user": {
                    "id": user_dict['id'],
                    "email": user_dict['email'],
                    "full_name": user_dict['full_name'],
                    "role": user_dict['role']
                },
                "license": {
                    "id": lic_dict['id'],
                    "license_key": lic_dict['license_key'],
                    "tier": lic_dict['tier'],
                    "max_devices": lic_dict['max_devices'],
                    "valid_until": str(lic_dict['valid_until']),
                    "allowed_modules": allowed_mods
                },
                "mac_id": mac_id
            }
        except Exception as e:
            logger.exception(f"Lỗi authenticate_client: {e}")
            conn.rollback()
            return {"status": "error", "message": f"Lỗi hệ thống xác thực: {str(e)}"}
        finally:
            conn.close()

    def verify_token_and_mac(self, user_id: str, license_id: str, mac_id: str) -> dict:
        """Heartbeat verification to check if account/license/MAC ID is active and valid"""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.use_postgres:
                cur.execute("SELECT status FROM users WHERE id = %s", (user_id,))
            else:
                cur.execute("SELECT status FROM users WHERE id = ?", (user_id,))
            u = cur.fetchone()
            if not u or dict(u)['status'] != 'active':
                return {"valid": False, "reason": "Tài khoản của bạn đã bị khóa từ xa bởi Admin!"}

            if self.use_postgres:
                cur.execute("SELECT * FROM licenses WHERE id = %s AND is_active = TRUE", (license_id,))
            else:
                cur.execute("SELECT * FROM licenses WHERE id = ? AND is_active = 1", (license_id,))
            lic = cur.fetchone()
            if not lic:
                return {"valid": False, "reason": "License Key đã bị vô hiệu hóa!"}

            lic_dict = dict(lic)
            v_until = lic_dict['valid_until']
            if isinstance(v_until, str):
                try:
                    v_until = datetime.fromisoformat(v_until)
                except Exception:
                    v_until = datetime.now() + timedelta(days=1)

            if datetime.now() > v_until:
                return {"valid": False, "reason": "License Key của bạn đã hết hạn!"}

            # Check if device MAC is bound
            if self.use_postgres:
                cur.execute("SELECT id FROM activated_devices WHERE license_id = %s AND mac_id = %s", (license_id, mac_id))
            else:
                cur.execute("SELECT id FROM activated_devices WHERE license_id = ? AND mac_id = ?", (license_id, mac_id))
            dev = cur.fetchone()
            if not dev:
                return {"valid": False, "reason": "Thiết bị (MAC ID) này đã bị gỡ liên kết bởi Admin!"}

            # Update heartbeat time
            now_iso = datetime.now().isoformat()
            if self.use_postgres:
                cur.execute("UPDATE activated_devices SET last_active_at = CURRENT_TIMESTAMP WHERE id = %s", (dict(dev)['id'],))
            else:
                cur.execute("UPDATE activated_devices SET last_active_at = ? WHERE id = ?", (now_iso, dict(dev)['id']))
            conn.commit()

            return {"valid": True, "tier": lic_dict['tier'], "valid_until": str(lic_dict['valid_until'])}
        except Exception as e:
            return {"valid": False, "reason": f"Lỗi kiểm tra session: {e}"}
        finally:
            conn.close()

    # -------------------------------------------------------------
    # Prompt History & Audit Logs
    # -------------------------------------------------------------

    def log_prompt_history(self, user_id: str, license_id: str, mac_id: str, veo_prompt: str, source_topic: str = "", aspect_ratio: str = "9:16", duration: int = 8, model: str = "veo-2", status: str = "SUCCESS"):
        """Save executed prompt details to PostgreSQL/SQLite DB for audit and user history"""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            now_iso = datetime.now().isoformat()
            if self.use_postgres:
                cur.execute("""
                    INSERT INTO prompt_history (user_id, license_id, mac_id, source_topic, veo_prompt, aspect_ratio, duration, model, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """, (user_id, license_id, mac_id, source_topic, veo_prompt, aspect_ratio, duration, model, status))
            else:
                cur.execute("""
                    INSERT INTO prompt_history (user_id, license_id, mac_id, source_topic, veo_prompt, aspect_ratio, duration, model, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, license_id, mac_id, source_topic, veo_prompt, aspect_ratio, duration, model, status, now_iso))
            conn.commit()
        except Exception as ex:
            logger.warning(f"Lỗi log prompt history: {ex}")
        finally:
            conn.close()

    def get_prompt_history(self, user_id: str = None, limit: int = 50) -> list:
        """Fetch prompt history list"""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if user_id:
                if self.use_postgres:
                    cur.execute("SELECT * FROM prompt_history WHERE user_id = %s ORDER BY id DESC LIMIT %s", (user_id, limit))
                else:
                    cur.execute("SELECT * FROM prompt_history WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
            else:
                if self.use_postgres:
                    cur.execute("SELECT * FROM prompt_history ORDER BY id DESC LIMIT %s", (limit,))
                else:
                    cur.execute("SELECT * FROM prompt_history ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()

    def _log_audit(self, cur, actor_id: str, action: str, details: str = ""):
        now_iso = datetime.now().isoformat()
        try:
            if self.use_postgres:
                cur.execute("INSERT INTO audit_logs (actor_id, action, details, created_at) VALUES (%s, %s, %s, CURRENT_TIMESTAMP)", (actor_id, action, details))
            else:
                cur.execute("INSERT INTO audit_logs (actor_id, action, details, created_at) VALUES (?, ?, ?, ?)", (actor_id, action, details, now_iso))
        except Exception:
            pass

    # -------------------------------------------------------------
    # Admin Management APIs
    # -------------------------------------------------------------

    def get_admin_dashboard_stats(self) -> dict:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.use_postgres:
                cur.execute("SELECT COUNT(*) as total_users FROM users")
                u_cnt = cur.fetchone()['total_users']
                cur.execute("SELECT COUNT(*) as total_licenses FROM licenses WHERE is_active = TRUE")
                l_cnt = cur.fetchone()['total_licenses']
                cur.execute("SELECT COUNT(*) as active_devices FROM activated_devices")
                d_cnt = cur.fetchone()['active_devices']
                cur.execute("SELECT COUNT(*) as total_prompts FROM prompt_history")
                p_cnt = cur.fetchone()['total_prompts']
            else:
                cur.execute("SELECT COUNT(*) FROM users")
                u_cnt = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM licenses WHERE is_active = 1")
                l_cnt = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM activated_devices")
                d_cnt = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM prompt_history")
                p_cnt = cur.fetchone()[0]

            return {
                "total_users": u_cnt,
                "active_licenses": l_cnt,
                "activated_devices": d_cnt,
                "total_prompts_generated": p_cnt
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    def list_all_licenses(self) -> list:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            query = """
                SELECT l.*, u.email, u.full_name, u.status as user_status,
                       (SELECT COUNT(*) FROM activated_devices d WHERE d.license_id = l.id) as bound_devices_count
                FROM licenses l
                LEFT JOIN users u ON l.user_id = u.id
                ORDER BY l.valid_until DESC
            """
            cur.execute(query)
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Lỗi list_all_licenses: {e}")
            return []
        finally:
            conn.close()

    def create_user_and_license(self, email: str, password: str, full_name: str, tier: str = "pro", max_devices: int = 2, valid_days: int = 30, allowed_modules: list = None) -> dict:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            email_clean = email.strip().lower()

            # Check if email exists
            if self.use_postgres:
                cur.execute("SELECT id FROM users WHERE LOWER(email) = %s", (email_clean,))
            else:
                cur.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email_clean,))
            if cur.fetchone():
                return {"status": "error", "message": "Email này đã được sử dụng!"}

            if not allowed_modules:
                if tier.lower() == "standard":
                    allowed_modules = ["veo_generate", "video_library"]
                elif tier.lower() == "enterprise":
                    allowed_modules = ["veo_generate", "tiktok_clone", "video_library", "social_autopost", "engine_settings"]
                else:
                    allowed_modules = ["veo_generate", "tiktok_clone", "video_library", "social_autopost"]

            modules_json = json.dumps(allowed_modules)
            user_id = str(uuid.uuid4())
            lic_id = str(uuid.uuid4())
            pwd_h = hash_password(password)
            now = datetime.now()
            v_until = now + timedelta(days=valid_days)
            random_key = f"VEO-PRO-{uuid.uuid4().hex[:4].upper()}-{uuid.uuid4().hex[:4].upper()}"

            if self.use_postgres:
                cur.execute("""
                    INSERT INTO users (id, email, password_hash, full_name, role, status, created_at)
                    VALUES (%s, %s, %s, %s, 'user', 'active', CURRENT_TIMESTAMP)
                """, (user_id, email_clean, pwd_h, full_name))
                cur.execute("""
                    INSERT INTO licenses (id, user_id, license_key, tier, max_devices, daily_video_quota, valid_until, is_active, allowed_modules)
                    VALUES (%s, %s, %s, %s, %s, 500, %s, TRUE, %s)
                """, (lic_id, user_id, random_key, tier, max_devices, v_until, modules_json))
            else:
                cur.execute("""
                    INSERT INTO users (id, email, password_hash, full_name, role, status, created_at)
                    VALUES (?, ?, ?, ?, 'user', 'active', ?)
                """, (user_id, email_clean, pwd_h, full_name, now.isoformat()))
                cur.execute("""
                    INSERT INTO licenses (id, user_id, license_key, tier, max_devices, daily_video_quota, valid_until, is_active, allowed_modules)
                    VALUES (?, ?, ?, ?, ?, 500, ?, 1, ?)
                """, (lic_id, user_id, random_key, tier, max_devices, v_until.isoformat(), modules_json))

            conn.commit()
            return {
                "status": "success",
                "message": "Đã tạo tài khoản & License Key mới thành công!",
                "user_id": user_id,
                "email": email_clean,
                "license_key": random_key,
                "valid_until": v_until.strftime("%d/%m/%Y"),
                "allowed_modules": allowed_modules
            }
        except Exception as e:
            conn.rollback()
            return {"status": "error", "message": f"Lỗi tạo License: {e}"}
        finally:
            conn.close()

    def update_license_modules(self, license_id: str, allowed_modules: list) -> bool:
        """Update allowed modules JSON for an existing license"""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            modules_json = json.dumps(allowed_modules)
            if self.use_postgres:
                cur.execute("UPDATE licenses SET allowed_modules = %s WHERE id = %s", (modules_json, license_id))
            else:
                cur.execute("UPDATE licenses SET allowed_modules = ? WHERE id = ?", (modules_json, license_id))
            conn.commit()
            return True
        except Exception as ex:
            logger.error(f"Lỗi update_license_modules: {ex}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def reset_license_devices(self, license_id: str) -> bool:
        """Unbind all MAC IDs for a license so the user can activate new devices"""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.use_postgres:
                cur.execute("DELETE FROM activated_devices WHERE license_id = %s", (license_id,))
            else:
                cur.execute("DELETE FROM activated_devices WHERE license_id = ?", (license_id,))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            return False
        finally:
            conn.close()

    def toggle_user_block(self, user_id: str, block: bool) -> bool:
        """Block or unblock user account from central server"""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            new_status = 'blocked' if block else 'active'
            if self.use_postgres:
                cur.execute("UPDATE users SET status = %s WHERE id = %s", (new_status, user_id))
            else:
                cur.execute("UPDATE users SET status = ? WHERE id = ?", (new_status, user_id))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            return False
        finally:
            conn.close()

    create_user_with_license = create_user_and_license
    reset_license_mac_bindings = reset_license_devices

    def get_mac_from_request(self, user_agent: str = "") -> str:
        if user_agent and "MAC:" in user_agent:
            try:
                return user_agent.split("MAC:")[1].split(";")[0].strip()
            except Exception:
                pass
        return get_mac_address()

    def validate_heartbeat(self, mac_id: str) -> dict:
        if not mac_id:
            return {"valid": False, "reason": "Không tìm thấy thông tin MAC ID"}
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.use_postgres:
                cur.execute("SELECT id FROM activated_devices WHERE mac_id = %s LIMIT 1", (mac_id,))
            else:
                cur.execute("SELECT id FROM activated_devices WHERE mac_id = ? LIMIT 1", (mac_id,))
            row = cur.fetchone()
            if not row:
                return {"valid": False, "reason": "Thiết bị chưa được đăng ký bản quyền!"}
            return {"valid": True}
        except Exception as e:
            return {"valid": False, "reason": str(e)}
        finally:
            conn.close()

    def reset_user_password(self, user_id: str, new_password: str) -> dict:
        """Reset password for a user account"""
        if not new_password or len(new_password.strip()) < 3:
            return {"status": "error", "message": "Mật khẩu mới phải có ít nhất 3 ký tự!"}
        
        pwd_h = hash_password(new_password.strip())
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.use_postgres:
                cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (pwd_h, user_id))
            else:
                cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pwd_h, user_id))
            
            self._log_audit(cur, user_id, "ADMIN_RESET_PASSWORD", "Admin đã đổi mật khẩu người dùng")
            conn.commit()
            return {"status": "success", "message": "Đã đổi mật khẩu thành công!"}
        except Exception as e:
            conn.rollback()
            return {"status": "error", "message": f"Lỗi đổi mật khẩu: {str(e)}"}
        finally:
            conn.close()



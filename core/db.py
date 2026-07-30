import os
import json
import logging
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path
from config.settings import DB_PATH

logger = logging.getLogger("DatabaseManager")

# Optional PostgreSQL library support
try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


class PgCursorWrapper:
    """Wrapper around psycopg2 cursor that translates SQLite '?' placeholders to '%s'
    and provides lastrowid support via RETURNING id.
    """
    def __init__(self, raw_cursor, conn):
        self._cursor = raw_cursor
        self._conn = conn
        self.lastrowid = None

    def execute(self, query: str, params=None):
        params = params or ()
        # Replace SQLite '?' parameter placeholders with PostgreSQL '%s'
        pg_query = query.replace('?', '%s')
        
        is_insert = pg_query.strip().upper().startswith("INSERT INTO")
        if is_insert and "RETURNING" not in pg_query.upper():
            pg_query = pg_query.rstrip("; ") + " RETURNING id"
        
        self._cursor.execute(pg_query, params)
        if is_insert:
            try:
                res = self._cursor.fetchone()
                if res:
                    if isinstance(res, dict):
                        self.lastrowid = res.get('id')
                    elif isinstance(res, (tuple, list)):
                        self.lastrowid = res[0]
                    elif hasattr(res, 'id'):
                        self.lastrowid = res.id
            except Exception:
                pass
        return self

    def executemany(self, query: str, param_list):
        pg_query = query.replace('?', '%s')
        return self._cursor.executemany(pg_query, param_list)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchmany(self, size=None):
        return self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class PgConnectionWrapper:
    """Wrapper around psycopg2 connection for context manager support (commit/close)."""
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self):
        return PgCursorWrapper(self._conn.cursor(), self._conn)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            try:
                self._conn.rollback()
            except Exception:
                pass
        else:
            try:
                self._conn.commit()
            except Exception:
                pass
        try:
            self._conn.close()
        except Exception:
            pass


class JobStatus(str, Enum):
    PENDING = "PENDING"
    SCRIPTED = "SCRIPTED"
    QUOTA_WAIT = "QUOTA_WAIT"
    GENERATING_VEO = "GENERATING_VEO"
    VEO_DONE = "VEO_DONE"
    PROCESSING_FFMPEG = "PROCESSING_FFMPEG"
    READY_TO_POST = "READY_TO_POST"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class DatabaseManager:
    """Database Manager supporting PostgreSQL with SQLite fallback for Job Queue Tracking"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, postgres_url: str = None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabaseManager, cls).__new__(cls)
                cls._instance._init_manager(postgres_url)
            return cls._instance

    def _init_manager(self, postgres_url: str = None):
        from config.settings import resolve_postgres_url
        self.postgres_url = resolve_postgres_url(postgres_url or os.getenv("POSTGRES_URL", os.getenv("DATABASE_URL", "")))
        self.use_postgres = bool(self.postgres_url and HAS_PSYCOPG2)
        if self.use_postgres:
            try:
                test_conn = psycopg2.connect(self.postgres_url, connect_timeout=3)
                test_conn.close()
            except Exception as e:
                logger.warning(f"[DatabaseManager] PostgreSQL URL không thể kết nối ({e}). Chuyển sang SQLite local.")
                self.use_postgres = False
        self._init_db()

    def _get_connection(self):
        if self.use_postgres:
            try:
                raw_conn = psycopg2.connect(self.postgres_url, cursor_factory=psycopg2.extras.RealDictCursor, connect_timeout=3)
                return PgConnectionWrapper(raw_conn)
            except Exception as e:
                logger.warning(f"[DatabaseManager] Lỗi kết nối PostgreSQL: {e}. Fallback sang SQLite local.")
                self.use_postgres = False
                import sqlite3
                conn = sqlite3.connect(DB_PATH, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                return conn
        else:
            import sqlite3
            conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if self.use_postgres:
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id SERIAL PRIMARY KEY,
                    source_type VARCHAR(100) NOT NULL,
                    source_input TEXT,
                    title TEXT,
                    voiceover_text TEXT,
                    veo_prompt TEXT,
                    tags TEXT,
                    veo_operation_id TEXT,
                    video_raw_path TEXT,
                    audio_path TEXT,
                    video_final_path TEXT,
                    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
                    fb_posted INT DEFAULT 0,
                    tiktok_posted INT DEFAULT 0,
                    x_posted INT DEFAULT 0,
                    error_msg TEXT,
                    voice VARCHAR(100) DEFAULT 'vi-VN-HoaiMyNeural',
                    style VARCHAR(100) DEFAULT 'cinematic',
                    add_voiceover INT DEFAULT 1,
                    add_subtitle INT DEFAULT 1,
                    quality VARCHAR(50) DEFAULT '1080p',
                    aspect_ratio VARCHAR(50) DEFAULT '9:16',
                    duration INT DEFAULT 8,
                    variants INT DEFAULT 1,
                    veo_model VARCHAR(100),
                    keep_context INT DEFAULT 0,
                    batch_id VARCHAR(100),
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS fb_post_logs (
                    id SERIAL PRIMARY KEY,
                    job_id INT NOT NULL,
                    profile_id VARCHAR(255) NOT NULL,
                    profile_name VARCHAR(255) DEFAULT '',
                    status VARCHAR(50) DEFAULT 'pending',
                    posted_at TEXT,
                    error_msg TEXT
                );
                CREATE TABLE IF NOT EXISTS tiktok_post_logs (
                    id SERIAL PRIMARY KEY,
                    job_id INT NOT NULL,
                    profile_id VARCHAR(255) NOT NULL,
                    profile_name VARCHAR(255) DEFAULT '',
                    status VARCHAR(50) DEFAULT 'pending',
                    posted_at TEXT,
                    error_msg TEXT
                );
                """)
                # Auto column migration for PostgreSQL
                for col_name, col_type in [
                    ('voice', "VARCHAR(100) DEFAULT 'vi-VN-HoaiMyNeural'"),
                    ('style', "VARCHAR(100) DEFAULT 'cinematic'"),
                    ('add_voiceover', "INT DEFAULT 1"),
                    ('add_subtitle', "INT DEFAULT 1"),
                    ('quality', "VARCHAR(50) DEFAULT '1080p'"),
                    ('aspect_ratio', "VARCHAR(50) DEFAULT '9:16'"),
                    ('duration', "INT DEFAULT 8"),
                    ('variants', "INT DEFAULT 1"),
                    ('veo_model', "VARCHAR(100)"),
                    ('keep_context', "INT DEFAULT 0"),
                    ('batch_id', "VARCHAR(100)")
                ]:
                    try:
                        cursor.execute(f"ALTER TABLE jobs ADD COLUMN IF NOT EXISTS {col_name} {col_type};")
                    except Exception:
                        pass
                logger.info("[DatabaseManager] DB Initialized on PostgreSQL")
            else:
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    source_input TEXT,
                    title TEXT,
                    voiceover_text TEXT,
                    veo_prompt TEXT,
                    tags TEXT,
                    veo_operation_id TEXT,
                    video_raw_path TEXT,
                    audio_path TEXT,
                    video_final_path TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    fb_posted INTEGER DEFAULT 0,
                    tiktok_posted INTEGER DEFAULT 0,
                    x_posted INTEGER DEFAULT 0,
                    error_msg TEXT,
                    voice TEXT DEFAULT 'vi-VN-HoaiMyNeural',
                    style TEXT DEFAULT 'cinematic',
                    created_at TEXT,
                    updated_at TEXT
                )
                """)
                
                # Auto migrate columns if table already exists
                cursor.execute("PRAGMA table_info(jobs)")
                cols = [r['name'] for r in cursor.fetchall()]
                if 'voice' not in cols:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN voice TEXT DEFAULT 'vi-VN-HoaiMyNeural'")
                if 'style' not in cols:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN style TEXT DEFAULT 'cinematic'")
                if 'add_voiceover' not in cols:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN add_voiceover INTEGER DEFAULT 1")
                if 'add_subtitle' not in cols:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN add_subtitle INTEGER DEFAULT 1")
                if 'quality' not in cols:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN quality TEXT DEFAULT '1080p'")
                if 'aspect_ratio' not in cols:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN aspect_ratio TEXT DEFAULT '9:16'")
                if 'duration' not in cols:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN duration INTEGER DEFAULT 8")
                if 'variants' not in cols:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN variants INTEGER DEFAULT 1")
                if 'veo_model' not in cols:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN veo_model TEXT")
                if 'keep_context' not in cols:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN keep_context INTEGER DEFAULT 0")
                if 'batch_id' not in cols:
                    cursor.execute("ALTER TABLE jobs ADD COLUMN batch_id TEXT")

                # fb_post_logs
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS fb_post_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    profile_id TEXT NOT NULL,
                    profile_name TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    posted_at TEXT,
                    error_msg TEXT
                )
                """)

                # tiktok_post_logs
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS tiktok_post_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    profile_id TEXT NOT NULL,
                    profile_name TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    posted_at TEXT,
                    error_msg TEXT
                )
                """)
                logger.info("[DatabaseManager] DB Initialized on SQLite")

    def create_job(
        self,
        source_type: str,
        source_input: str,
        title: str = "",
        voiceover_text: str = "",
        veo_prompt: str = "",
        tags: list = None,
        voice: str = "vi-VN-HoaiMyNeural",
        style: str = "cinematic",
        add_voiceover: bool = True,
        add_subtitle: bool = True,
        quality: str = "1080p",
        aspect_ratio: str = "9:16",
        duration: int = 8,
        variants: int = 1,
        veo_model: str = None,
        keep_context: bool = False,
        batch_id: str = None
    ) -> int:
        now = datetime.now().isoformat()
        tags_str = json.dumps(tags or [], ensure_ascii=False)
        status = JobStatus.SCRIPTED.value if veo_prompt else JobStatus.PENDING.value

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO jobs (source_type, source_input, title, voiceover_text, veo_prompt, tags, voice, style, add_voiceover, add_subtitle, quality, aspect_ratio, duration, variants, veo_model, keep_context, batch_id, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (source_type, source_input, title, voiceover_text, veo_prompt, tags_str, voice, style, int(add_voiceover), int(add_subtitle), quality, aspect_ratio, duration, variants, veo_model, int(keep_context), batch_id, status, now, now))
            return cursor.lastrowid

    def update_job(self, job_id: int, **kwargs):
        now = datetime.now().isoformat()
        kwargs['updated_at'] = now
        
        if 'tags' in kwargs and isinstance(kwargs['tags'], list):
            kwargs['tags'] = json.dumps(kwargs['tags'], ensure_ascii=False)
            
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [job_id]

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)

    def get_job(self, job_id: int) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                if d.get('tags'):
                    try:
                        d['tags'] = json.loads(d['tags'])
                    except Exception:
                        pass
                return d
            return None

    def get_jobs_by_status(self, status: JobStatus, limit: int = 50) -> list:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE status = ? ORDER BY id ASC LIMIT ?", (status.value, limit))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def delete_job(self, job_id: int) -> bool:
        job = self.get_job(job_id)
        if not job:
            return False

        # Cleanup physical video/audio files if exist
        for key in ['video_raw_path', 'audio_path', 'video_final_path']:
            if job.get(key):
                try:
                    p = Path(job[key])
                    if p.exists():
                        p.unlink(missing_ok=True)
                except Exception:
                    pass

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            return cursor.rowcount > 0

    def get_jobs_by_batch(self, batch_id: str) -> list:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE batch_id = ? ORDER BY id ASC", (batch_id,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_statistics(self) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, COUNT(*) as count FROM jobs GROUP BY status")
            rows = cursor.fetchall()
            stats = {status.value: 0 for status in JobStatus}
            for row in rows:
                r_dict = dict(row)
                stats[r_dict['status']] = r_dict['count']
            return stats

    # ─────────────────────────────────────────────────────────
    # FB Post Logs — per-profile, per-job tracking
    # ─────────────────────────────────────────────────────────
    def log_fb_post(self, job_id: int, profile_id: str, profile_name: str = "") -> int:
        """Create a pending log entry. Returns log_id."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO fb_post_logs (job_id, profile_id, profile_name, status, posted_at)
                VALUES (?, ?, ?, 'pending', ?)
            """, (job_id, profile_id, profile_name, now))
            return cursor.lastrowid

    def update_fb_post_log(self, log_id: int, status: str, error_msg: str = None):
        """Update status: pending → posting → success | failed"""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE fb_post_logs
                SET status = ?, posted_at = ?, error_msg = ?
                WHERE id = ?
            """, (status, now, error_msg, log_id))

    def get_fb_post_logs(self, job_id: int) -> list:
        """Get all profile logs for a specific job."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM fb_post_logs WHERE job_id = ? ORDER BY id ASC",
                (job_id,)
            )
            return [dict(r) for r in cursor.fetchall()]

    # ─────────────────────────────────────────────────────────
    # TikTok Post Logs — per-profile, per-job tracking
    # ─────────────────────────────────────────────────────────
    def log_tiktok_post(self, job_id: int, profile_id: str, profile_name: str = "") -> int:
        """Create a pending log entry for TikTok. Returns log_id."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tiktok_post_logs (job_id, profile_id, profile_name, status, posted_at)
                VALUES (?, ?, ?, 'pending', ?)
            """, (job_id, profile_id, profile_name, now))
            return cursor.lastrowid

    def update_tiktok_post_log(self, log_id: int, status: str, error_msg: str = None):
        """Update status: pending → posting → success | failed"""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tiktok_post_logs
                SET status = ?, posted_at = ?, error_msg = ?
                WHERE id = ?
            """, (status, now, error_msg, log_id))

    def get_tiktok_post_logs(self, job_id: int) -> list:
        """Get all TikTok profile logs for a specific job."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM tiktok_post_logs WHERE job_id = ? ORDER BY id ASC",
                (job_id,)
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_all_jobs(self, limit: int = 200) -> list:
        """Get all jobs ordered by most recent first."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if d.get('tags'):
                    try: d['tags'] = json.loads(d['tags'])
                    except Exception: pass
                result.append(d)
            return result

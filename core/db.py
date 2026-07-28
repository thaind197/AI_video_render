import sqlite3
import json
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path
from config.settings import DB_PATH

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
    """Thread-safe SQLite Database Manager for Job Queue Tracking"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabaseManager, cls).__new__(cls)
                cls._instance._init_db()
            return cls._instance

    def _get_connection(self):
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
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
            conn.commit()

            # fb_post_logs: track per-profile posting per job
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

            # tiktok_post_logs: track per-profile posting per job for TikTok
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
            conn.commit()

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
            conn.commit()
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
            conn.commit()

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
                except Exception as e:
                    pass

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            conn.commit()
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
                stats[row['status']] = row['count']
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
            conn.commit()
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
            conn.commit()

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
            conn.commit()
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
            conn.commit()

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

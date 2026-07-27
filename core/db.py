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
                created_at TEXT,
                updated_at TEXT
            )
            """)
            conn.commit()

    def create_job(self, source_type: str, source_input: str, title: str = "", voiceover_text: str = "", veo_prompt: str = "", tags: list = None) -> int:
        now = datetime.now().isoformat()
        tags_str = json.dumps(tags or [], ensure_ascii=False)
        status = JobStatus.SCRIPTED.value if veo_prompt else JobStatus.PENDING.value
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO jobs (source_type, source_input, title, voiceover_text, veo_prompt, tags, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (source_type, source_input, title, voiceover_text, veo_prompt, tags_str, status, now, now))
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

    def get_statistics(self) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, COUNT(*) as count FROM jobs GROUP BY status")
            rows = cursor.fetchall()
            stats = {status.value: 0 for status in JobStatus}
            for row in rows:
                stats[row['status']] = row['count']
            return stats

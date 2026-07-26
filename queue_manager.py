import time
import logging
from concurrent.futures import ThreadPoolExecutor
from config.settings import (
    MAX_CONCURRENT_VEO_JOBS,
    MAX_CONCURRENT_PROCESSING,
    MAX_CONCURRENT_POST_JOBS
)
from core.db import DatabaseManager, JobStatus
from core.script_engine import ScriptEngine
from core.video_cloner import VideoCloner
from core.veo_generator import VeoGenerator
from core.video_processor import VideoProcessor
from publishers.facebook_publisher import FacebookPublisher
from publishers.tiktok_publisher import TikTokPublisher
from publishers.x_publisher import XPublisher

logger = logging.getLogger(__name__)

class MultiThreadQueueManager:
    """Orchestrates multi-threaded processing pipeline for 100 videos/day target"""

    def __init__(self):
        self.db = DatabaseManager()
        self.script_engine = ScriptEngine()
        self.cloner = VideoCloner()
        self.veo_gen = VeoGenerator()
        self.video_processor = VideoProcessor()
        self.fb_pub = FacebookPublisher()
        self.tiktok_pub = TikTokPublisher()
        self.x_pub = XPublisher()

        # Thread Pools for pipeline stages
        self.script_pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="ScriptWorker")
        self.veo_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_VEO_JOBS, thread_name_prefix="VeoWorker")
        self.process_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PROCESSING, thread_name_prefix="RenderWorker")
        self.post_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_POST_JOBS, thread_name_prefix="PostWorker")

        self.is_running = False
        self.active_jobs = set()
        self.last_quota_retry_time = 0
        self.lock = __import__("threading").Lock()

    def _safe_submit(self, pool, func, job_id):
        with self.lock:
            if job_id in self.active_jobs:
                return
            self.active_jobs.add(job_id)

        def wrapped():
            try:
                func(job_id)
            finally:
                with self.lock:
                    self.active_jobs.discard(job_id)

        pool.submit(wrapped)

    def add_prompt_batch(self, topic: str, count: int = 10, styles: list = None, voices: list = None, keep_context: bool = True, custom_context: str = ""):
        """Add batch of prompt jobs to queue with selected styles, voices & context persistence"""
        logger.info(f"Đang sinh {count} kịch bản từ chủ đề: '{topic}' với styles={styles}, voices={voices}, keep_context={keep_context}...")
        scripts = self.script_engine.generate_batch_scripts(topic, count=count, keep_context=keep_context, custom_context=custom_context)
        added_count = 0
        
        valid_styles = styles or ["cinematic"]
        valid_voices = voices or ["vi-VN-HoaiMyNeural"]

        for idx, s in enumerate(scripts):
            assigned_style = valid_styles[idx % len(valid_styles)]
            assigned_voice = valid_voices[idx % len(valid_voices)]

            # Sử dụng trực tiếp topic nhập từ UI làm Veo Prompt
            veo_prompt = topic.strip()
            if custom_context:
                veo_prompt += f", {custom_context}"
            if assigned_style:
                veo_prompt += f", {assigned_style} style"

            self.db.create_job(
                source_type="PROMPT",
                source_input=topic,
                title=s.get('title', ''),
                voiceover_text=s.get('voiceover_text', ''),
                veo_prompt=veo_prompt,
                tags=s.get('tags', []),
                voice=assigned_voice,
                style=assigned_style
            )
            added_count += 1
        logger.info(f"Đã thêm thành công {added_count} job vào hàng chờ DB!")
        return added_count

    def add_clone_job(self, video_url: str, add_voiceover: bool = True, add_subtitle: bool = True):
        """Add a video clone URL job to queue with optional voiceover/subtitle"""
        job_id = self.db.create_job(
            source_type="CLONE",
            source_input=video_url,
            add_voiceover=add_voiceover,
            add_subtitle=add_subtitle
        )
        logger.info(f"Đã thêm Job Clone #{job_id} | voiceover={add_voiceover} | subtitle={add_subtitle} | link: {video_url}")
        return job_id

    def _process_publish_job(self, job_id: int):
        """Worker function for auto publishing ready videos"""
        job = self.db.get_job(job_id)
        if not job or job['status'] != JobStatus.READY_TO_POST.value:
            return

        has_fb = self.fb_pub.is_logged_in()
        has_tiktok = self.tiktok_pub.is_logged_in()
        has_x = self.x_pub.is_logged_in()

        # If no social account is logged in, keep video at READY_TO_POST (Render completed)
        if not (has_fb or has_tiktok or has_x):
            return

        # Guard: video_final_path must exist before publishing
        video_final = job.get('video_final_path') or job.get('video_raw_path')
        if not video_final:
            logger.error(f"Job #{job_id}: Không có video_final_path để đăng bài, bỏ qua.")
            self.db.update_job(job_id, status=JobStatus.READY_TO_POST.value, error_msg="Thiếu file video cuối")
            return
        video_path = Path(video_final)
        if not video_path.exists():
            logger.error(f"Job #{job_id}: File video không tồn tại: {video_path}, bỏ qua.")
            self.db.update_job(job_id, status=JobStatus.READY_TO_POST.value, error_msg=f"File không tồn tại: {video_path.name}")
            return

        self.db.update_job(job_id, status=JobStatus.PUBLISHING.value)

        # Build caption — truncate voiceover to keep caption ≤ 2200 chars (FB/TikTok limit)
        title = (job.get('title') or '').strip()
        voiceover = (job.get('voiceover_text') or '').strip()
        max_caption = 2000
        base = f"{title}\n\n" if title else ""
        remaining = max_caption - len(base)
        if len(voiceover) > remaining:
            voiceover = voiceover[:remaining].rsplit(' ', 1)[0] + "..."
        caption = base + voiceover

        import json
        raw_tags = job.get('tags', [])
        if isinstance(raw_tags, str):
            try:
                raw_tags = json.loads(raw_tags)
            except Exception:
                raw_tags = []
        tags = raw_tags if isinstance(raw_tags, list) else []

        fb_success = False
        tiktok_success = False
        x_success = False

        # Priority 1: Facebook Reels (Multi-Profile Parallel Posting)
        if not job.get('fb_posted'):
            from publishers.fb_profile_manager import FBProfileManager
            fb_mgr = FBProfileManager()
            logged_in_fb_profiles = [p["id"] for p in fb_mgr.list_profiles() if p.get("logged_in")]
            if logged_in_fb_profiles:
                logger.info(f"Job #{job_id}: Tự động đăng đa luồng cho {len(logged_in_fb_profiles)} profiles Facebook...")
                results = fb_mgr.post_to_profiles_parallel(
                    video_path=video_path,
                    caption=caption,
                    profile_ids=logged_in_fb_profiles,
                    max_workers=min(len(logged_in_fb_profiles), 5),
                    tags=tags
                )
                if any(results.values()):
                    self.db.update_job(job_id, fb_posted=1)
                    fb_success = True

        # Priority 2: TikTok (Multi-Profile Parallel Posting)
        if not job.get('tiktok_posted'):
            from publishers.tiktok_profile_manager import TikTokProfileManager
            tiktok_mgr = TikTokProfileManager()
            logged_in_tiktok_profiles = [p["id"] for p in tiktok_mgr.list_profiles() if p.get("logged_in")]
            if logged_in_tiktok_profiles:
                logger.info(f"Job #{job_id}: Tự động đăng đa luồng cho {len(logged_in_tiktok_profiles)} profiles TikTok...")
                results = tiktok_mgr.post_to_profiles_parallel(
                    video_path=video_path,
                    caption=caption,
                    profile_ids=logged_in_tiktok_profiles,
                    max_workers=min(len(logged_in_tiktok_profiles), 5),
                    tags=tags
                )
                if any(results.values()):
                    self.db.update_job(job_id, tiktok_posted=1)
                    tiktok_success = True

        # Priority 3: X (Twitter)
        if has_x and not job.get('x_posted'):
            x_success = self.x_pub.post_video(video_path, caption, tags)
            if x_success:
                self.db.update_job(job_id, x_posted=1)

        if fb_success or tiktok_success or x_success:
            self.db.update_job(job_id, status=JobStatus.PUBLISHED.value)
        else:
            self.db.update_job(job_id, status=JobStatus.READY_TO_POST.value)

    def run_worker_cycle(self):
        """Single processing iteration across all queues with duplication protection and quota throttling"""
        # 1. Process PENDING Jobs
        pending_jobs = self.db.get_jobs_by_status(JobStatus.PENDING, limit=10)
        for job in pending_jobs:
            if job['source_type'] == 'PROMPT':
                self._safe_submit(self.script_pool, self.script_engine.process_pending_script_job, job['id'])
            elif job['source_type'] == 'CLONE':
                self._safe_submit(self.script_pool, self.cloner.process_clone_job, job['id'])

        # 2. Process SCRIPTED Jobs -> Veo API
        scripted_jobs = self.db.get_jobs_by_status(JobStatus.SCRIPTED, limit=MAX_CONCURRENT_VEO_JOBS)
        for job in scripted_jobs:
            self._safe_submit(self.veo_pool, self.veo_gen.process_veo_job, job['id'])

        # 2.5 Process QUOTA_WAIT retry -> only every 180 seconds to avoid API ban & spam
        now = time.time()
        if now - self.last_quota_retry_time > 180:
            quota_wait_jobs = self.db.get_jobs_by_status(JobStatus.QUOTA_WAIT, limit=2)
            if quota_wait_jobs:
                logger.info(f"🔄 Thử retry {len(quota_wait_jobs)} job QUOTA_WAIT sau 3 phút...")
                self.last_quota_retry_time = now
                for job in quota_wait_jobs:
                    self._safe_submit(self.veo_pool, self.veo_gen.process_veo_job, job['id'])

        # 3. Process VEO_DONE Jobs -> FFmpeg Render
        veo_done_jobs = self.db.get_jobs_by_status(JobStatus.VEO_DONE, limit=MAX_CONCURRENT_PROCESSING)
        for job in veo_done_jobs:
            self._safe_submit(self.process_pool, self.video_processor.process_render_job, job['id'])

        # 4. Process READY_TO_POST Jobs -> Social Auto Post
        from publishers.fb_profile_manager import FBProfileManager
        from publishers.tiktok_profile_manager import TikTokProfileManager
        has_fb = any(p.get("logged_in") for p in FBProfileManager().list_profiles())
        has_tiktok = any(p.get("logged_in") for p in TikTokProfileManager().list_profiles())
        has_x = self.x_pub.is_logged_in()

        if has_fb or has_tiktok or has_x:
            ready_jobs = self.db.get_jobs_by_status(JobStatus.READY_TO_POST, limit=MAX_CONCURRENT_POST_JOBS)
            for job in ready_jobs:
                self._safe_submit(self.post_pool, self._process_publish_job, job['id'])

    def start_loop(self, poll_interval_sec: int = 10):
        """Start continuous multi-thread worker background loop"""
        self.is_running = True
        logger.info("Đã khởi chạy Queue Manager đa luồng thành công!")
        try:
            while self.is_running:
                self.run_worker_cycle()
                time.sleep(poll_interval_sec)
        except KeyboardInterrupt:
            logger.info("Đang dừng Queue Manager...")
            self.stop()

    def stop(self):
        self.is_running = False
        self.script_pool.shutdown(wait=False)
        self.veo_pool.shutdown(wait=False)
        self.process_pool.shutdown(wait=False)
        self.post_pool.shutdown(wait=False)

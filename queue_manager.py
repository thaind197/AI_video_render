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

    def add_prompt_batch(self, topic: str, count: int = 10):
        """Add batch of prompt jobs to queue"""
        logger.info(f"Đang sinh {count} kịch bản từ chủ đề: '{topic}'...")
        scripts = self.script_engine.generate_batch_scripts(topic, count=count)
        added_count = 0
        for s in scripts:
            self.db.create_job(
                source_type="PROMPT",
                source_input=topic,
                title=s.get('title', ''),
                voiceover_text=s.get('voiceover_text', ''),
                veo_prompt=s.get('veo_prompt', ''),
                tags=s.get('tags', [])
            )
            added_count += 1
        logger.info(f"Đã thêm thành công {added_count} job vào hàng chờ DB!")
        return added_count

    def add_clone_job(self, video_url: str):
        """Add a video clone URL job to queue"""
        job_id = self.db.create_job(source_type="CLONE", source_input=video_url)
        logger.info(f"Đã thêm Job Clone #{job_id} cho link: {video_url}")
        return job_id

    def _process_publish_job(self, job_id: int):
        """Worker function for auto publishing ready videos"""
        job = self.db.get_job(job_id)
        if not job or job['status'] != JobStatus.READY_TO_POST.value:
            return

        self.db.update_job(job_id, status=JobStatus.PUBLISHING.value)
        video_path = Path(job['video_final_path'])
        caption = f"{job['title']}\n\n{job['voiceover_text']}"
        tags = job.get('tags', [])

        fb_success = True
        tiktok_success = True
        x_success = True

        # Priority 1: Facebook Reels
        if not job.get('fb_posted'):
            fb_success = self.fb_pub.post_video(video_path, caption, tags)
            if fb_success:
                self.db.update_job(job_id, fb_posted=1)

        # Priority 2: TikTok
        if not job.get('tiktok_posted'):
            tiktok_success = self.tiktok_pub.post_video(video_path, caption, tags)
            if tiktok_success:
                self.db.update_job(job_id, tiktok_posted=1)

        # Priority 3: X (Twitter)
        if not job.get('x_posted'):
            x_success = self.x_pub.post_video(video_path, caption, tags)
            if x_success:
                self.db.update_job(job_id, x_posted=1)

        if fb_success or tiktok_success or x_success:
            self.db.update_job(job_id, status=JobStatus.PUBLISHED.value)
        else:
            self.db.update_job(job_id, status=JobStatus.FAILED.value, error_msg="Đăng bài social thất bại")

    def run_worker_cycle(self):
        """Single processing iteration across all queues"""
        # 1. Process PENDING Jobs
        pending_jobs = self.db.get_jobs_by_status(JobStatus.PENDING, limit=10)
        for job in pending_jobs:
            if job['source_type'] == 'PROMPT':
                self.script_pool.submit(self.script_engine.process_pending_script_job, job['id'])
            elif job['source_type'] == 'CLONE':
                self.script_pool.submit(self.cloner.process_clone_job, job['id'])

        # 2. Process SCRIPTED Jobs -> Veo API
        scripted_jobs = self.db.get_jobs_by_status(JobStatus.SCRIPTED, limit=MAX_CONCURRENT_VEO_JOBS)
        for job in scripted_jobs:
            self.veo_pool.submit(self.veo_gen.process_veo_job, job['id'])

        # 3. Process VEO_DONE Jobs -> FFmpeg Render
        veo_done_jobs = self.db.get_jobs_by_status(JobStatus.VEO_DONE, limit=MAX_CONCURRENT_PROCESSING)
        for job in veo_done_jobs:
            self.process_pool.submit(self.video_processor.process_render_job, job['id'])

        # 4. Process READY_TO_POST Jobs -> Social Auto Post
        ready_jobs = self.db.get_jobs_by_status(JobStatus.READY_TO_POST, limit=MAX_CONCURRENT_POST_JOBS)
        for job in ready_jobs:
            self.post_pool.submit(self._process_publish_job, job['id'])

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

import time
import logging
from concurrent.futures import ThreadPoolExecutor
from config.settings import (
    MAX_CONCURRENT_VEO_JOBS,
    MAX_CONCURRENT_LABS_JOBS,
    MAX_CONCURRENT_PROCESSING,
    MAX_CONCURRENT_POST_JOBS,
    DEFAULT_ASPECT_RATIO,
    DEFAULT_VEO_DURATION,
    DEFAULT_VEO_VARIANTS,
    DEFAULT_VEO_MODEL
)
from core.db import DatabaseManager, JobStatus
from core.script_engine import ScriptEngine
from core.video_cloner import VideoCloner
from core.veo_generator import VeoGenerator
from core.video_processor import VideoProcessor
from core.labs_google_generator import LabsGoogleGenerator
from publishers.facebook_publisher import FacebookPublisher
from publishers.tiktok_publisher import TikTokPublisher
from publishers.x_publisher import XPublisher
import threading
import uuid
logger = logging.getLogger(__name__)

class MultiThreadQueueManager:
    """Orchestrates multi-threaded processing pipeline for 100 videos/day target"""

    def __init__(self):
        self.db = DatabaseManager()
        self.script_engine = ScriptEngine()
        self.cloner = VideoCloner()
        self.veo_gen = VeoGenerator()
        self.labs_gen = LabsGoogleGenerator()
        self.video_processor = VideoProcessor()
        self.fb_pub = FacebookPublisher()
        self.tiktok_pub = TikTokPublisher()
        self.x_pub = XPublisher()

        # Thread Pools for pipeline stages
        self.script_pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="ScriptWorker")
        self.veo_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_VEO_JOBS, thread_name_prefix="VeoWorker")
        self.labs_pool = ThreadPoolExecutor(max_workers=max(1, MAX_CONCURRENT_LABS_JOBS), thread_name_prefix="LabsWorker")
        self.process_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PROCESSING, thread_name_prefix="RenderWorker")
        self.post_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_POST_JOBS, thread_name_prefix="PostWorker")

        # Dynamic Worker Pool for Multi-Browser Labs Automation
        self.labs_worker_ids = set(range(1, MAX_CONCURRENT_LABS_JOBS + 1))
        self.labs_worker_lock = threading.Lock()
        self.labs_semaphore = threading.BoundedSemaphore(value=max(1, MAX_CONCURRENT_LABS_JOBS))

        # Context Persistence Tracking for keep_context series (Sequential execution in 1 thread)
        self.active_context_batches = set()
        self.batch_worker_map = {}

        self.is_running = False
        self.active_jobs = set()
        self.last_quota_retry_time = 0
        self.lock = threading.Lock()

    def _acquire_labs_worker_id(self) -> int:
        with self.labs_worker_lock:
            if self.labs_worker_ids:
                return self.labs_worker_ids.pop()
            return 1

    def _release_labs_worker_id(self, worker_id: int):
        with self.labs_worker_lock:
            self.labs_worker_ids.add(worker_id)

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

    def add_prompt_batch(
        self,
        topic: str,
        count: int = 10,
        styles: list = None,
        voices: list = None,
        keep_context: bool = True,
        custom_context: str = "",
        aspect_ratio: str = "9:16",
        duration: int = 8,
        variants: int = 1,
        veo_model: str = None,
        quality: str = "1080p"
    ):
        """Add batch of prompt jobs to queue with selected styles, voices & context persistence"""
        batch_id = f"batch_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        logger.info(f"Đang sinh {count} kịch bản từ chủ đề: '{topic}' [batch_id={batch_id}] với styles={styles}, voices={voices}, keep_context={keep_context}...")
        scripts = self.script_engine.generate_batch_scripts(topic, count=count, keep_context=keep_context, custom_context=custom_context)
        added_count = 0
        
        valid_styles = styles or ["cinematic"]
        valid_voices = voices or ["vi-VN-HoaiMyNeural"]

        for idx, s in enumerate(scripts):
            assigned_style = valid_styles[idx % len(valid_styles)]
            assigned_voice = valid_voices[idx % len(valid_voices)]

            # Ưu tiên lấy veo_prompt thông minh được Gemini AI sinh cho từng tập khi keep_context
            ai_veo_prompt = s.get('veo_prompt', '').strip()
            if ai_veo_prompt:
                veo_prompt = ai_veo_prompt
            else:
                veo_prompt = topic.strip()
                if custom_context:
                    veo_prompt += f", {custom_context}"
                if assigned_style:
                    veo_prompt += f", {assigned_style} style"

            from config.settings import DEFAULT_GEN_ENGINE
            source_type_val = "LABS_PROMPT" if getattr(DEFAULT_GEN_ENGINE, 'lower', lambda: 'labs')() == 'labs' else "PROMPT"

            self.db.create_job(
                source_type=source_type_val,
                source_input=topic,
                title=s.get('title', f"Tập {idx+1}: {topic[:30]}"),
                voiceover_text=s.get('voiceover_text', ''),
                veo_prompt=veo_prompt,
                tags=s.get('tags', []),
                voice=assigned_voice,
                style=assigned_style,
                aspect_ratio=aspect_ratio or DEFAULT_ASPECT_RATIO or "9:16",
                duration=duration or DEFAULT_VEO_DURATION or 8,
                variants=variants or DEFAULT_VEO_VARIANTS or 1,
                veo_model=veo_model or DEFAULT_VEO_MODEL,
                quality=quality or "1080p",
                keep_context=keep_context,
                batch_id=batch_id
            )
            added_count += 1
        logger.info(f"Đã thêm thành công {added_count} job vào hàng chờ DB (engine={DEFAULT_GEN_ENGINE})!")
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

    def process_labs_google_job(self, job_id: int):
        """Worker function: Process job using labs.google browser automation with multi-browser parallel & context persistence support"""
        job = self.db.get_job(job_id)
        if not job or job['status'] not in (JobStatus.SCRIPTED.value, JobStatus.PENDING.value):
            batch_id = job.get('batch_id') if job else None
            keep_ctx = bool(job.get('keep_context', False)) if job else False
            if keep_ctx and batch_id:
                with self.lock:
                    self.active_context_batches.discard(batch_id)
            return

        batch_id = job.get('batch_id')
        keep_context = bool(job.get('keep_context', False))

        try:
            from config.settings import (
                GENERATED_DIR,
                DEFAULT_ASPECT_RATIO,
                DEFAULT_VEO_DURATION,
                DEFAULT_VEO_VARIANTS,
                DEFAULT_VEO_MODEL
            )
            self.db.update_job(job_id, status=JobStatus.GENERATING_VEO.value)
            out_raw_path = GENERATED_DIR / f"raw_{job_id}.mp4"

            prompt = job.get('veo_prompt') or job.get('source_input') or job.get('title')
            quality = job.get('quality') or '1080p'
            aspect_ratio = job.get('aspect_ratio') or DEFAULT_ASPECT_RATIO or "9:16"
            duration = job.get('duration') or DEFAULT_VEO_DURATION or 8
            variants = job.get('variants') or DEFAULT_VEO_VARIANTS or 1
            veo_model = job.get('veo_model') or DEFAULT_VEO_MODEL

            self.labs_semaphore.acquire()
            worker_id = None
            if keep_context and batch_id:
                with self.labs_worker_lock:
                    if batch_id in self.batch_worker_map:
                        worker_id = self.batch_worker_map[batch_id]

            if worker_id is None:
                worker_id = self._acquire_labs_worker_id()
                if keep_context and batch_id:
                    with self.labs_worker_lock:
                        self.batch_worker_map[batch_id] = worker_id

            ok = False
            try:
                logger.info(f"Job #{job_id}: Bắt đầu chạy trên Labs Worker #{worker_id} (keep_context={keep_context}, batch={batch_id}) | {aspect_ratio} | {duration}s | {variants}x | Model: {veo_model}")
                ok = self.labs_gen.generate_video(
                    prompt=prompt,
                    out_path=out_raw_path,
                    aspect_ratio=aspect_ratio,
                    duration=duration,
                    variants=variants,
                    model=veo_model,
                    quality=quality,
                    worker_id=worker_id
                )
            finally:
                if keep_context and batch_id:
                    with self.lock:
                        self.active_context_batches.discard(batch_id)
                    remaining = self.db.get_jobs_by_batch(batch_id)
                    has_remaining = any(r['status'] in (JobStatus.SCRIPTED.value, JobStatus.PENDING.value) and r['id'] != job_id for r in remaining)
                    if not has_remaining:
                        with self.labs_worker_lock:
                            self.batch_worker_map.pop(batch_id, None)
                            self.labs_worker_ids.add(worker_id)
                        self.labs_semaphore.release()
                    else:
                        self.labs_semaphore.release()
                else:
                    self._release_labs_worker_id(worker_id)
                    self.labs_semaphore.release()

            if ok and out_raw_path.exists():
                self.db.update_job(
                    job_id,
                    video_raw_path=str(out_raw_path),
                    status=JobStatus.VEO_DONE.value
                )
            else:
                logger.warning(f"Job #{job_id}: labs.google browser automation không thành công, thử dùng VeoGenerator API...")
                self.veo_gen.process_veo_job(job_id)
        except Exception as e:
            logger.exception(f"Lỗi LabsGoogle job #{job_id}: {e}")
            if keep_context and batch_id:
                with self.lock:
                    self.active_context_batches.discard(batch_id)
            self.db.update_job(job_id, status=JobStatus.FAILED.value, error_msg=str(e))

    def run_worker_cycle(self):
        """Single processing iteration across all queues with duplication protection and quota throttling"""
        # 1. Process PENDING Jobs
        pending_jobs = self.db.get_jobs_by_status(JobStatus.PENDING, limit=10)
        for job in pending_jobs:
            if job['source_type'] == 'PROMPT':
                self._safe_submit(self.script_pool, self.script_engine.process_pending_script_job, job['id'])
            elif job['source_type'] == 'LABS_PROMPT':
                self.db.update_job(job['id'], status=JobStatus.SCRIPTED.value)
            elif job['source_type'] == 'CLONE':
                self._safe_submit(self.script_pool, self.cloner.process_clone_job, job['id'])

        # 2. Process SCRIPTED Jobs -> Veo API or Labs Google Browser Automation (Multi-Browser)
        scripted_jobs = self.db.get_jobs_by_status(JobStatus.SCRIPTED, limit=20)
        from config.settings import DEFAULT_GEN_ENGINE, GEMINI_API_KEY
        for job in scripted_jobs:
            use_labs = (
                job.get('source_type') == 'LABS_PROMPT' or
                getattr(DEFAULT_GEN_ENGINE, 'lower', lambda: 'labs')() == 'labs' or
                not (GEMINI_API_KEY and GEMINI_API_KEY.strip())
            )
            if use_labs:
                keep_ctx = bool(job.get('keep_context', False))
                b_id = job.get('batch_id')
                if keep_ctx and b_id:
                    with self.lock:
                        if b_id in self.active_context_batches:
                            # Tập trước trong cùng chuỗi batch keep_context này đang chạy. Chờ tập trước chạy xong!
                            continue
                        self.active_context_batches.add(b_id)
                self._safe_submit(self.labs_pool, self.process_labs_google_job, job['id'])
            else:
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
        self.labs_pool.shutdown(wait=False)
        self.process_pool.shutdown(wait=False)
        self.post_pool.shutdown(wait=False)

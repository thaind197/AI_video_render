import json
import logging
from google import genai
from config.settings import GEMINI_API_KEY
from config.prompt_templates import BATCH_SCRIPT_GEN_PROMPT, VIDEO_CLONE_REMAKE_PROMPT
from core.db import DatabaseManager, JobStatus

logger = logging.getLogger(__name__)

class ScriptEngine:
    """Generates 10s short video scripts & Google Veo prompts using Gemini 1.5 Flash"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or GEMINI_API_KEY
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception:
                self.client = None
        else:
            self.client = None

    def _generate_fallback_scripts(self, topic: str, count: int = 10) -> list:
        """Generate smart fallback scripts when GEMINI_API_KEY is not configured"""
        scripts = []
        for i in range(1, count + 1):
            scripts.append({
                "title": f"{topic} - Mẹo Hay #{i}",
                "hook": f"Bạn có biết điều này về {topic} chưa?",
                "voiceover_text": f"Khám phá ngay bí quyết đỉnh cao về {topic} năm 2026. Áp dụng ngay hôm nay để đạt hiệu quả gấp đôi!",
                "veo_prompt": f"Continuous 9:16 vertical 4k cinematic shot showing futuristic concept of {topic}, dramatic lighting, hyper-realistic, 30fps",
                "tags": [f"#{topic.replace(' ', '')}", "#Shorts", "#AI2026", "#VeoStudio"]
            })
        return scripts

    def generate_batch_scripts(self, topic: str, count: int = 10) -> list:
        """Generate a batch of 10s video scripts from a single topic prompt"""
        if not self.client:
            logger.info("Dùng Template Script Engine Fallback (Chưa nạp GEMINI_API_KEY)")
            return self._generate_fallback_scripts(topic, count)

        prompt = BATCH_SCRIPT_GEN_PROMPT.format(topic=topic, count=count)

        try:
            response = self.client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt,
                config={
                    'response_mime_type': 'application/json',
                    'temperature': 0.7
                }
            )

            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            scripts = json.loads(text.strip())
            return scripts
        except Exception as e:
            logger.error(f"Lỗi gọi Gemini API ({e}), chuyển sang fallback script...")
            return self._generate_fallback_scripts(topic, count)

    def remake_script(self, transcript: str, vision_description: str) -> dict:
        """Remake a cloned video transcript/description into a new fresh 10s script"""
        if not self.client:
            return {
                "title": "TikTok Video Remake AI",
                "voiceover_text": f"Nội dung tái tạo độc đáo từ video gốc: {transcript[:40]}... Khám phá xu hướng mới nhất năm 2026!",
                "veo_prompt": "Continuous 9:16 vertical video shot, 4k resolution, cinematic lighting, hyper-realistic motion",
                "tags": ["#Remake", "#Shorts", "#AI2026"]
            }

        prompt = VIDEO_CLONE_REMAKE_PROMPT.format(
            transcript=transcript or "Không có thoại",
            vision_description=vision_description or "Video ngắn ấn tượng"
        )

        try:
            response = self.client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt,
                config={
                    'response_mime_type': 'application/json',
                    'temperature': 0.8
                }
            )

            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            return json.loads(text.strip())
        except Exception as e:
            logger.error(f"Lỗi parse JSON remake script: {e}")
            return {
                "title": "TikTok Video Remake AI",
                "voiceover_text": "Nội dung tái tạo độc đáo năm 2026!",
                "veo_prompt": "Continuous 9:16 vertical video shot, 4k resolution",
                "tags": ["#Remake", "#Shorts"]
            }

    def process_pending_script_job(self, job_id: int):
        """Worker function: Process a PENDING job and generate its script/prompt"""
        db = DatabaseManager()
        job = db.get_job(job_id)
        if not job or job['status'] != JobStatus.PENDING.value:
            return

        try:
            if job['source_type'] == 'PROMPT':
                scripts = self.generate_batch_scripts(job['source_input'], count=1)
                if scripts:
                    s = scripts[0]
                    db.update_job(
                        job_id,
                        title=s.get('title', ''),
                        voiceover_text=s.get('voiceover_text', ''),
                        veo_prompt=s.get('veo_prompt', ''),
                        tags=s.get('tags', []),
                        status=JobStatus.SCRIPTED.value
                    )
                else:
                    db.update_job(job_id, status=JobStatus.FAILED.value, error_msg="Không sinh được kịch bản")
        except Exception as e:
            logger.exception(f"Lỗi xử lý Script Job #{job_id}: {e}")
            db.update_job(job_id, status=JobStatus.FAILED.value, error_msg=str(e))

import json
import logging
from google import genai
from config.settings import GEMINI_API_KEY
from config.prompt_templates import BATCH_SCRIPT_GEN_PROMPT, BATCH_SCRIPT_GEN_WITH_CONTEXT_PROMPT, VIDEO_CLONE_REMAKE_PROMPT
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

    def _generate_fallback_scripts(self, topic: str, count: int = 10, keep_context: bool = True, custom_context: str = "") -> list:
        """Generate smart fallback scripts when GEMINI_API_KEY is not configured"""
        scripts = []
        context_prefix = f" [{custom_context}]" if custom_context else ""
        for i in range(1, count + 1):
            episode_title = f"Tập {i}: {topic}" if keep_context else f"{topic} - Mẹo Hay #{i}"
            scripts.append({
                "title": episode_title,
                "hook": f"Tập {i}: Bạn có biết bí mật này về {topic} chưa?",
                "voiceover_text": f"Tập {i}: Khám phá ngay bí quyết đỉnh cao về {topic}{context_prefix} năm 2026. Hãy theo dõi tập tiếp theo!",
                "veo_prompt": f"Continuous 9:16 vertical 4k cinematic shot, episode {i} of continuous series about {topic}, same consistent character and environment context{context_prefix}, dramatic lighting, hyper-realistic, 30fps",
                "tags": [f"#{topic.replace(' ', '')}", "#Shorts", f"#SeriesPart{i}", "#VeoStudio"]
            })
        return scripts

    def generate_batch_scripts(self, topic: str, count: int = 10, keep_context: bool = True, custom_context: str = "") -> list:
        """Generate a batch of 10s video scripts maintaining storyline & character context"""
        if not self.client:
            logger.info("Dùng Template Script Engine Fallback (Chưa nạp GEMINI_API_KEY)")
            return self._generate_fallback_scripts(topic, count, keep_context=keep_context, custom_context=custom_context)

        context_instruction = f"Mô tả nhân vật / bối cảnh cố định cần khóa context: '{custom_context}'" if custom_context else "Tự suy luận và cố định 1 mô tả nhân vật chính và bối cảnh không gian đặc trưng xuyên suốt cả chuỗi video."

        if keep_context:
            prompt = BATCH_SCRIPT_GEN_WITH_CONTEXT_PROMPT.format(topic=topic, count=count, context_instruction=context_instruction)
        else:
            prompt = BATCH_SCRIPT_GEN_PROMPT.format(topic=topic, count=count)

        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
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
            return self._generate_fallback_scripts(topic, count, keep_context=keep_context, custom_context=custom_context)

    def remake_script(self, transcript: str, vision_description: str, duration_sec: float = 10.0) -> dict:
        """Remake a cloned video transcript/description, preserving original duration and refining text slightly"""
        duration_int = max(int(round(duration_sec)), 3)
        clean_transcript = transcript.strip() if transcript else ""
        
        if not self.client:
            default_voiceover = clean_transcript if clean_transcript and len(clean_transcript) > 5 else "Khám phá nội dung ấn tượng nhất năm 2026!"
            return {
                "title": "TikTok Video Remake AI",
                "voiceover_text": default_voiceover,
                "veo_prompt": f"Continuous 9:16 vertical video shot, 4k resolution, cinematic lighting, duration {duration_int}s: {vision_description}",
                "tags": ["#Remake", "#Shorts", "#AI2026"]
            }

        prompt = VIDEO_CLONE_REMAKE_PROMPT.format(
            duration_sec=duration_int,
            transcript=clean_transcript or "Không có thoại",
            vision_description=vision_description or "Video ngắn ấn tượng"
        )

        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
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
            return json.loads(text.strip())
        except Exception as e:
            logger.error(f"Lỗi parse JSON remake script: {e}")
            default_voiceover = clean_transcript if clean_transcript and len(clean_transcript) > 5 else "Nội dung tinh chỉnh lôi cuốn hơn năm 2026!"
            return {
                "title": "TikTok Video Remake AI",
                "voiceover_text": default_voiceover,
                "veo_prompt": f"Continuous 9:16 vertical video shot, 4k resolution, duration {duration_int}s",
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

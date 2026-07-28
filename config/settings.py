import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Directory Paths
STORAGE_DIR = BASE_DIR / "storage"
DOWNLOADS_DIR = STORAGE_DIR / "downloads"
GENERATED_DIR = STORAGE_DIR / "generated"
FINAL_DIR = STORAGE_DIR / "final"
BROWSER_DATA_DIR = STORAGE_DIR / "browser_sessions"
DB_PATH = STORAGE_DIR / "jobs.db"

# Create directories if not exist
for folder in [STORAGE_DIR, DOWNLOADS_DIR, GENERATED_DIR, FINAL_DIR, BROWSER_DATA_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

# Processing & Multi-threading Config
TARGET_FPS = 30
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
DEFAULT_VIDEO_DURATION_SEC = 10

# Labs.google Agent & Generation Default Configs
DEFAULT_VEO_MODEL = os.getenv("DEFAULT_VEO_MODEL", "veo-3.1-lite-generate-preview")
DEFAULT_IMAGE_MODEL = os.getenv("DEFAULT_IMAGE_MODEL", "imagen-3.0-generate-002")
DEFAULT_ASPECT_RATIO = os.getenv("DEFAULT_ASPECT_RATIO", "9:16")
DEFAULT_LABS_QUALITY = os.getenv("DEFAULT_LABS_QUALITY", "1080p")
DEFAULT_ADD_SUBTITLE = os.getenv("DEFAULT_ADD_SUBTITLE", "true").lower() == "true"
DEFAULT_ADD_VOICEOVER = os.getenv("DEFAULT_ADD_VOICEOVER", "true").lower() == "true"
REQUIRE_CONFIRMATION = os.getenv("REQUIRE_CONFIRMATION", "false").lower() == "true"

# Veo generation options (matching Labs.google UI)
try:
    DEFAULT_VEO_DURATION = int(os.getenv("DEFAULT_VEO_DURATION", "8"))
    if DEFAULT_VEO_DURATION not in (4, 6, 8):
        DEFAULT_VEO_DURATION = 8
except ValueError:
    DEFAULT_VEO_DURATION = 8

try:
    DEFAULT_VEO_VARIANTS = int(os.getenv("DEFAULT_VEO_VARIANTS", "1"))
    if DEFAULT_VEO_VARIANTS not in (1, 2, 3, 4):
        DEFAULT_VEO_VARIANTS = 1
except ValueError:
    DEFAULT_VEO_VARIANTS = 1

# If True: only use the chosen DEFAULT_VEO_MODEL, no fallback to other models (matches Labs.google exact model selection)
DEFAULT_VEO_STRICT_MODEL = os.getenv("DEFAULT_VEO_STRICT_MODEL", "true").lower() == "true"

# Default video generation engine ('labs' for Playwright Chrome automation, 'veo_api' for official Gemini API)
DEFAULT_GEN_ENGINE = os.getenv("DEFAULT_GEN_ENGINE", "labs")

try:
    MAX_CONCURRENT_VEO_JOBS = int(os.getenv("MAX_CONCURRENT_VEO_JOBS", "5"))
except ValueError:
    MAX_CONCURRENT_VEO_JOBS = 5

try:
    MAX_CONCURRENT_LABS_JOBS = int(os.getenv("MAX_CONCURRENT_LABS_JOBS", "3"))
except ValueError:
    MAX_CONCURRENT_LABS_JOBS = 3

MAX_CONCURRENT_POST_JOBS = 2     # Maximum parallel browser uploads (avoid rate limit)
MAX_CONCURRENT_PROCESSING = 4    # Maximum parallel FFmpeg video renders

custom_dir = os.getenv("CUSTOM_STORAGE_DIR", "")
if custom_dir and Path(custom_dir).exists():
    FINAL_DIR = Path(custom_dir)

# Social Media Login Context Paths
FACEBOOK_SESSION_DIR = BROWSER_DATA_DIR / "facebook"  # legacy default profile
FACEBOOK_PROFILES_DIR = BROWSER_DATA_DIR / "facebook_profiles"  # multi-profile storage
FACEBOOK_PROFILES_CONFIG = STORAGE_DIR / "fb_profiles.json"     # profile metadata
TIKTOK_SESSION_DIR = BROWSER_DATA_DIR / "tiktok"
TIKTOK_PROFILES_DIR = BROWSER_DATA_DIR / "tiktok_profiles"
TIKTOK_PROFILES_CONFIG = STORAGE_DIR / "tiktok_profiles.json"
X_SESSION_DIR = BROWSER_DATA_DIR / "x"
LABS_GOOGLE_SESSION_DIR = BROWSER_DATA_DIR / "labs_google"

for sess_folder in [FACEBOOK_SESSION_DIR, FACEBOOK_PROFILES_DIR, TIKTOK_SESSION_DIR, TIKTOK_PROFILES_DIR, X_SESSION_DIR, LABS_GOOGLE_SESSION_DIR]:
    sess_folder.mkdir(parents=True, exist_ok=True)

def reload_settings():
    global GEMINI_API_KEY, MAX_CONCURRENT_VEO_JOBS, MAX_CONCURRENT_LABS_JOBS, FINAL_DIR, STORAGE_DIR
    global DEFAULT_VEO_MODEL, DEFAULT_IMAGE_MODEL, DEFAULT_ASPECT_RATIO, REQUIRE_CONFIRMATION
    global DEFAULT_VEO_DURATION, DEFAULT_VEO_VARIANTS, DEFAULT_VEO_STRICT_MODEL
    load_dotenv(BASE_DIR / ".env", override=True)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    DEFAULT_VEO_MODEL = os.getenv("DEFAULT_VEO_MODEL", "veo-3.1-lite-generate-preview")
    DEFAULT_IMAGE_MODEL = os.getenv("DEFAULT_IMAGE_MODEL", "imagen-3.0-generate-002")
    DEFAULT_ASPECT_RATIO = os.getenv("DEFAULT_ASPECT_RATIO", "9:16")
    REQUIRE_CONFIRMATION = os.getenv("REQUIRE_CONFIRMATION", "false").lower() == "true"
    DEFAULT_VEO_STRICT_MODEL = os.getenv("DEFAULT_VEO_STRICT_MODEL", "true").lower() == "true"
    try:
        DEFAULT_VEO_DURATION = int(os.getenv("DEFAULT_VEO_DURATION", "8"))
        if DEFAULT_VEO_DURATION not in (4, 6, 8): DEFAULT_VEO_DURATION = 8
    except ValueError:
        DEFAULT_VEO_DURATION = 8
    try:
        DEFAULT_VEO_VARIANTS = int(os.getenv("DEFAULT_VEO_VARIANTS", "1"))
        if DEFAULT_VEO_VARIANTS not in (1, 2, 3, 4): DEFAULT_VEO_VARIANTS = 1
    except ValueError:
        DEFAULT_VEO_VARIANTS = 1
    try:
        MAX_CONCURRENT_VEO_JOBS = int(os.getenv("MAX_CONCURRENT_VEO_JOBS", "5"))
    except ValueError:
        MAX_CONCURRENT_VEO_JOBS = 5
    try:
        MAX_CONCURRENT_LABS_JOBS = int(os.getenv("MAX_CONCURRENT_LABS_JOBS", "3"))
    except ValueError:
        MAX_CONCURRENT_LABS_JOBS = 3

    custom_storage = os.getenv("CUSTOM_STORAGE_DIR", "")
    if custom_storage:
        p = Path(custom_storage)
        p.mkdir(parents=True, exist_ok=True)
        FINAL_DIR = p
    else:
        FINAL_DIR = STORAGE_DIR / "final"
        FINAL_DIR.mkdir(parents=True, exist_ok=True)

def update_env_settings(
    api_key: str = None,
    max_workers: int = None,
    max_labs_workers: int = None,
    storage_dir: str = None,
    veo_model: str = None,
    image_model: str = None,
    aspect_ratio: str = None,
    require_confirmation: bool = None,
    veo_duration: int = None,
    veo_variants: int = None,
    veo_strict_model: bool = None,
    gen_engine: str = None,
    **kwargs
):
    env_path = BASE_DIR / ".env"
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()

    if api_key is not None:
        env_vars["GEMINI_API_KEY"] = api_key.strip()
        os.environ["GEMINI_API_KEY"] = api_key.strip()

    if max_workers is not None:
        env_vars["MAX_CONCURRENT_VEO_JOBS"] = str(max_workers)
        os.environ["MAX_CONCURRENT_VEO_JOBS"] = str(max_workers)

    if max_labs_workers is not None:
        env_vars["MAX_CONCURRENT_LABS_JOBS"] = str(max_labs_workers)
        os.environ["MAX_CONCURRENT_LABS_JOBS"] = str(max_labs_workers)

    if gen_engine is not None and gen_engine.strip():
        env_vars["DEFAULT_GEN_ENGINE"] = gen_engine.strip()
        os.environ["DEFAULT_GEN_ENGINE"] = gen_engine.strip()

    if storage_dir is not None and storage_dir.strip():
        env_vars["CUSTOM_STORAGE_DIR"] = storage_dir.strip()
        os.environ["CUSTOM_STORAGE_DIR"] = storage_dir.strip()

    if veo_model is not None:
        env_vars["DEFAULT_VEO_MODEL"] = veo_model.strip()
        os.environ["DEFAULT_VEO_MODEL"] = veo_model.strip()

    if image_model is not None:
        env_vars["DEFAULT_IMAGE_MODEL"] = image_model.strip()
        os.environ["DEFAULT_IMAGE_MODEL"] = image_model.strip()

    if aspect_ratio is not None:
        env_vars["DEFAULT_ASPECT_RATIO"] = aspect_ratio.strip()
        os.environ["DEFAULT_ASPECT_RATIO"] = aspect_ratio.strip()

    if require_confirmation is not None:
        val_str = "true" if require_confirmation else "false"
        env_vars["REQUIRE_CONFIRMATION"] = val_str
        os.environ["REQUIRE_CONFIRMATION"] = val_str

    if veo_duration is not None:
        env_vars["DEFAULT_VEO_DURATION"] = str(veo_duration)
        os.environ["DEFAULT_VEO_DURATION"] = str(veo_duration)

    if veo_variants is not None:
        env_vars["DEFAULT_VEO_VARIANTS"] = str(veo_variants)
        os.environ["DEFAULT_VEO_VARIANTS"] = str(veo_variants)

    if veo_strict_model is not None:
        val_str = "true" if veo_strict_model else "false"
        env_vars["DEFAULT_VEO_STRICT_MODEL"] = val_str
        os.environ["DEFAULT_VEO_STRICT_MODEL"] = val_str

    # Handle arbitrary extra env vars via **kwargs (e.g. FB_PAGE_ID, FB_PAGE_ACCESS_TOKEN)
    for k, v in kwargs.items():
        if v is not None:
            env_vars[k] = str(v).strip()
            os.environ[k] = str(v).strip()

    with open(env_path, "w", encoding="utf-8") as f:
        for k, v in env_vars.items():
            f.write(f"{k}={v}\n")

    reload_settings()

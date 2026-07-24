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

MAX_CONCURRENT_VEO_JOBS = 5      # Maximum parallel Veo API generations
MAX_CONCURRENT_POST_JOBS = 2     # Maximum parallel browser uploads (avoid rate limit)
MAX_CONCURRENT_PROCESSING = 4    # Maximum parallel FFmpeg video renders

# Social Media Login Context Paths
FACEBOOK_SESSION_DIR = BROWSER_DATA_DIR / "facebook"
TIKTOK_SESSION_DIR = BROWSER_DATA_DIR / "tiktok"
X_SESSION_DIR = BROWSER_DATA_DIR / "x"

for sess_folder in [FACEBOOK_SESSION_DIR, TIKTOK_SESSION_DIR, X_SESSION_DIR]:
    sess_folder.mkdir(parents=True, exist_ok=True)

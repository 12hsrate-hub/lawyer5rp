import os
import sys
from pathlib import Path

import uvicorn

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ogp_web.env import load_web_env


load_web_env()

if __name__ == "__main__":
    host = os.getenv("OGP_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("OGP_WEB_PORT", os.getenv("PORT", "8000")))
    reload_enabled = os.getenv("OGP_WEB_RELOAD", "true").lower() in {"1", "true", "yes", "on"}
    uvicorn.run("ogp_web.app:app", host=host, port=port, reload=reload_enabled)
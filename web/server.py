from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ogp_web.env import load_web_env


def main() -> None:
    load_web_env()

    parser = argparse.ArgumentParser(description="Production launcher for OGP Builder Web")
    parser.add_argument("--host", default=os.getenv("OGP_WEB_HOST", "0.0.0.0"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("OGP_WEB_PORT", os.getenv("PORT", "8000"))),
    )
    args = parser.parse_args()

    uvicorn.run(
        "ogp_web.app:app",
        host=args.host,
        port=args.port,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()

"""
VayuSutra — Canonical FastAPI entrypoint.

Run with:
    uvicorn main:app --host 0.0.0.0 --port 8000
or:
    python main.py
"""
import os
import sys

# Ensure the repo root is on sys.path when launched from elsewhere.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn  # noqa: E402
from vayusutra_apix.api.main import app  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        workers=int(os.environ.get("WORKERS", "1")),
    )

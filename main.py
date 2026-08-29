"""
Workspace-root FastAPI entrypoint shim so preview tooling can auto-detect `app`.

The real application lives in the SIH26056 repository; this shim just points at it
so a generic entrypoint scan finds `app` in a default location.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.join(_HERE, "SIH26056")
if os.path.isdir(_REPO):
    sys.path.insert(0, _REPO)

from vayusutra_apix.api.main import app  # noqa: E402

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))

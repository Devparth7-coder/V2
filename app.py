"""
Workspace-root FastAPI entrypoint so preview/serverless tooling can auto-detect `app`.

The `vayusutra_apix` package can live in two layouts:
  (a) as a SIBLING of this file — i.e. the project files were pasted OUTSIDE any
      `SIH26056/` folder, so `vayusutra_apix/` sits right here next to this file; or
  (b) inside a `SIH26056/` subfolder (the original repo layout).

This shim probes both and points sys.path at whichever contains `vayusutra_apix`,
so `app` resolves correctly no matter how the files were arranged.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def _find_package_root() -> str:
    candidates = [
        _HERE,                                   # (a) files outside the SIH26056 folder
        os.path.join(_HERE, "SIH26056"),          # (b) original nested repo layout
    ]
    for candidate in candidates:
        if os.path.isdir(os.path.join(candidate, "vayusutra_apix")):
            return candidate
    return _HERE


_REPO = _find_package_root()
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from vayusutra_apix.api.main import app  # noqa: E402

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
    )

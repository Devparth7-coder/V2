"""
Pytest configuration: run the test suite against an isolated, freshly-seeded database
so that every test run is deterministic and independent of any persisted dev data.
Set VAYUSUTRA_DB_PATH before the FastAPI app is imported.
"""
import os
import tempfile

# Isolated DB file inside a temp dir (removed/recreated each session for determinism).
_tmpdir = tempfile.mkdtemp(prefix="vayusutra_test_")
_db_file = os.path.join(_tmpdir, "vayusutra_airfare.db")
if os.path.exists(_db_file):
    os.remove(_db_file)

os.environ["VAYUSUTRA_DB_PATH"] = _db_file

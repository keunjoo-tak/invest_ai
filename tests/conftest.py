import os
import tempfile
from pathlib import Path

workspace_tmp = Path(__file__).resolve().parents[1] / ".pytest_tmp"
workspace_tmp.mkdir(exist_ok=True)
for key in ("TMP", "TEMP", "TMPDIR"):
    os.environ.setdefault(key, str(workspace_tmp))
tempfile.tempdir = str(workspace_tmp)
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("GEMINI_ENABLED", "false")

from app.core.config import get_settings

get_settings.cache_clear()

"""Catch syntax errors in the embedded login page JavaScript before deployment."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


def test_inline_login_script_is_valid_javascript():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    source = (Path(__file__).resolve().parents[1] / "web" / "app.py").read_text(encoding="utf-8")
    script = re.search(r"<script>(.*?)</script>", source, re.DOTALL)
    assert script, "Missing inline application script"
    code = script.group(1).replace("__SUPABASE_URL_JSON__", '""').replace("__SUPABASE_KEY_JSON__", '""')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "inline-login.js"
        path.write_text(code, encoding="utf-8")
        result = subprocess.run([node, "--check", str(path)], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr

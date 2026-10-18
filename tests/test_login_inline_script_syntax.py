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
    from web.app import home
    from unittest.mock import patch
    with patch.dict("os.environ", {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_ANON_KEY": "test-public-key"}):
        response = home()
    script = re.search(r"<script>(.*?)</script>", response.body.decode("utf-8"), re.DOTALL)
    assert script, "Missing inline application script"
    code = script.group(1).replace("__SUPABASE_URL_JSON__", '""').replace("__SUPABASE_KEY_JSON__", '""')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "inline-login.js"
        path.write_text(code, encoding="utf-8")
        result = subprocess.run([node, "--check", str(path)], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr

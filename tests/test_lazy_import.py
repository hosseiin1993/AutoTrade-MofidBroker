import subprocess
import sys


def test_importing_autotrade_does_not_load_playwright() -> None:
    script = """
import sys
import autotrade
loaded = [name for name in sys.modules if name == "playwright" or name.startswith("playwright.")]
assert loaded == [], loaded
from autotrade.browser import sync_playwright
assert "playwright.sync_api" in sys.modules
assert callable(sync_playwright)
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

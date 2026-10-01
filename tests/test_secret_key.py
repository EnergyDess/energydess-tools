"""На проде (FLY_APP_NAME) без своего SECRET_KEY auth не импортируется;
со своим ключом и вне прода — импортируется (обратный случай)."""
import os
import subprocess
import sys


def _импорт(окружение: dict) -> int:
    env = {k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "FLY_APP_NAME")}
    env.update(окружение)
    return subprocess.run([sys.executable, "-c", "import auth"], env=env,
                          capture_output=True).returncode


def test_на_проде_без_ключа_не_стартует():
    assert _импорт({"FLY_APP_NAME": "energydess-tools"}) != 0


def test_на_проде_со_своим_ключом_стартует():
    assert _импорт({"FLY_APP_NAME": "energydess-tools", "SECRET_KEY": "x" * 40}) == 0


def test_вне_прода_без_ключа_стартует():
    assert _импорт({}) == 0

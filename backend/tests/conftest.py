import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATA_ENCRYPTION_KEY", base64.b64encode(b"t" * 32).decode())
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN_abcdefghijklmnopqrstuvwxyz")

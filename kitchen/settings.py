import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)


def data_dir():
    path = Path(os.environ.get("KITCHEN_DATA_DIR", str(ROOT / "data"))).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def live_available():
    return os.environ.get("KITCHEN_ENABLE_LIVE", "0") == "1" and bool(os.environ.get("DEEPSEEK_API_KEY"))


def require_live(consent: bool):
    if not live_available():
        raise PermissionError("真实 API 调用未开启。需在本地配置密钥并设置 KITCHEN_ENABLE_LIVE=1。")
    if not consent:
        raise PermissionError("本次调用尚未得到明确确认。")

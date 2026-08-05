"""
鸿讯 HONGXUN · PDF 下载配置
版本 1.0.0

独立配置文件 data/pdf_config.json（不修改 HONGXUN-LOCKED 的 config_manager.py）。

字段：
  pdf_dir          PDF 保存目录（默认 ~/Downloads/HONGXUN-PDF）
  enable_scihub    是否启用 Sci-Hub 兜底（默认 False，法律风险由用户决定）
  unpaywall_email  Unpaywall 邮箱（填写可提高 OA 命中率，可选）
"""

import json
import os

from .config_manager import DATA_DIR

PDF_CONFIG_FILE = os.path.join(DATA_DIR, "pdf_config.json")

_DEFAULT = {
    "pdf_dir": os.path.join(os.path.expanduser("~"), "Downloads", "HONGXUN-PDF"),
    "enable_scihub": False,
    "unpaywall_email": "691678079@qq.com",
}


def load_pdf_config() -> dict:
    """读取配置，缺失键用默认值补齐。文件不存在返回默认值。"""
    cfg = dict(_DEFAULT)
    if not os.path.exists(PDF_CONFIG_FILE):
        return cfg
    try:
        with open(PDF_CONFIG_FILE, encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            cfg.update(saved)
    except Exception:
        pass
    return cfg


def save_pdf_config(cfg: dict) -> None:
    """原子写入配置（os.replace 防写坏）。"""
    os.makedirs(os.path.dirname(PDF_CONFIG_FILE), exist_ok=True)
    tmp = PDF_CONFIG_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, PDF_CONFIG_FILE)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        raise

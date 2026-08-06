"""自动备份：处理前把原文件复制为带时间戳的 .bak。"""

import os
import shutil
from datetime import datetime


def create_backup(path: str) -> str | None:
    """把 path 复制为同目录下 `原文件名_YYYYMMDD_HHMMSS.bak`。

    返回备份路径；失败返回 None（不阻断主流程）。
    """
    try:
        if not path or not os.path.exists(path):
            return None
        directory = os.path.dirname(os.path.abspath(path))
        base = os.path.basename(path)
        stem, ext = os.path.splitext(base)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(directory, f"{stem}_{stamp}.bak")
        shutil.copy2(path, backup_path)
        return backup_path
    except Exception:
        return None

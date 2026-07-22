# HONGXUN-LOCKED — 此文件受保护，修改需密码验证
# 请通过程序界面解锁后编辑
"""
鸿讯 HONGXUN · 底层代码保护（完整性校验 + 密码验证）
版本 1.0.0
"""

import hashlib
import json
import os
import sys
import re
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
MANIFEST_FILE = os.path.join(DATA_DIR, "code_manifest.json")

# 受保护的文件（相对项目根目录）
PROTECTED_FILES = [
    "gui_app.py",
    "scheduler_daemon.py",
    "core/__init__.py",
    "core/abstract.py",
    "core/code_protector.py",
    "core/config_manager.py",
    "core/coupon_manager.py",
    "core/email_sender.py",
    "core/engine.py",
    "core/search.py",
    "core/session.py",
]

# 解锁密码（非本机设备编辑代码时需输入）
UNLOCK_PASSWORD = "XHcxy1993.0827"

# 本机授权 MAC（免密码）— eno1 / eth0 MAC 地址
AUTHORIZED_MAC = "ac:de:48:00:11:22"


def _read_file_hash(filepath: str) -> Optional[str]:
    """计算单个文件的 SHA256"""
    abs_path = os.path.join(BASE_DIR, filepath)
    if not os.path.exists(abs_path):
        return None
    try:
        with open(abs_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def build_manifest() -> dict:
    """构建当前文件的哈希清单"""
    manifest = {}
    for rel_path in PROTECTED_FILES:
        h = _read_file_hash(rel_path)
        if h:
            manifest[rel_path] = h
    return manifest


def save_manifest(manifest: dict = None) -> dict:
    """保存哈希清单到文件"""
    if manifest is None:
        manifest = build_manifest()
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


def load_manifest() -> dict:
    """加载存储的哈希清单"""
    if not os.path.exists(MANIFEST_FILE):
        return {}
    try:
        with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def check_integrity() -> dict:
    """检查文件完整性，返回 {文件: 状态}"""
    stored = load_manifest()
    current = build_manifest()
    result = {}
    for rel_path in PROTECTED_FILES:
        old = stored.get(rel_path)
        new = current.get(rel_path)
        if old is None and new is None:
            result[rel_path] = "missing"
        elif old is None:
            result[rel_path] = "new"
        elif new is None:
            result[rel_path] = "deleted"
        elif old != new:
            result[rel_path] = "modified"
        else:
            result[rel_path] = "ok"
    return result


def is_code_tampered() -> bool:
    """是否有受保护文件被修改"""
    status = check_integrity()
    return any(v not in ("ok", "missing") for v in status.values())


def verify_password(password: str) -> bool:
    """验证解锁密码"""
    return password == UNLOCK_PASSWORD


def authorize_modification(password: str = "") -> bool:
    """授权代码修改：验证密码或检测到本机 MAC 则自动通过

    本机判断逻辑（二选一通过即视为本机）：
    1. 当前机器 MAC 等于硬编码的 AUTHORIZED_MAC（开发本机）
    2. 当前机器 MAC 等于 license.json 中绑定的 MAC（已激活的用户本机）

    非本机设备必须输入密码 UNLOCK_PASSWORD 才能解锁。
    """
    # 如果提供了密码，优先验证
    if password and verify_password(password):
        return True

    from .coupon_manager import get_current_mac, load_license
    current_mac = get_current_mac()
    if current_mac == "unknown":
        return False

    # 检查是否开发本机（硬编码 MAC）
    if current_mac == AUTHORIZED_MAC:
        return True

    # 检查是否已激活的许可设备（license 绑定的 MAC）
    lic = load_license()
    bound_mac = lic.get("mac", "")
    if bound_mac and bound_mac == current_mac:
        return True

    return False


# ── PY文件锁定（禁止直接编辑/打开）───────────────────────────
# 通过在受保护文件顶部插入校验头，防止其他人员直接双击运行或编辑

_LOCK_MARKER = "# HONGXUN-LOCKED"
_LOCK_HEADER = (
    '# HONGXUN-LOCKED — 此文件受保护，修改需密码验证\n'
    '# 请通过程序界面解锁后编辑\n'
)


def is_file_locked(rel_path: str) -> bool:
    """检查文件是否被锁定（顶部包含锁定标记）"""
    abs_path = os.path.join(BASE_DIR, rel_path)
    if not os.path.exists(abs_path):
        return False
    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            first_line = f.readline()
            return _LOCK_MARKER in first_line
    except Exception:
        return False


def lock_file(rel_path: str) -> bool:
    """锁定单个文件：在顶部插入保护头"""
    abs_path = os.path.join(BASE_DIR, rel_path)
    if not os.path.exists(abs_path):
        return False
    if is_file_locked(rel_path):
        return True  # 已锁定
    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(_LOCK_HEADER + content)
        return True
    except Exception:
        return False


def unlock_file(rel_path: str, password: str = "") -> bool:
    """解锁单个文件：移除保护头（需密码或本机 MAC）"""
    if not authorize_modification(password):
        return False
    abs_path = os.path.join(BASE_DIR, rel_path)
    if not os.path.exists(abs_path):
        return False
    if not is_file_locked(rel_path):
        return True  # 未锁定
    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        # 移除锁定头行
        while lines and _LOCK_MARKER in lines[0]:
            lines.pop(0)
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        return True
    except Exception:
        return False


def lock_all_protected_files() -> dict:
    """锁定所有受保护文件，返回 {文件: 成功/失败}"""
    results = {}
    for rel_path in PROTECTED_FILES:
        results[rel_path] = lock_file(rel_path)
    return results


def unlock_all_protected_files(password: str = "") -> dict:
    """解锁所有受保护文件，返回 {文件: 成功/失败}"""
    if not authorize_modification(password):
        return {p: False for p in PROTECTED_FILES}
    results = {}
    for rel_path in PROTECTED_FILES:
        results[rel_path] = unlock_file(rel_path, password)
    return results

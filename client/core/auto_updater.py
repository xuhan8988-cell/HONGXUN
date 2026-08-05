# HONGXUN-LOCKED — 此文件受保护，修改需密码验证
# 请通过程序界面解锁后编辑
"""
鸿讯 HONGXUN · 自动更新模块
版本 1.0.0

从 Gitee 发布页检查新版本 → 推送通知 → 静默下载 → 替换旧文件。
"""
import json
import os
import sys
import platform
import subprocess
import tempfile
import shutil
import zipfile
import tarfile
import time
from datetime import datetime
from typing import Optional

import requests

# ── 仓库配置 ────────────────────────────────────────────
_GITHUB_OWNER = "xuhan8988-cell"
_GITHUB_REPO = "HONGXUN"
_GITHUB_RELEASE_URL = f"https://api.github.com/repos/{_GITHUB_OWNER}/{_GITHUB_REPO}/releases/latest"
# 公告文件 — 修改此 URL 指向的 JSON 即可向所有用户推送弹窗
# 你需要在 GitHub 仓库根目录维护一个 notice.json，格式见 fetch_notice()
_GITHUB_NOTICE_URL = f"https://api.github.com/repos/{_GITHUB_OWNER}/{_GITHUB_REPO}/contents/notice.json"

# 当前版本（与 gui/theme.py 同步，由 init() 注入覆盖）
CURRENT_VERSION = "0.0.0"

# 更新状态标记文件（存放于 data 目录）
_UPDATE_MARK_FILE = None  # 在 init 时根据 BASE_DIR 设定


def init(base_dir: str, version: str = "0.0.0"):
    """初始化更新模块（需传入 BASE_DIR）"""
    global _UPDATE_MARK_FILE, CURRENT_VERSION
    CURRENT_VERSION = version
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    _UPDATE_MARK_FILE = os.path.join(data_dir, "update_marker.json")


def _is_redhat_family() -> bool:
    """判断是否基于 RPM 的 Linux"""
    if sys.platform != "linux":
        return False
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            content = f.read().lower()
        return any(x in content for x in ("rhel", "centos", "fedora", "rocky", "almalinux"))
    except Exception:
        return False


def _is_debian_family() -> bool:
    """判断是否基于 Debian 的 Linux"""
    if sys.platform != "linux":
        return False
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            content = f.read().lower()
        return any(x in content for x in ("debian", "ubuntu", "mint", "kalilinux"))
    except Exception:
        return False


def _get_platform_key() -> str:
    """返回平台标识：macos / windows / linux-rpm / linux-deb"""
    system = platform.system()
    if system == "Darwin":
        return "macos"
    elif system == "Windows":
        return "windows"
    elif system == "Linux":
        if _is_redhat_family():
            return "linux-rpm"
        elif _is_debian_family():
            return "linux-deb"
        return "linux"  # fallback
    return system.lower()


def _get_asset_filename() -> str:
    """根据当前平台返回要下载的发布包文件名"""
    key = _get_platform_key()
    mapping = {
        "macos":     "HONGXUN-macos.zip",
        "windows":   "HONGXUN-windows.zip",
        "linux-rpm": "HONGXUN-linux-rpm.tar.gz",
        "linux-deb": "HONGXUN-linux-deb.tar.gz",
        "linux":     "HONGXUN-linux.tar.gz",
    }
    return mapping.get(key, "")


def _load_update_marker() -> dict:
    """读取更新标记"""
    if not _UPDATE_MARK_FILE or not os.path.exists(_UPDATE_MARK_FILE):
        return {"notified_versions": [], "last_check": None}
    try:
        with open(_UPDATE_MARK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"notified_versions": [], "last_check": None}


def _save_update_marker(marker: dict):
    """保存更新标记"""
    if not _UPDATE_MARK_FILE:
        return
    try:
        with open(_UPDATE_MARK_FILE, "w", encoding="utf-8") as f:
            json.dump(marker, f, indent=2)
    except Exception:
        pass


def _parse_version(v: str) -> tuple:
    """安全拆分版本号用于比较"""
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0, 0, 0)


def fetch_notice() -> Optional[dict]:
    """
    从 GitHub 仓库读取 notice.json，返回公告内容。

    你需要在 GitHub 仓库根目录创建 notice.json，格式：
    {
      "msg_id": "20260728_001",
      "title": "重要更新 v2.0.0",
      "body": "新增功能：\\n1. DeepSeek AI 翻译\\n2. 重构礼品券系统\\n3. ..."
    }

    msg_id 递增即可让每个用户只弹窗一次。body 支持 \\n 换行。
    不需要公告时把 notice.json 内容置空 {} 或删除文件即可。
    """
    marker = _load_update_marker()
    try:
        resp = requests.get(_GITHUB_NOTICE_URL, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        # GitHub API 返回的 content 是 base64 编码
        import base64
        raw_content = data.get("content", "")
        if not raw_content:
            return None
        raw = base64.b64decode(raw_content).decode("utf-8")
        notice = json.loads(raw)
        if not notice or not isinstance(notice, dict):
            return None
        msg_id = notice.get("msg_id", "")
        if not msg_id:
            return None
        # 已经弹过的不再弹
        if msg_id in marker.get("noticed_msg_ids", []):
            return None
        return notice
    except Exception:
        return None


def mark_notice_read(msg_id: str):
    """标记公告已读，不再重复弹窗"""
    marker = _load_update_marker()
    noticed = marker.get("noticed_msg_ids", [])
    if msg_id not in noticed:
        noticed.append(msg_id)
    marker["noticed_msg_ids"] = noticed
    _save_update_marker(marker)


def check_update(skip_notified: bool = False) -> Optional[dict]:
    """
    检查 GitHub 最新发布版本。
    返回 dict = {"version": str, "download_url": str, "body": str, "tag_name": str}
    skip_notified=True 则跳过已通知过的版本。
    """
    marker = _load_update_marker()
    notified_versions = marker.get("notified_versions", [])
    if skip_notified and CURRENT_VERSION in notified_versions:
        return None

    try:
        resp = requests.get(_GITHUB_RELEASE_URL, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()

        tag = data.get("tag_name", "")
        version = tag.lstrip("v") if tag else ""
        if not version:
            return None
        if _parse_version(version) <= _parse_version(CURRENT_VERSION):
            return None
        if skip_notified and version in notified_versions:
            return None

        # 匹配当前平台的发布附件
        asset_filename = _get_asset_filename()
        download_url = ""
        for asset in data.get("assets", []):
            if asset.get("name") == asset_filename:
                download_url = asset.get("browser_download_url", "")
                break

        if not download_url:
            # fallback：用仓库源码 zip
            download_url = data.get("zipball_url", "")
            if not download_url:
                download_url = f"https://github.com/{_GITHUB_OWNER}/{_GITHUB_REPO}/archive/refs/tags/{tag}.zip"

        result = {
            "version": version,
            "tag_name": tag,
            "download_url": download_url,
            "body": data.get("body", "暂无更新说明"),
        }
        return result if download_url else None
    except Exception:
        return None


def skip_current_version():
    """标记当前版本已通知过（用户选择跳过），不再重复推送"""
    marker = _load_update_marker()
    notified = marker.get("notified_versions", [])
    if CURRENT_VERSION not in notified:
        notified.append(CURRENT_VERSION)
    marker["notified_versions"] = notified
    _save_update_marker(marker)


def has_upgrade_file() -> bool:
    """检查是否有已下载的更新包"""
    if not _UPDATE_MARK_FILE:
        return False
    marker = _load_update_marker()
    pending = marker.get("pending_upgrade", "")
    return bool(pending and os.path.exists(pending))


def download_update(info: dict, progress_callback=None) -> Optional[str]:
    """
    下载更新包到临时目录。
    返回本地文件路径，失败返回 None。
    progress_callback(received, total) 可选。
    """
    url = info.get("download_url", "")
    if not url:
        return None

    tmp_dir = tempfile.mkdtemp(prefix="hongxun_update_")
    ext = ".zip" if url.endswith(".zip") else ".tar.gz"
    local_path = os.path.join(tmp_dir, f"hongxun_update{ext}")

    try:
        resp = requests.get(url, stream=True, timeout=60)
        if resp.status_code != 200:
            return None

        total = int(resp.headers.get("content-length", 0))
        received = 0
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    received += len(chunk)
                    if progress_callback and total:
                        progress_callback(received, total)
        return local_path
    except Exception:
        return None


def _get_app_dir() -> str:
    """获取当前程序所在目录（打包后为 exe 目录，源码为项目根目录）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    # 源码模式：项目根目录
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_backup_dir() -> str:
    """获取备份目录"""
    app_dir = _get_app_dir()
    backup_dir = os.path.join(app_dir, "_backup")
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def _is_frozen() -> bool:
    """是否 PyInstaller 打包模式"""
    return getattr(sys, 'frozen', False)


def _backup_current(backup_dir: str) -> bool:
    """
    备份当前程序文件。
    打包模式：备份 _data/ 和 client/ 目录（如果存在）
    源码模式：备份 client/ 目录
    """
    app_dir = _get_app_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(backup_dir, f"v{CURRENT_VERSION}_{timestamp}")
    os.makedirs(dest, exist_ok=True)
    try:
        if _is_frozen():
            # 打包模式下备份 _data
            data_src = os.path.join(app_dir, "_data")
            if os.path.exists(data_src):
                shutil.copytree(data_src, os.path.join(dest, "_data"), dirs_exist_ok=True)
        else:
            # 源码模式备份整个 client/ 目录
            client_src = os.path.join(app_dir, "client")
            if os.path.exists(client_src):
                shutil.copytree(client_src, os.path.join(dest, "client"), dirs_exist_ok=True)
        return True
    except Exception:
        return False


def _extract_and_replace(package_path: str) -> tuple[bool, str]:
    """
    解压更新包并替换文件。
    返回 (成功, 错误信息)。
    """
    app_dir = _get_app_dir()
    try:
        # 先备份
        backup_dir = _get_backup_dir()
        _backup_current(backup_dir)

        if package_path.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(package_path, "r") as zf:
                zf.extractall(app_dir)
        elif package_path.endswith(".tar.gz") or package_path.endswith(".tgz"):
            with tarfile.open(package_path, "r:gz") as tf:
                tf.extractall(app_dir)
        else:
            return False, "不支持的更新包格式"

        return True, ""
    except Exception as e:
        return False, str(e)


def _restart_app():
    """重启应用程序（打包后替换为新版再启动）"""
    app_dir = _get_app_dir()
    if _is_frozen():
        if sys.platform == "darwin":
            # macOS .app bundle
            app_bundle = None
            for item in os.listdir(app_dir):
                if item.endswith(".app"):
                    app_bundle = os.path.join(app_dir, item)
                    break
            if app_bundle:
                subprocess.Popen(["open", app_bundle])
            else:
                # 可能是 exe 同级的可执行文件
                exe = os.path.join(app_dir, "HONGXUN")
                if os.path.exists(exe):
                    subprocess.Popen([exe])
        elif sys.platform == "win32":
            exe = os.path.join(app_dir, "HONGXUN.exe")
            if os.path.exists(exe):
                subprocess.Popen([exe])
        else:
            exe = os.path.join(app_dir, "HONGXUN")
            if os.path.exists(exe):
                subprocess.Popen([exe])
    else:
        # 源码模式：重新启动
        script = os.path.join(app_dir, "client", "gui_app.py")
        if os.path.exists(script):
            subprocess.Popen([sys.executable, script])

    sys.exit(0)


def apply_update(package_path: str, progress_callback=None) -> bool:
    """
    执行更新：解压替换文件 + 标记重启。
    GUI 调用此函数，完成后提示用户重启。
    返回 True 表示更新成功，需重启。
    """
    success, err = _extract_and_replace(package_path)
    if not success:
        return False

    # 标记版本
    marker = _load_update_marker()
    marker["last_update"] = datetime.now().isoformat()
    marker["pending_upgrade"] = ""  # 清除待升级标记
    _save_update_marker(marker)

    return True


def restart_and_update():
    """重启到新版本"""
    _restart_app()

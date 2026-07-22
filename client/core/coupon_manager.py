# HONGXUN-LOCKED — 此文件受保护，修改需密码验证
# 请通过程序界面解锁后编辑
"""
鸿讯 HONGXUN · 礼品券管理（永久有效 + HMAC 防伪）
版本 2.0.0
"""

import json
import os
import sys
import base64
import secrets
import hashlib
import hmac
from datetime import datetime, timedelta

import requests

# 路径处理：兼容 PyInstaller 打包（与 config_manager.py 保持一致）
if getattr(sys, 'frozen', False):
    _EXE_DIR = os.path.dirname(sys.executable)
    BASE_DIR = os.path.join(_EXE_DIR, "_data")
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
COUPON_STORAGE_FILE = os.path.join(DATA_DIR, "coupon_storage.json")
LICENSE_FILE = os.path.join(DATA_DIR, "license.json")
TRIAL_RECORD_FILE = os.path.join(DATA_DIR, "trial_record.json")

# 字符集：剔除易混淆字符 (0/O, 1/I/L)
CHARSET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
CHARSET_LEN = len(CHARSET)  # 32

# 礼品券有效期（天）— 永久有效
COUPON_VALID_DAYS = 99999

# HMAC 密钥（增强防伪）
_HMAC_SECRET = b"HONGXUN_V2_HMAC_SECRET_2026_XK7#mP9$"

# 网络时间 API
NTP_API_URLS = [
    "https://worldtimeapi.org/api/timezone/Etc/UTC",
    "https://timeapi.io/api/Time/current/zone?timeZone=UTC",
]

_NETWORK_TIME_CACHE = None


# Gitee 远程注册表 — 跨机兑换锁
_GITEE_OWNER = "mysterious-code-of-ancients"
_GITEE_REPO = "coupon-registry"
_GITEE_BRANCH = "master"
_GITEE_TOKEN = "5a813021b459eb4bb2901b6a37162533"
_GITEE_REGISTRY_PATH = "registry.json"


def _fetch_registry() -> tuple[dict | None, str]:
    """从 Gitee 获取远程注册表，返回 (registry_dict, sha)"""
    url = (f"https://gitee.com/api/v5/repos/{_GITEE_OWNER}/{_GITEE_REPO}"
           f"/contents/{_GITEE_REGISTRY_PATH}")
    try:
        resp = requests.get(url, params={
            "access_token": _GITEE_TOKEN, "ref": _GITEE_BRANCH,
        }, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            raw = base64.b64decode(data["content"]).decode("utf-8")
            return json.loads(raw), data.get("sha", "")
        return None, ""
    except Exception:
        return None, ""

def _get_network_time() -> datetime | None:
    """从网络获取当前 UTC 时间，失败返回 None"""
    for url in NTP_API_URLS:
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if "utc_datetime" in data:
                    return datetime.fromisoformat(data["utc_datetime"].replace("Z", ""))
                elif "dateTime" in data:
                    return datetime.fromisoformat(data["dateTime"].replace("Z", ""))
        except Exception:
            continue
    return None


def get_current_time() -> datetime:
    """获取当前时间（优先网络，失败抛异常）"""
    net = _get_network_time()
    if net is None:
        raise RuntimeError("无法连接到网络时间服务器，请检查网络连接后重试")
    return net


def _char_index(c: str) -> int:
    return CHARSET.index(c)


def _checksum(chars: list[str]) -> str:
    """对前22位计算校验和 → 2位校验字符（旧格式兼容）"""
    total = sum(_char_index(c) for c in chars)
    total %= CHARSET_LEN * CHARSET_LEN
    return CHARSET[total // CHARSET_LEN] + CHARSET[total % CHARSET_LEN]


def _hmac_signature(data_chars: list[str]) -> str:
    """对前 16 位数据计算 HMAC-SHA256 签名 → 8 位签名（新格式）"""
    data_str = ''.join(data_chars)
    sig = hmac.new(_HMAC_SECRET, data_str.encode('ascii'), hashlib.sha256).digest()
    # 取前 5 字节（40 bit）编码为 8 个 CHARSET 字符
    value = int.from_bytes(sig[:5], 'big')
    result = []
    for _ in range(8):
        result.append(CHARSET[value % CHARSET_LEN])
        value //= CHARSET_LEN
    return ''.join(result)


def generate_coupon() -> str:
    """
    生成一张 24 位礼品券（16 位随机数据 + 8 位 HMAC 签名）。
    HMAC 签名使用密钥，防破解、防伪造。
    """
    chars = [secrets.choice(CHARSET) for _ in range(16)]
    sig = _hmac_signature(chars)
    chars.extend(list(sig))
    return ''.join(chars)


def format_coupon(code: str) -> str:
    """24位码格式化为 XXXX-XXXX-XXXX-XXXX-XXXX-XXXX"""
    c = code.replace('-', '').upper()
    return '-'.join(c[i:i+4] for i in range(0, 24, 4))


def validate_coupon(code: str) -> tuple[bool, str]:
    """
    校验礼品券格式，支持两种格式：
    - 新格式（v2）：16 位数据 + 8 位 HMAC 签名
    - 旧格式（v1）：22 位数据 + 2 位校验和（向下兼容）
    返回 (是否合法, 格式化后的码)
    """
    raw = code.replace('-', '').replace(' ', '').upper()
    if len(raw) != 24:
        return False, raw
    if any(ch not in CHARSET for ch in raw):
        return False, raw
    chars = list(raw)

    # 尝试新格式：16 位数据 + 8 位 HMAC 签名
    data_chars = chars[:16]
    sig_chars = chars[16:]
    expected_sig = _hmac_signature(data_chars)
    if ''.join(sig_chars) == expected_sig:
        return True, raw

    # 尝试旧格式（向下兼容）：22 位数据 + 2 位校验和
    old_data_chars = chars[:22]
    old_sig_chars = chars[22:]
    expected_cs = _checksum(old_data_chars)
    if ''.join(old_sig_chars) == expected_cs:
        return True, raw

    return False, raw


def batch_generate(count: int = 1000) -> list[str]:
    """批量生成不重复的礼品券"""
    seen = set()
    result = []
    while len(result) < count:
        code = generate_coupon()
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result


def save_coupon_storage(codes: list[str]) -> None:
    """（已弃用）同步历史注册表：从 Gitee 拉取最新数据"""
    pass


def _push_registry(registry: dict, sha: str) -> bool:
    """将更新后的注册表推送到 Gitee，返回是否成功"""
    url = (f"https://gitee.com/api/v5/repos/{_GITEE_OWNER}/{_GITEE_REPO}"
           f"/contents/{_GITEE_REGISTRY_PATH}")
    content_b64 = base64.b64encode(
        json.dumps(registry, ensure_ascii=False).encode("utf-8")
    ).decode("utf-8")
    try:
        resp = requests.put(url, json={
            "access_token": _GITEE_TOKEN,
            "content": content_b64,
            "sha": sha,
            "message": f"兑换礼品券",
        }, timeout=10)
        return resp.status_code in (200, 201)
    except Exception:
        return False


def redeem_coupon(code: str) -> tuple[bool, str]:
    """兑换礼品券：Gitee 远程校验 → 检查跨机绑定 → 标记已使用 → 生成许可"""
    # 获取网络时间
    try:
        now = get_current_time()
    except RuntimeError as e:
        return False, str(e)

    valid, raw = validate_coupon(code)
    if not valid:
        return False, "礼品券格式无效"

    # 从 Gitee 获取远程注册表
    registry, sha = _fetch_registry()
    if registry is None:
        return False, "无法连接到礼品券服务器，请检查网络后重试"

    # 检查此券是否在注册表中（不在表中的券码为无效）
    if raw not in registry:
        return False, "该礼品券未在服务端注册，请联系管理员"

    current_mac = _get_mac()
    remote_entry = registry[raw]

    # 已绑定 -> 检查是否同一台机器
    if remote_entry is not None:
        bound_mac = remote_entry.get("bound_mac") if isinstance(remote_entry, dict) else None
        if bound_mac:
            if current_mac != "unknown" and current_mac != bound_mac:
                return False, "此礼品券已在其他设备上使用，无法再次兑换"
            # 同机器重兑：直接写本地 license，不需改远程
            _write_license(raw, current_mac, now)
            return True, "兑换成功！服务已永久激活，绑定本机设备"

    # 未绑定 -> 第一次兑换，在远程注册表中写入 MAC
    registry[raw] = {
        "bound_mac": current_mac,
        "used_at": now.isoformat(),
    }
    if not _push_registry(registry, sha):
        return False, "服务端注册失败，请稍后重试"

    # 更新本地存储
    _write_license(raw, current_mac, now)
    return True, "兑换成功！服务已永久激活，绑定本机设备"


def _write_license(raw: str, mac: str, now: datetime) -> None:
    """写入本地许可文件（永久有效）"""
    far_future = now + timedelta(days=COUPON_VALID_DAYS)
    license_data = {
        "activated": True,
        "mac": mac,
        "coupon": raw,
        "activated_at": now.isoformat(),
        "expires_at": far_future.isoformat(),
        "permanent": True,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LICENSE_FILE, 'w', encoding='utf-8') as f:
        json.dump(license_data, f, ensure_ascii=False, indent=2)


def _get_mac() -> str:
    """获取本机 MAC 地址"""
    import uuid
    mac_int = uuid.getnode()
    if (mac_int >> 40) % 2:
        return "unknown"
    mac = ':'.join(format((mac_int >> bits) & 0xff, '02x')
                    for bits in range(40, -1, -8))
    return mac


def get_current_mac() -> str:
    """公开获取本机 MAC 地址"""
    return _get_mac()


def load_license() -> dict:
    """加载许可信息"""
    if not os.path.exists(LICENSE_FILE):
        return {"activated": False, "mac": "", "coupon": "", "activated_at": None, "expires_at": None}
    try:
        with open(LICENSE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"activated": False, "mac": "", "coupon": "", "activated_at": None, "expires_at": None}


def is_activated() -> bool:
    """检查邮件推送是否已激活（含有效期检查，需联网确认时间）"""
    lic = load_license()
    if not lic.get("activated"):
        return False
    stored_mac = lic.get("mac", "")
    if not stored_mac:
        return False
    current_mac = _get_mac()
    if current_mac == "unknown":
        return False
    if stored_mac != current_mac:
        return False

    # 检查到期时间
    expires_at = lic.get("expires_at", "")
    if lic.get("permanent"):
        # 永久有效礼品券：无需联网确认，直接通过
        return True

    # 兼容旧许可证（没有 permanent 标记但 expires_at 远大于 activated_at）
    if expires_at:
        try:
            activated_at = lic.get("activated_at")
            if activated_at:
                act = datetime.fromisoformat(activated_at)
                exp = datetime.fromisoformat(expires_at)
                span_days = (exp - act).days
                if span_days >= 30000:
                    return True  # 有效期为 82+ 年，视为永久有效
        except Exception:
            pass

    # 非永久 → 需要联网确认是否已到期
    if expires_at:
        try:
            net_time = _get_network_time()
            if net_time is None:
                return False  # 无法联网确认，视为未激活
            exp = datetime.fromisoformat(expires_at)
            if exp < net_time:
                return False
        except Exception:
            return False

    return True


def get_remaining_days() -> int:
    """获取剩余天数"""
    lic = load_license()
    if not lic.get("activated"):
        return 0
    if lic.get("permanent"):
        return 99999
    expires_at = lic.get("expires_at", "")
    if not expires_at:
        return 0
    try:
        net_time = _get_network_time()
        if net_time is None:
            return 0
        exp = datetime.fromisoformat(expires_at)
        remaining = (exp - net_time).days
        return max(0, remaining)
    except Exception:
        return 0


def is_authorized_machine() -> bool:
    """判断是否为本机（许可绑定的机器）"""
    current = _get_mac()
    if current == "unknown":
        return False
    lic = load_license()
    if not lic.get("activated"):
        return False
    return current == lic.get("mac", "")


# ── 14 天免费试用 ────────────────────────────────────────────
TRIAL_DAYS = 14

# 试用期锚定文件列表（写入多个文件防清理）
_TRIAL_ANCHOR_FILES = [
    "trial_record.json",
    "app_config.json",
    "tasks.json",
    "scheduler_state.json",
]


def _get_anchor_path(filename: str) -> str:
    return os.path.join(DATA_DIR, filename)


def _write_trial_anchor(mac: str, started_at: str) -> None:
    """将试用起始时间和 MAC 写入多个锚定文件"""
    import json
    for fname in _TRIAL_ANCHOR_FILES:
        fpath = _get_anchor_path(fname)
        try:
            data = {}
            if os.path.exists(fpath):
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            data["_trial_mac"] = mac
            data["_trial_started"] = started_at
            with open(fpath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def _read_trial_from_anchors() -> tuple[str, str]:
    """
    从所有锚定文件中读取试用记录，返回 (mac, started_at)。
    取最早记录的 started_at（防止用户修改某个文件来延长试用）。
    如果所有锚定文件都被删除，返回 ("", "")。
    """
    import json
    candidates = []  # [(mac, started_at), ...]
    for fname in _TRIAL_ANCHOR_FILES:
        fpath = _get_anchor_path(fname)
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            m = data.get("_trial_mac", "")
            started = data.get("_trial_started", "")
            if m and started:
                candidates.append((m, started))
        except Exception:
            pass

    # 如果有文件记录了 trial_started（旧版 app_config.json），也要纳入
    try:
        from .config_manager import load_app_config
        cfg = load_app_config()
        t = cfg.get("trial_started", "")
        if t:
            candidates.append((cfg.get("_trial_mac", ""), t))
    except Exception:
        pass

    if not candidates:
        return "", ""

    # 取最早的 started_at
    candidates.sort(key=lambda x: x[1])
    return candidates[0]


def _load_trial_record() -> dict:
    """加载试用记录（含 MAC 绑定信息）"""
    if not os.path.exists(TRIAL_RECORD_FILE):
        return {}
    try:
        with open(TRIAL_RECORD_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_trial_record(record: dict) -> None:
    """保存试用记录"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TRIAL_RECORD_FILE, 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def is_trial_period(net_time: datetime = None) -> tuple[bool, int]:
    """
    判断是否在 14 天免费试用期内（MAC 绑定）。
    返回 (is_in_trial, remaining_days_or_0)。
    首次调用时自动记录 trial_started 时间并绑定本机 MAC。
    """
    current_mac = _get_mac()
    if current_mac == "unknown":
        return False, 0

    record = _load_trial_record()
    stored_mac = record.get("mac", "")
    stored_started = record.get("trial_started")

    # 迁移路径：旧版 app_config.json 有 trial_started 但无 trial_record.json
    if not record:
        from .config_manager import load_app_config
        cfg = load_app_config()
        legacy_started = cfg.get("trial_started")
        if legacy_started:
            record = {
                "mac": current_mac,
                "trial_started": legacy_started,
                "trial_notified": cfg.get("trial_notified", False),
            }
            _save_trial_record(record)
            stored_mac = current_mac
            stored_started = legacy_started

    if stored_mac == current_mac and stored_started:
        # 同一 MAC，试用已开始——检查是否到期
        if net_time is None:
            net_time = _get_network_time()
        if net_time is None:
            return False, 0
        started = datetime.fromisoformat(stored_started)
        elapsed_days = (net_time - started).days
        remaining = max(0, TRIAL_DAYS - elapsed_days)
        if remaining > 0:
            return True, remaining
        return False, 0

    # 试用记录为空（可能被清理）→ 从锚定文件恢复
    anchor_mac, anchor_started = _read_trial_from_anchors()
    if anchor_mac == current_mac and anchor_started:
        # 锚定文件中找到了本机 MAC 的试用记录，恢复
        stored_started = anchor_started
        if net_time is None:
            net_time = _get_network_time()
        if net_time is None:
            return False, 0
        started = datetime.fromisoformat(stored_started)
        elapsed_days = (net_time - started).days
        remaining = max(0, TRIAL_DAYS - elapsed_days)
        # 重新写入 trial_record.json
        _save_trial_record({
            "mac": current_mac,
            "trial_started": stored_started,
            "trial_notified": False,
        })
        if remaining > 0:
            return True, remaining
        return False, 0

    # 无试用记录 → 首次安装，创建 MAC 绑定的试用记录
    if net_time is None:
        net_time = _get_network_time()
    if net_time is None:
        return False, 0

    record = {
        "mac": current_mac,
        "trial_started": net_time.isoformat(),
        "trial_notified": False,
    }
    _save_trial_record(record)

    # 将试用记录写入多个锚定文件（防清理）
    _write_trial_anchor(current_mac, net_time.isoformat())

    # 向后兼容：同时写入 app_config.json
    from .config_manager import load_app_config, save_app_config
    cfg = load_app_config()
    cfg["trial_started"] = net_time.isoformat()
    save_app_config(cfg)

    return True, TRIAL_DAYS


def is_feature_allowed() -> bool:
    """
    功能许可检查（14天试用 or 礼品券激活）。
    邮件推送等功能调用此函数。
    """
    if is_activated():
        return True
    trial_ok, _ = is_trial_period()
    return trial_ok


def get_remaining_days_all() -> int:
    """
    获取剩余可用天数（先查礼品券，无券查试用）。
    """
    coupon_days = get_remaining_days()
    if coupon_days > 0:
        return coupon_days
    _, trial_days = is_trial_period()
    return trial_days


def get_current_mac() -> str:
    return _get_mac()


def check_mac_match(target_mac: str) -> bool:
    """比较给定 MAC 是否与本机一致"""
    return _get_mac() == target_mac

# HONGXUN-LOCKED — 此文件受保护，修改需密码验证
# 请通过程序界面解锁后编辑
"""
鸿讯 HONGXUN · 用户注册登录模块
版本 2.0.0

邮箱+密码注册登录制：
  - 用户名 = 邮箱；密码 ≥6 位，含数字+字母
  - 密码加盐 PBKDF2 哈希存储（管理员看不到明文）
  - 注册验证码经开发者 QQ 邮箱 SMTP 发送（内置配置）
  - 已注册账号写入 GitHub registry users 列表（管理员可查看邮箱，密码不可见）
  - 本地 session.json 记录登录态；游客可跳过登录使用免费版
  - 邀请码：用户首次生成专属 8 位码（唯一），被邀请人填码注册 → 邀请人 +1 个月全功能

数据安全：
  - 验证码只存本地待验证（10 分钟有效）
  - 密码永不存明文/永不写入 GitHub registry
"""

import json
import os
import random
import re
import secrets
import hashlib
from datetime import datetime, timedelta

from .config_manager import DATA_DIR, load_email_config, save_email_config, \
    load_email_data, save_email_data

USER_FILE = os.path.join(DATA_DIR, "user.json")
PENDING_FILE = os.path.join(DATA_DIR, "user_pending.json")
SESSION_FILE = os.path.join(DATA_DIR, "session.json")

CODE_VALID_MINUTES = 10
MAX_RESEND_SECONDS = 60
PASSWORD_MIN_LEN = 6
PBKDF2_ITERATIONS = 100000
INVITE_REWARD_DAYS = 30  # 邀请人奖励 1 个月全功能


def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _valid_email(email: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email))


def _generate_code() -> str:
    return f"{random.randint(0, 999999):06d}"


# ── 密码加密 ─────────────────────────────────────────────
def _hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """加盐 PBKDF2 哈希。返回 (hash_hex, salt_hex)。"""
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                             salt.encode('utf-8'), PBKDF2_ITERATIONS)
    return dk.hex(), salt


def _verify_password(password: str, salt: str, expected_hash: str) -> bool:
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                             salt.encode('utf-8'), PBKDF2_ITERATIONS)
    return secrets.compare_digest(dk.hex(), expected_hash)


def _valid_password(password: str) -> tuple[bool, str]:
    """密码规则：≥6 位，含数字+字母。"""
    if not password or len(password) < PASSWORD_MIN_LEN:
        return False, f"密码至少 {PASSWORD_MIN_LEN} 位"
    if not re.search(r"[0-9]", password) or not re.search(r"[a-zA-Z]", password):
        return False, "密码需同时包含数字和英文字母"
    return True, ""


# ── GitHub 注册表（复用 coupon_manager）───────────────────
def _fetch_registry_users() -> list:
    try:
        from . import coupon_manager
        registry, _sha = coupon_manager._fetch_registry()
        if registry:
            return registry.get("users", [])
    except Exception:
        pass
    return []


def _push_registry_users(users: list) -> bool:
    try:
        from . import coupon_manager
        registry, sha = coupon_manager._fetch_registry()
        if registry is None:
            registry = {}
        registry["users"] = users
        return coupon_manager._push_registry(registry, sha)
    except Exception:
        return False


# ── 邀请码 ───────────────────────────────────────────────
_INVITE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去易混淆字符


def _generate_invite_code() -> str:
    return "".join(secrets.choice(_INVITE_CHARS) for _ in range(8))


def generate_invite_code(email: str) -> tuple[bool, str]:
    """为用户生成专属 8 位邀请码（唯一）。已生成则直接返回。"""
    email = (email or "").strip().lower()
    data = _load_json(USER_FILE, {})
    if data.get("email") != email:
        return False, "请先登录"

    if data.get("invite_code"):
        return True, data["invite_code"]

    # 生成唯一码（查 registry + 本地去重）
    users = _fetch_registry_users()
    used = {u.get("invite_code") for u in users if u.get("invite_code")}
    for _ in range(10):
        code = _generate_invite_code()
        if code not in used:
            break
    else:
        return False, "邀请码生成失败，请重试"

    data["invite_code"] = code
    _save_json(USER_FILE, data)
    # 同步 registry
    for u in users:
        if u.get("email") == email:
            u["invite_code"] = code
            break
    _push_registry_users(users)
    return True, code


def validate_invite_code(code: str) -> str:
    """校验邀请码，返回邀请人邮箱；无效返回空串。"""
    code = (code or "").strip().upper()
    if not code:
        return ""
    users = _fetch_registry_users()
    for u in users:
        if u.get("invite_code") == code:
            return u.get("email", "")
    return ""


# ── 注册 / 验证码流程 ─────────────────────────────────────
def request_verification_code(email: str) -> tuple[bool, str]:
    """发送注册验证码到指定邮箱（开发者 QQ 邮箱 SMTP 发送）。"""
    email = (email or "").strip().lower()
    if not _valid_email(email):
        return False, "邮箱格式不正确，请检查后重试"
    if is_registered(email):
        return False, "该邮箱已注册，请直接登录"

    pending = _load_json(PENDING_FILE, {})
    last = pending.get("last_sent_at", "")
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            if (datetime.now() - last_dt).total_seconds() < MAX_RESEND_SECONDS:
                return False, "发送过于频繁，请稍候再试"
        except Exception:
            pass

    from .email_sender import send_code_email
    code = _generate_code()
    ok = send_code_email(email, code)
    if not ok:
        return False, "验证码发送失败，请稍后重试"

    pending["email"] = email
    pending["code"] = code
    pending["created_at"] = datetime.now().isoformat()
    pending["last_sent_at"] = datetime.now().isoformat()
    _save_json(PENDING_FILE, pending)
    return True, "验证码已发送，请查收邮箱"


def register(email: str, password: str, code: str,
             invite_code: str = None) -> tuple[bool, str]:
    """完成注册：校验验证码 + 密码，创建账号（邮箱=用户名）。

    成功返回 (True, 消息)；失败返回 (False, 原因)。
    """
    email = (email or "").strip().lower()
    if is_registered(email):
        return False, "该邮箱已注册，请直接登录"

    pwd_ok, pwd_msg = _valid_password(password)
    if not pwd_ok:
        return False, pwd_msg

    # 校验验证码
    pending = _load_json(PENDING_FILE, {})
    if pending.get("email") != email:
        return False, "请先发送验证码到该邮箱"
    if pending.get("code") != (code or "").strip():
        return False, "验证码错误，请重新输入"
    created = pending.get("created_at", "")
    if created:
        try:
            created_dt = datetime.fromisoformat(created)
            if datetime.now() - created_dt > timedelta(minutes=CODE_VALID_MINUTES):
                return False, "验证码已过期，请重新发送"
        except Exception:
            pass

    # 密码哈希
    hash_hex, salt = _hash_password(password)
    now = datetime.now().isoformat()

    # 邀请码：校验并奖励邀请人
    inviter_email = validate_invite_code(invite_code) if invite_code else ""

    user_data = {
        "username": email,
        "email": email,
        "password_hash": hash_hex,
        "salt": salt,
        "registered_at": now,
        "invite_code": "",
        "inviter_email": inviter_email or "",
        "invite_reward_until": "",
    }
    _save_json(USER_FILE, user_data)

    # 加入每日推送默认邮箱
    _add_to_receivers(email)

    # 清理待验证
    _save_json(PENDING_FILE, {})

    # 同步 GitHub registry（密码不写 registry，只写账号元信息）
    try:
        users = _fetch_registry_users()
        if email not in [u.get("email") for u in users]:
            users.append({
                "email": email,
                "username": email,
                "registered_at": now,
                "invite_code": "",
                "inviter_email": inviter_email or "",
            })
        _push_registry_users(users)
    except Exception:
        pass

    # 奖励邀请人（+1 个月全功能）
    if inviter_email:
        _reward_inviter(inviter_email)

    return True, "注册成功！请登录"


def _reward_inviter(inviter_email: str):
    """邀请人获得 1 个月全功能：写本地 user.json + registry。"""
    try:
        from .config_manager import DATA_DIR as _DD
        inviter_file = os.path.join(_DD, "user.json")
        # 仅当被邀请人本地有邀请人数据时奖励（多设备场景由 registry 处理）
        reward_until = (datetime.now() + timedelta(days=INVITE_REWARD_DAYS)).isoformat()
        users = _fetch_registry_users()
        for u in users:
            if u.get("email") == inviter_email:
                u["invite_reward_until"] = reward_until
        _push_registry_users(users)
        # 本地若已登录该邀请人则写本地
        data = _load_json(inviter_file, {})
        if data.get("email") == inviter_email:
            data["invite_reward_until"] = reward_until
            _save_json(inviter_file, data)
    except Exception:
        pass


# ── 登录 / 会话 ───────────────────────────────────────────
def login(username_or_email: str, password: str) -> tuple[bool, str]:
    """用邮箱（用户名）+ 密码登录。成功写 session.json。"""
    email = (username_or_email or "").strip().lower()
    data = _load_json(USER_FILE, {})
    if data.get("email") != email:
        # 本地无此账号，尝试从 GitHub registry 拉取（跨设备）
        if not _fetch_and_sync_account(email):
            return False, "账号不存在，请先注册"
        data = _load_json(USER_FILE, {})

    if not data.get("password_hash") or not data.get("salt"):
        return False, "该账号未设置密码，请重新注册"

    if not _verify_password(password, data["salt"], data["password_hash"]):
        return False, "密码错误，请重试"

    _save_json(SESSION_FILE, {
        "username": email,
        "email": email,
        "login_at": datetime.now().isoformat(),
    })
    return True, "登录成功"


def logout():
    """退出登录，清除会话。"""
    try:
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
    except Exception:
        pass


def is_logged_in() -> bool:
    """是否已登录（本地会话存在）。"""
    return bool(get_logged_in_email())


def get_logged_in_email() -> str:
    """返回当前登录邮箱；未登录返回空串。"""
    session = _load_json(SESSION_FILE, {})
    return session.get("email", "")


def _fetch_and_sync_account(email: str) -> bool:
    """从 GitHub registry 拉取账号并同步到本地（跨设备登录）。"""
    try:
        users = _fetch_registry_users()
        for u in users:
            if u.get("email") == email:
                # 只同步元信息，密码需本地已设（跨设备登录需先在本机注册）
                return False
    except Exception:
        pass
    return False


# ── 本地用户状态 ─────────────────────────────────────────
def get_registered_email() -> str:
    """读取已注册邮箱。"""
    data = _load_json(USER_FILE, {})
    return data.get("email", "")


def is_registered(email: str = None) -> bool:
    if email:
        return email == get_registered_email()
    return bool(get_registered_email())


def get_user_info() -> dict:
    """返回本地用户信息（不含密码哈希）。"""
    data = _load_json(USER_FILE, {})
    return {
        "email": data.get("email", ""),
        "username": data.get("username", ""),
        "invite_code": data.get("invite_code", ""),
        "inviter_email": data.get("inviter_email", ""),
        "invite_reward_until": data.get("invite_reward_until", ""),
        "registered_at": data.get("registered_at", ""),
    }


def _add_to_receivers(email: str):
    """把注册邮箱加入每日推送收件人列表（email_config + email_data 双写）。"""
    try:
        cfg = load_email_config()
        receivers = cfg.get("receivers", [])
        if isinstance(receivers, str):
            receivers = [r.strip() for r in receivers.replace('；', ';').split(';') if r.strip()]
        if not receivers and cfg.get("receiver", "").strip():
            receivers = [cfg["receiver"].strip()]
        if email not in receivers:
            receivers.append(email)
        cfg["receivers"] = receivers
        cfg["receiver"] = email
        save_email_config(cfg)

        data = load_email_data()
        rl = data.get("receivers", [])
        if email not in rl:
            rl.append(email)
        data["receivers"] = rl
        save_email_data(data)
    except Exception:
        pass

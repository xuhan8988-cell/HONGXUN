# HONGXUN-LOCKED — 此文件受保护，修改需密码验证
# 请通过程序界面解锁后编辑
"""
鸿讯 HONGXUN · 付费订阅模块
版本 2.0.0

聚合支付扫码订阅（个人开发者免签约）：
  - 弹窗展示收款二维码 → 用户扫码支付 → 轮询订单状态 → 支付成功自动激活并计时。
  - 订阅档位：3 个月 / 6 个月 / 12 个月 / 24 个月。

支付平台接入说明：
  本文件目前使用「占位假支付」流程（create_order 返回假订单、query_order 模拟支付成功），
  供界面联调与演示。接入真实聚合支付（如虎皮椒/易支付）时，只需替换下方
  PAYMENT_ADAPTER 区块内的两个函数实现，其余 UI 逻辑无需改动。

代码保护：
  本文件受 HONGXUN-LOCKED 保护，仅本机授权可查看/修改。
"""

import json
import os
import time
import uuid
from datetime import datetime, timedelta

# 路径处理（与 coupon_manager.py 保持一致）
if getattr(__import__('sys'), 'frozen', False):
    import sys as _sys
    BASE_DIR = os.path.join(os.path.dirname(_sys.executable), "_data")
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
LICENSE_FILE = os.path.join(DATA_DIR, "license.json")

# 网络时间（复用 coupon_manager 的获取逻辑）
try:
    from .coupon_manager import _get_network_time, _write_license, load_license
except Exception:
    _get_network_time = None

# ── 订阅档位 ──────────────────────────────────────────────
# plan_key → {label, months, days, origin_price, price, daily, discount}
PLANS = {
    "3M": {
        "label": "3 个月",
        "months": 3,
        "days": 90,
        "origin_price": 49.9,
        "price": 29.9,
        "daily": 0.33,
        "discount": "6折",
    },
    "6M": {
        "label": "6 个月",
        "months": 6,
        "days": 180,
        "origin_price": 99.9,
        "price": 49.9,
        "daily": 0.27,
        "discount": "5折",
    },
    "12M": {
        "label": "12 个月",
        "months": 12,
        "days": 365,
        "origin_price": 199.9,
        "price": 89.9,
        "daily": 0.24,
        "discount": "4.5折",
    },
    "24M": {
        "label": "24 个月",
        "months": 24,
        "days": 730,
        "origin_price": 399.9,
        "price": 159.9,
        "daily": 0.21,
        "discount": "4折",
    },
}

DEFAULT_PLAN = "12M"


# ======================================================================
# PAYMENT_ADAPTER — 真实聚合支付接入替换点
# ----------------------------------------------------------------------
# 接入真实支付平台时，替换下方 create_order / query_order 的实现即可。
# 要求：
#   create_order(plan) -> dict {order_id, qr_content, ...}
#   query_order(order_id) -> "pending" | "paid" | "failed"
# 参考平台：虎皮椒(xunhupay)、易支付等，均提供「下单 + 主动查询订单」API。
# ======================================================================

# 假支付开关：True 时模拟几秒后自动支付成功（联调用）。
# 接真实平台后改为 False 或删除。
_MOCK_PAYMENT = True
_MOCK_PAID_DELAY = 5  # 秒

# 假订单存储：order_id → {plan, created_at}
_mock_orders: dict[str, dict] = {}


def create_order(plan: str) -> dict:
    """创建支付订单，返回订单信息（含二维码内容）。

    占位实现：返回假订单与虚假二维码内容。
    真实接入：调用支付平台「下单 API」，获取收款二维码链接/字符串。
    """
    plan = plan if plan in PLANS else DEFAULT_PLAN
    order_id = "HX" + uuid.uuid4().hex[:16].upper()
    _mock_orders[order_id] = {
        "plan": plan,
        "created_at": time.time(),
        "paid": False,
    }
    return {
        "order_id": order_id,
        "plan": plan,
        "amount": PLANS[plan]["price"],
        # 虚假二维码内容：接入真实平台后替换为支付平台返回的 code_url / 二维码串
        "qr_content": f"HONGXUN-PAY|{order_id}|{PLANS[plan]['price']}|mock-qr",
    }


def query_order(order_id: str) -> str:
    """轮询订单状态，返回 "pending" / "paid" / "failed"。

    占位实现：_MOCK_PAYMENT 为 True 时，延时后自动标记 paid。
    真实接入：调用支付平台「订单查询 API」，返回实际支付状态。
    """
    order = _mock_orders.get(order_id)
    if not order:
        return "failed"
    if _MOCK_PAYMENT:
        elapsed = time.time() - order["created_at"]
        if elapsed >= _MOCK_PAID_DELAY:
            order["paid"] = True
            return "paid"
    return "paid" if order.get("paid") else "pending"


def get_qr_image(qr_content: str):
    """获取二维码图片对象（占位实现）。

    当前返回 None，由 UI 绘制「虚假二维码」占位图案。
    真实接入：用 qrcode 库根据 qr_content 生成 PIL Image 并返回。
    """
    try:
        import qrcode
        from PIL import Image
        img = qrcode.make(qr_content)
        return img
    except Exception:
        return None


def get_license_status() -> dict:
    """统一读取许可状态：{active, source, expires_at, remaining_days, in_grace, grace_until}。"""
    lic = load_license()
    activated = lic.get("activated", False)
    source = lic.get("source", lic.get("coupon_type", "")) or ""
    expires_at = lic.get("expires_at", "")
    remaining = 0
    in_grace = False
    grace_until = ""
    if activated and expires_at:
        try:
            now = _get_network_time() if _get_network_time else None
            now = now or datetime.now()
            exp = datetime.fromisoformat(expires_at)
            remaining = max(0, (exp - now).days)
            # 3 天宽限期
            if remaining == 0:
                in_grace = (exp + timedelta(days=3)) > now
                grace_until = (exp + timedelta(days=3)).isoformat()
                active = in_grace
            else:
                active = True
        except Exception:
            active = False
    else:
        active = False

    return {
        "active": active,
        "source": source,
        "expires_at": expires_at,
        "remaining_days": remaining,
        "in_grace": in_grace,
        "grace_until": grace_until,
        "permanent": bool(lic.get("permanent")),
    }


def activate_subscription(plan: str, paid_at: datetime = None) -> bool:
    """支付成功后激活订阅：写入 license.json。

    到期时间 = 支付时间 + 订阅时长（不叠加之前剩余）。
    """
    if plan not in PLANS:
        return False
    if paid_at is None:
        try:
            paid_at = _get_network_time() if _get_network_time else datetime.now()
        except Exception:
            paid_at = datetime.now()

    valid_days = PLANS[plan]["days"]
    expires_at = paid_at + timedelta(days=valid_days)

    license_data = {
        "activated": True,
        "source": "subscription",
        "plan": plan,
        "activated_at": paid_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "coupon_type": plan,
        "valid_days": valid_days,
        "permanent": False,
    }
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(LICENSE_FILE, 'w', encoding='utf-8') as f:
            json.dump(license_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def is_subscription_active() -> bool:
    """检查当前订阅是否在有效期内。"""
    st = get_license_status()
    return st["active"] and st["source"] == "subscription"

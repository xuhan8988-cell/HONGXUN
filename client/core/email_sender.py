# HONGXUN-LOCKED — 此文件受保护，修改需密码验证
# 请通过程序界面解锁后编辑
"""
鸿讯 HONGXUN · 邮件发送模块
版本 1.0.0
"""

import smtplib
from email.mime.text import MIMEText
from email.header import Header

from .config_manager import load_email_config
from .coupon_manager import is_feature_allowed


def send_email(subject: str, content: str) -> bool:
    """发送邮件，返回是否成功（检查许可激活状态）"""
    if not is_feature_allowed():
        return False

    cfg = load_email_config()
    if not cfg.get("sender") or not cfg.get("auth_code"):
        return False

    # 收集收件人列表（支持新格式 receivers 列表 与旧格式 receiver 字符串）
    receivers = cfg.get("receivers", [])
    if isinstance(receivers, str):
        receivers = [r.strip() for r in receivers.replace('；', ';').split(';') if r.strip()]
    if not receivers and cfg.get("receiver", "").strip():
        receivers = [cfg["receiver"].strip()]
    if not receivers:
        return False

    msg = MIMEText(content, 'plain', 'utf-8')
    msg['From'] = Header(cfg["sender"])
    msg['To'] = Header('; '.join(receivers))
    msg['Subject'] = Header(subject, 'utf-8')

    try:
        port = int(cfg["port"])
        if port == 465:
            server = smtplib.SMTP_SSL(cfg["smtp_server"], port)
        else:
            server = smtplib.SMTP(cfg["smtp_server"], port)
            server.starttls()
        server.login(cfg["sender"], cfg["auth_code"])
        server.sendmail(cfg["sender"], receivers, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"邮件发送失败: {str(e)}", flush=True)
        return False

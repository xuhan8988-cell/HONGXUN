# HONGXUN-LOCKED — 此文件受保护，修改需密码验证
# 请通过程序界面解锁后编辑
"""
鸿讯 HONGXUN · 配置管理模块
版本 1.0.0
"""

import json
import os
import re
import sys
from datetime import datetime
from typing import Optional

# 路径常量
# PyInstaller 打包后，数据文件夹应该放在 exe 同级
if getattr(sys, 'frozen', False):
    _EXE_DIR = os.path.dirname(sys.executable)
    BASE_DIR = os.path.join(_EXE_DIR, "_data")
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
UNSENT_DIR = os.path.join(OUTPUT_DIR, "unsent")
TASKS_FILE = os.path.join(DATA_DIR, "tasks.json")
EMAIL_FILE = os.path.join(DATA_DIR, "email_config.json")
RECORDS_FILE = os.path.join(DATA_DIR, "push_records.json")
EMAIL_DATA_FILE = os.path.join(DATA_DIR, "email_data.json")
APP_CONFIG_FILE = os.path.join(DATA_DIR, "app_config.json")
SCHEDULER_PID_FILE = os.path.join(DATA_DIR, "scheduler.pid")
SCHEDULER_STOP_FILE = os.path.join(DATA_DIR, "scheduler_stop.flag")
SCHEDULER_LOG_FILE = os.path.join(DATA_DIR, "scheduler.log")
LIBRARY_FILE = os.path.join(DATA_DIR, "library.json")

# 初始化目录
for d in [DATA_DIR, OUTPUT_DIR, UNSENT_DIR]:
    os.makedirs(d, exist_ok=True)

# 正则规则
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')
MIN_DATE = datetime(1949, 10, 1)
MAX_DATE = datetime(2100, 10, 1)


def _load_json(file_path, default):
    if not os.path.exists(file_path):
        return default
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return default


def _save_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# -------------------- 输入校验 --------------------
def _split_items(text: str) -> list[str]:
    """将输入按多种分隔符分割，返回去空后的项目列表。

    支持的分隔符：
      - 英文分号 ;
      - 中文分号 ；
      - 英文逗号 ,
      - 中文逗号 ，
      - 中文顿号 、
    """
    normalized = text
    for sep in ['；', '，', '、', ',']:
        normalized = normalized.replace(sep, ';')
    items = [item.strip() for item in normalized.split(';') if item.strip()]
    return items


def validate_journals(journal_str: str) -> tuple[list[str], list[str]]:
    """校验期刊名称输入，返回(合法列表, 错误信息列表)"""
    errors = []
    if not journal_str.strip():
        errors.append("期刊输入框不能为空")
        return [], errors

    items = _split_items(journal_str)
    if len(items) > 10:
        errors.append(f"期刊数量不能超过10个，当前输入{len(items)}个")

    valid = []
    for idx, item in enumerate(items, 1):
        if len(item) < 1:
            errors.append(f"期刊输入框第{idx}项内容为空")
        else:
            valid.append(item)
    return valid, errors


def validate_keywords(keyword_str: str) -> tuple[list[str], list[str]]:
    """校验关键词输入，返回(合法列表, 错误信息列表)"""
    errors = []
    if not keyword_str.strip():
        errors.append("关键词输入框不能为空")
        return [], errors

    items = _split_items(keyword_str)
    if len(items) > 10:
        errors.append(f"关键词数量不能超过10个，当前输入{len(items)}个")

    valid = []
    for idx, item in enumerate(items, 1):
        if len(item) < 1:
            errors.append(f"关键词输入框第{idx}项内容为空")
        else:
            valid.append(item)
    return valid, errors


def validate_keywords2(keyword_str: str) -> tuple[list[str], list[str]]:
    """校验第二个关键词输入框（可为空，最多2个），返回(合法列表, 错误信息列表)"""
    errors = []
    if not keyword_str.strip():
        return [], errors  # 为空合法

    items = _split_items(keyword_str)
    if len(items) > 2:
        errors.append(f"关键词(选填)数量不能超过2个，当前输入{len(items)}个")

    valid = []
    for idx, item in enumerate(items, 1):
        if len(item) < 1:
            errors.append(f"关键词(选填)第{idx}项内容为空")
        else:
            valid.append(item)
    return valid, errors


def validate_date_range(date_str: str) -> tuple[tuple[str, str], list[str]]:
    """校验时间范围输入，返回((起始日期, 结束日期), 错误信息列表)"""
    errors = []
    if not date_str.strip():
        errors.append("时间范围输入框不能为空")
        return ("", ""), errors

    # 先统一将中文分号替换为英文分号
    normalized = date_str.replace('；', ';')
    parts = [p.strip() for p in normalized.split(';') if p.strip()]
    if len(parts) != 2:
        errors.append("时间范围格式错误，正确格式为 yyyy-mm-dd;yyyy-mm-dd")
        return ("", ""), errors
    
    start_str, end_str = parts
    if not DATE_PATTERN.match(start_str):
        errors.append(f"时间范围起始日期「{start_str}」格式错误，应为 yyyy-mm-dd")
    if not DATE_PATTERN.match(end_str):
        errors.append(f"时间范围结束日期「{end_str}」格式错误，应为 yyyy-mm-dd")
    
    if errors:
        return ("", ""), errors
    
    try:
        start_dt = datetime.strptime(start_str, "%Y-%m-%d")
        end_dt = datetime.strptime(end_str, "%Y-%m-%d")
    except ValueError as e:
        errors.append(f"时间范围日期不合法：{str(e)}")
        return ("", ""), errors
    
    if start_dt < MIN_DATE:
        errors.append("起始日期不能早于 1949-10-01")
    if end_dt > MAX_DATE:
        errors.append("结束日期不能晚于 2100-10-01")
    if start_dt >= end_dt:
        errors.append("起始日期必须早于结束日期")
    
    return (start_str, end_str), errors


def validate_email_config(cfg: dict) -> list[str]:
    """校验邮箱配置，返回错误信息列表"""
    errors = []
    if not cfg.get("sender", "").strip():
        errors.append("发件邮箱不能为空")
    elif not EMAIL_PATTERN.match(cfg["sender"].strip()):
        errors.append("发件邮箱格式不正确")

    if not cfg.get("auth_code", "").strip():
        errors.append("SMTP授权码不能为空")

    port = cfg.get("port", "")
    if not str(port).strip():
        errors.append("SMTP端口不能为空")
    else:
        try:
            port_num = int(port)
            if port_num < 1 or port_num > 65535:
                errors.append("SMTP端口数值超出合法范围(1-65535)")
        except ValueError:
            errors.append("SMTP端口必须为数字")

    # 多收件人校验（支持旧版单字符串和列表）
    receivers = cfg.get("receivers", [])
    if isinstance(receivers, str):
        if receivers.strip():
            receivers = [r.strip() for r in receivers.replace('；', ';').split(';') if r.strip()]
        else:
            receivers = []

    if isinstance(cfg.get("receiver", ""), str) and cfg["receiver"].strip():
        r = cfg["receiver"].strip()
        if r not in receivers:
            receivers.insert(0, r)

    if not receivers:
        errors.append("至少需要设置1个收件邮箱")

    for r in receivers:
        if not EMAIL_PATTERN.match(r):
            errors.append(f"收件邮箱「{r}」格式不正确")

    if len(receivers) > 5:
        errors.append(f"收件邮箱最多设置5个，当前已添加{len(receivers)}个")

    return errors


def validate_receivers(receiver_str: str) -> tuple[list[str], list[str]]:
    """校验收件邮箱字符串（分号分隔），返回 (列表, 错误)"""
    errors = []
    if not receiver_str.strip():
        errors.append("收件邮箱列表不能为空")
        return [], errors
    normalized = receiver_str.replace('；', ';')
    items = [r.strip() for r in normalized.split(';') if r.strip()]
    valid = []
    for idx, r in enumerate(items, 1):
        if not EMAIL_PATTERN.match(r):
            errors.append(f"第{idx}个收件邮箱「{r}」格式不正确")
        else:
            valid.append(r)
    if len(valid) > 5:
        errors.append(f"收件邮箱最多设置5个，当前已添加{len(valid)}个")
        return valid[:5], errors
    return valid, errors


# -------------------- 任务管理 --------------------
def load_all_tasks() -> dict:
    return _load_json(TASKS_FILE, {})


def save_task(task_id: str, task_data: dict) -> None:
    tasks = load_all_tasks()
    tasks[task_id] = task_data
    _save_json(TASKS_FILE, tasks)


def delete_task(task_id: str) -> None:
    tasks = load_all_tasks()
    if task_id in tasks:
        del tasks[task_id]
        _save_json(TASKS_FILE, tasks)


def get_task(task_id: str) -> Optional[dict]:
    tasks = load_all_tasks()
    return tasks.get(task_id)


# -------------------- 邮箱配置 --------------------
def load_email_config() -> dict:
    default = {
        "sender": "",
        "auth_code": "",
        "smtp_server": "smtp.qq.com",
        "port": 465,
        "receiver": ""
    }
    return _load_json(EMAIL_FILE, default)


def save_email_config(cfg: dict) -> None:
    _save_json(EMAIL_FILE, cfg)


def load_email_data() -> dict:
    """加载邮箱扩展数据（收件人列表等）"""
    default = {"receivers": []}
    return _load_json(EMAIL_DATA_FILE, default)


def save_email_data(data: dict) -> None:
    """保存邮箱扩展数据"""
    _save_json(EMAIL_DATA_FILE, data)


# -------------------- 推送记录（去重） --------------------
def load_push_records() -> dict:
    return _load_json(RECORDS_FILE, {})


def add_push_record(task_id: str, doi_list: list[str]) -> None:
    records = load_push_records()
    if task_id not in records:
        records[task_id] = []
    records[task_id].extend(doi_list)
    records[task_id] = list(set(records[task_id]))[-5000:]  # 保留最近5000条
    _save_json(RECORDS_FILE, records)


# -------------------- 应用配置（试用期等全局设置） --------------------
def load_app_config() -> dict:
    """加载应用级配置，返回配置字典"""
    default = {
        # 14天免费试用
        "trial_started": None,   # 首次启动时的 ISO 时间戳
        "trial_notified": False, # 是否已弹出试用提示
    }
    return _load_json(APP_CONFIG_FILE, default)


def save_app_config(cfg: dict) -> None:
    """保存应用级配置"""
    _save_json(APP_CONFIG_FILE, cfg)
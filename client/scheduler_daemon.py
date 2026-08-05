# HONGXUN-LOCKED — 此文件受保护，修改需密码验证
# 请通过程序界面解锁后编辑
#!/usr/bin/env python3
"""
鸿讯 HONGXUN · 独立调度守护进程 v2.0

由 GUI 自动启动/停止，与 GUI 生命周期解耦。
功能：
  · 每天早上 8:00 执行增量论文检索 → 邮件推送
  · 首次运行从 daemon 启动时间计算到当天 8:00 的时间范围
  · 之后每次以昨天 8:00 → 今天 8:00 为 24h 周期
  · 无新增论文时写入结果文件供 GUI 弹窗提示
"""
import os, sys, json, signal, time, logging, datetime as dt_module, subprocess
from datetime import datetime, timedelta

# 确保能找到 core 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 路径常量（与 config_manager 保持一致：打包后数据在 exe 同级 _data 下）
if getattr(sys, 'frozen', False):
    _EXE_DIR = os.path.dirname(sys.executable)
    _BASE_DIR = os.path.join(_EXE_DIR, "_data")
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_BASE_DIR, "data")
PID_FILE = os.path.join(DATA_DIR, "scheduler.pid")
STOP_FILE = os.path.join(DATA_DIR, "scheduler_stop.flag")
STATE_FILE = os.path.join(DATA_DIR, "scheduler_state.json")
RESULT_FILE = os.path.join(DATA_DIR, "scheduler_last_result.json")
UNSENT_DIR = os.path.join(_BASE_DIR, "output", "unsent")

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UNSENT_DIR, exist_ok=True)

# ============ 日志 ============
LOG_FILE = os.path.join(DATA_DIR, "scheduler.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# 同时也输出到 stderr（便于 GUI 捕获异常）
console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.getLogger().addHandler(console)


def _log(msg, level="info"):
    getattr(logging, level, logging.info)(msg)


# ============ 信号处理 ============
def _signal_handler(sig, frame):
    _log(f"收到信号 {sig}，正在退出...")
    _cleanup()
    sys.exit(0)


def _cleanup():
    """清理 PID 文件和停止标记"""
    for f in [PID_FILE, STOP_FILE]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass


# ============ 状态持久化 ============

def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_state(state: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding='utf-8') as f:
        json.dump(state, f, indent=2)

def _write_result(has_new: bool, total: int, task_details: str = "", *, unsent_attachments: bool = False):
    """写入本次推送结果，供 GUI 读取显示"""
    result = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "has_new": has_new,
        "total": total,
        "task_details": task_details,
        "unsent_attachments": unsent_attachments,
    }
    with open(RESULT_FILE, "w", encoding='utf-8') as f:
        json.dump(result, f, indent=2)


def _write_llm_failure(reason: str):
    """写入 LLM 翻译失败标记，供 GUI 轮询弹窗提示用户。"""
    result = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "llm_failed": True,
        "reason": reason,
    }
    try:
        with open(RESULT_FILE, "w", encoding='utf-8') as f:
            json.dump(result, f, indent=2)
    except Exception:
        pass
    # 同时在 state 中标记，GUI 启动时也能读到
    try:
        state = _load_state()
        state["llm_failed"] = True
        state["llm_failed_reason"] = reason
        _save_state(state)
    except Exception:
        pass


# ============ 调度逻辑 ============
CHECK_INTERVAL = 5  # 等待时的轮询间隔（秒）


def _should_stop() -> bool:
    return os.path.exists(STOP_FILE)


def run_scheduler():
    _log("调度守护进程 v2.0 启动")
    _log(f"PID: {os.getpid()}")

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PID_FILE, "w", encoding='utf-8') as f:
        f.write(str(os.getpid()))
    if os.path.exists(STOP_FILE):
        try:
            os.remove(STOP_FILE)
        except Exception:
            pass

    # 记录启动时间（首次执行的起点）
    first_start = datetime.now()
    state = _load_state()
    if "first_start_ts" not in state:
        state["first_start_ts"] = first_start.isoformat()
        state["last_run_end_ts"] = None  # None 表示尚未执行过
        _save_state(state)
        _log(f"首次启动时间: {first_start.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        _log(f"守护进程恢复，首次启动时间: {state['first_start_ts']}")

    while True:
        if _should_stop():
            _log("检测到停止标记，退出")
            _cleanup()
            return

        now = datetime.now()
        # 推送时间从 app_config.json 读取（HH:MM，默认 08:00）
        try:
            _cfg = json.load(open(os.path.join(DATA_DIR, "app_config.json"), encoding="utf-8"))
            _push_hh, _push_mm = (str(_cfg.get("push_time", "08:00")).split(":") + ["00", "00"])[:2]
            _push_hh = int(_push_hh)
            _push_mm = int(_push_mm)
        except Exception:
            _push_hh, _push_mm = 8, 0
        today_8am = now.replace(hour=_push_hh, minute=_push_mm, second=0, microsecond=0)
        if now < today_8am:
            next_run = today_8am
        else:
            next_run = today_8am + timedelta(days=1)

        wait_seconds = (next_run - now).total_seconds()
        _log(f"下次执行时间: {next_run.strftime('%Y-%m-%d %H:%M')} (等待 {int(wait_seconds)} 秒)")

        # 等待至下次执行
        while wait_seconds > 0:
            if _should_stop():
                _log("检测到停止标记，退出")
                _cleanup()
                return
            chunk = min(wait_seconds, CHECK_INTERVAL)
            time.sleep(chunk)
            wait_seconds -= chunk

        # == 执行时间到（早上 8:00）==
        try:
            _execute_push()
        except Exception as e:
            _log(f"每日推送执行异常: {e}", "error")


def _execute_push():
    """执行一次每日推送"""
    _log("开始执行每日推送...")

    # macOS: 启动 caffeinate 防止休眠
    caffeinate_proc = None
    if sys.platform == "darwin":
        try:
            caffeinate_proc = subprocess.Popen(
                ["caffeinate", "-dimsu"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    try:
        _do_execute_push()
    finally:
        if caffeinate_proc is not None:
            try:
                caffeinate_proc.terminate()
                caffeinate_proc.wait(timeout=3)
            except Exception:
                try:
                    caffeinate_proc.kill()
                except Exception:
                    pass


def _do_execute_push():
    from core import (
        load_all_tasks, load_email_config, load_email_data,
        run_increment_check, send_combined_email, add_push_record,
    )
    from core.email_sender import send_email

    # 加载状态，确定检索时间范围
    state = _load_state()
    now = datetime.now()

    if state.get("last_run_end_ts") is None:
        # 第一次执行：从 daemon 启动时间到当前 8:00
        try:
            search_start = datetime.fromisoformat(state["first_start_ts"])
        except Exception:
            search_start = now - timedelta(days=1)
        _log(f"首次推送，时间范围: {search_start.strftime('%Y-%m-%d %H:%M')} ~ {now.strftime('%Y-%m-%d %H:%M')}")
    else:
        # 后续执行：从上一次结束时间到当前 8:00（约 24h）
        try:
            search_start = datetime.fromisoformat(state["last_run_end_ts"])
        except Exception:
            search_start = now - timedelta(hours=24)
        _log(f"常规推送，时间范围: {search_start.strftime('%Y-%m-%d %H:%M')} ~ {now.strftime('%Y-%m-%d %H:%M')}")

    end_str = now.strftime("%Y-%m-%d %H:%M:%S")
    start_str = search_start.strftime("%Y-%m-%d %H:%M:%S")

    tasks = load_all_tasks()
    if not tasks:
        _log("无任何任务，跳过")
        # 更新状态
        state["last_run_end_ts"] = now.isoformat()
        _save_state(state)
        _write_result(False, 0, "无任何任务")
        return

    all_results = []
    total_new = 0
    task_details_list = []

    for tid, task in tasks.items():
        if not task.get("enabled", True):
            continue
        try:
            # 传入自定义时间范围替代默认 24h
            new_papers = run_increment_check(tid, task, start_str=start_str, end_str=end_str)
            if new_papers:
                all_results.append((tid, task["name"], new_papers))
                total_new += len(new_papers)
                task_details_list.append(f"{task['name']}({len(new_papers)}篇)")
                _log(f"任务「{task['name']}」新增 {len(new_papers)} 篇论文")
            else:
                _log(f"任务「{task['name']}」无新增论文")
        except Exception as e:
            # LLM 翻译失败 → 写入失败标记并中止本次推送（不更新 last_run_end_ts）
            try:
                from core.translator import TranslationError
            except Exception:
                TranslationError = None
            if TranslationError is not None and isinstance(e, TranslationError):
                _log(f"LLM 翻译失败，中止每日推送: {e}", "error")
                _write_llm_failure(str(e))
                return
            _log(f"任务「{task.get('name', tid)}」增量检查失败: {e}", "error")

    if all_results:
        _log(f"共 {len(all_results)} 个任务有新论文，准备发送邮件...")
        try:
            result = send_combined_email(all_results)
            if result:
                _log("邮件推送成功")
                # 邮件发送成功后再记录推送状态
                for tid, tname, papers in all_results:
                    add_push_record(tid, [p["doi"] for p in papers])
            else:
                _log("邮件推送失败（可能配置不完整）", "error")
        except Exception as e:
            _log(f"邮件发送异常: {e}", "error")
        # 检查是否有未发送附件
        has_unsent = os.path.exists(os.path.join(UNSENT_DIR, "pending_email.json"))
        _write_result(True, total_new, "; ".join(task_details_list), unsent_attachments=has_unsent)
    else:
        _log("无新增论文，跳过邮件发送")
        # 无论文时写入结果，供 GUI 弹窗
        _write_result(False, 0, "所有任务均无新增论文")

    # 更新状态
    state["last_run_end_ts"] = now.isoformat()
    _save_state(state)
    _log("每日推送执行完毕")


# ============ launchd 开机自启管理 ============

def get_daemon_path() -> str:
    return os.path.abspath(__file__)

def get_plist_path() -> str:
    plist_name = "com.hongxun.papermonitor.scheduler.plist"
    return os.path.expanduser(f"~/Library/LaunchAgents/{plist_name}")

def install_launchd() -> bool:
    if sys.platform != "darwin":
        return True  # 未在 macOS 上，跳过
    import pathlib
    plist_path = get_plist_path()
    daemon_path = get_daemon_path()
    python_path = sys.executable
    os.makedirs(os.path.dirname(plist_path), exist_ok=True)

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hongxun.papermonitor.scheduler</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{daemon_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>WorkingDirectory</key>
    <string>{os.path.dirname(daemon_path)}</string>
    <key>StandardOutPath</key>
    <string>{os.path.join(DATA_DIR, "launchd_stdout.log")}</string>
    <key>StandardErrorPath</key>
    <string>{os.path.join(DATA_DIR, "launchd_stderr.log")}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")}</string>
    </dict>
</dict>
</plist>
"""
    try:
        with open(plist_path, "w", encoding="utf-8") as f:
            f.write(plist_content)
        result = subprocess.run(
            ["launchctl", "load", plist_path],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            _log(f"launchd 开机自启已注册: {plist_path}")
            return True
        else:
            _log(f"launchctl load 失败: {result.stderr.strip()}", "error")
            return False
    except Exception as e:
        _log(f"注册 launchd 异常: {e}", "error")
        return False

def uninstall_launchd() -> bool:
    if sys.platform != "darwin":
        return True
    plist_path = get_plist_path()
    if not os.path.exists(plist_path):
        return True
    try:
        subprocess.run(
            ["launchctl", "unload", plist_path],
            capture_output=True, text=True, timeout=15
        )
        os.remove(plist_path)
        return True
    except Exception as e:
        _log(f"卸载 launchd 异常: {e}", "error")
        return False

def is_launchd_installed() -> bool:
    if sys.platform != "darwin":
        return False
    plist_path = get_plist_path()
    if not os.path.exists(plist_path):
        return False
    try:
        result = subprocess.run(
            ["launchctl", "list", "com.hongxun.papermonitor.scheduler"],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


# ============ Windows 开机自启管理（注册表方式） ============

def _get_windows_startup_name() -> str:
    return "HONGXUN-Scheduler"


def _get_windows_daemon_cmd() -> str:
    """获取 Windows 守护进程的启动命令"""
    python_exe = sys.executable
    daemon_path = os.path.abspath(__file__)
    return f'"{python_exe}" "{daemon_path}"'


def install_windows_startup() -> bool:
    """注册 Windows 开机自启（通过注册表 HKCU\...\Run）"""
    if sys.platform != "win32":
        return True
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, _get_windows_startup_name(), 0,
                          winreg.REG_SZ, _get_windows_daemon_cmd())
        winreg.CloseKey(key)
        _log("Windows 开机自启已注册")
        return True
    except Exception as e:
        _log(f"注册 Windows 开机自启失败: {e}", "error")
        return False


def uninstall_windows_startup() -> bool:
    """卸载 Windows 开机自启"""
    if sys.platform != "win32":
        return True
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        try:
            winreg.DeleteValue(key, _get_windows_startup_name())
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
        _log("Windows 开机自启已卸载")
        return True
    except Exception as e:
        _log(f"卸载 Windows 开机自启失败: {e}", "error")
        return False


def is_windows_startup_installed() -> bool:
    """检查 Windows 开机自启是否已注册"""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        )
        value, _ = winreg.QueryValueEx(key, _get_windows_startup_name())
        winreg.CloseKey(key)
        return value == _get_windows_daemon_cmd()
    except (FileNotFoundError, Exception):
        return False


# ============ 入口 ============
if __name__ == "__main__":
    # Windows 不支持部分信号，用 try/except 安全处理
    if sys.platform != "win32":
        try:
            signal.signal(signal.SIGTERM, _signal_handler)
        except Exception:
            pass
    try:
        signal.signal(signal.SIGINT, _signal_handler)
    except Exception:
        pass

    try:
        run_scheduler()
    except KeyboardInterrupt:
        _cleanup()
    except Exception as e:
        _log(f"守护进程异常崩溃: {e}", "error")
        _cleanup()
        raise

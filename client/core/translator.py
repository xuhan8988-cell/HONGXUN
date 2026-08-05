"""
鸿讯 HONGXUN · AI 翻译模块（LLM 大模型接入）
版本 2.0.0

支持多家 LLM 大模型（OpenAI 兼容接口）：
  - DeepSeek：https://api.deepseek.com/v1，模型 deepseek-chat
  - 豆包 Doubao（火山方舟）：https://ark.cn-beijing.volces.com/api/v3，
    模型需填「推理接入点 ID」（形如 ep-2024xxxxxxxx-xxxxx）
  - MiniMax：https://api.minimaxi.com/v1，模型 MiniMax-Text-01

API Key 从项目根目录的 .env 文件读取（DEEPSEEK_API_KEY 兼容旧键名）。
厂商 / Base URL / 模型可在「设置 → AI 翻译 → 配置 API」弹窗中修改，
持久化到 app_config.json（键：llm_provider / llm_base_url / llm_model）。
"""

import os
import re
import json
from .session import _session

# 默认 DeepSeek（兼容旧配置）
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

# 厂商预设：key → (label, base_url, model 提示)
# 全部为 OpenAI 兼容接口（POST /chat/completions + Bearer Key）
PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek 深度求索",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "qwen": {
        "label": "千问 Qwen（阿里云百炼）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "zhipu": {
        "label": "智谱 GLM（智谱AI）",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
    "doubao": {
        "label": "豆包 Doubao（火山方舟）",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "ep-填推理接入点ID",
    },
    "kimi": {
        "label": "Kimi（月之暗面）",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    "minimax": {
        "label": "MiniMax（稀宇科技）",
        "base_url": "https://api.minimaxi.com/v1",
        "model": "MiniMax-Text-01",
    },
    "custom": {
        "label": "自定义（OpenAI 兼容）",
        "base_url": "",
        "model": "",
    },
}

# API Key — 从 .env 文件加载
_api_key = ""

# 配置缓存（避免频繁读 app_config）
_llm_cfg_cache: dict | None = None


class TranslationError(Exception):
    """LLM API 调用失败。code: 401/402/403/429/0(无key)/-1(网络错误)。"""

    def __init__(self, code: int, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(detail)


def _env_path() -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, ".env")


def _load_key_from_env() -> str:
    """从 .env 文件读取 DEEPSEEK_API_KEY"""
    env_path = _env_path()
    if os.path.exists(env_path):
        try:
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DEEPSEEK_API_KEY="):
                        return line.split("=", 1)[1].strip().strip("\"'")
        except Exception:
            pass
    return ""


def _load_app_config() -> dict:
    try:
        from .config_manager import load_app_config
        return load_app_config()
    except Exception:
        return {}


def _get_llm_cfg() -> dict:
    global _llm_cfg_cache
    if _llm_cfg_cache is None:
        cfg = _load_app_config()
        _llm_cfg_cache = {
            "provider": cfg.get("llm_provider", "deepseek"),
            "base_url": cfg.get("llm_base_url", ""),
            "model": cfg.get("llm_model", ""),
        }
    return _llm_cfg_cache


def _reset_cfg_cache():
    global _llm_cfg_cache
    _llm_cfg_cache = None


def get_provider() -> str:
    return _get_llm_cfg().get("provider", "deepseek") or "deepseek"


def get_api_url() -> str:
    """返回 chat/completions 完整 URL。base_url 存的是不带 /chat/completions 的地址。"""
    cfg = _get_llm_cfg()
    base = (cfg.get("base_url") or "").strip()
    if not base:
        base = PROVIDERS.get(cfg.get("provider", "deepseek"), PROVIDERS["deepseek"]).get("base_url", "")
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def get_model() -> str:
    cfg = _get_llm_cfg()
    model = (cfg.get("model") or "").strip()
    if model:
        return model
    return PROVIDERS.get(cfg.get("provider", "deepseek"), PROVIDERS["deepseek"]).get("model", DEEPSEEK_MODEL)


def set_api_key(key: str):
    global _api_key
    _api_key = (key or "").strip()


def get_api_key() -> str:
    return _api_key or _load_key_from_env()


def save_env_config(provider: str, api_key: str, base_url: str = "", model: str = "") -> None:
    """保存 LLM 配置。API Key 写入 client/.env，厂商/URL/模型写入 app_config.json。"""
    global _api_key
    _api_key = (api_key or "").strip()

    # 1. 写 .env（兼容旧 DEEPSEEK_API_KEY 键名）
    env_path = _env_path()
    new_lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            new_lines = f.read().splitlines()
    # 移除旧键，避免重复
    new_lines = [ln for ln in new_lines
                 if not ln.strip().startswith(("DEEPSEEK_API_KEY=", "LLM_PROVIDER=",
                                               "LLM_BASE_URL=", "LLM_MODEL="))]
    if _api_key:
        new_lines.append(f"DEEPSEEK_API_KEY={_api_key}")
    try:
        with open(env_path, "w") as f:
            f.write("\n".join(new_lines) + "\n")
    except Exception as e:
        raise TranslationError(-2, f"无法写入 .env 文件：{e}")

    # 2. 写 app_config.json
    try:
        from .config_manager import load_app_config, save_app_config
        cfg = load_app_config()
        cfg["llm_provider"] = provider or "deepseek"
        if base_url:
            cfg["llm_base_url"] = base_url.strip()
        if model:
            cfg["llm_model"] = model.strip()
        save_app_config(cfg)
    except Exception:
        pass
    _reset_cfg_cache()


def test_api_connection(api_key: str = "", base_url: str = "", model: str = "") -> tuple[bool, str]:
    """发一次最小 chat 请求验证 API 可用性。返回 (ok, msg)。

    401 → 密钥无效/已删除；402 → 欠费；403 → 无权访问该模型；
    429 → 限流/配额用尽；网络错误 → 连通性问题。
    """
    key = (api_key or get_api_key()).strip()
    if not key:
        return False, "未配置 API Key，请先在弹窗中填写。"
    url = base_url.strip() or get_api_url()
    mdl = model.strip() or get_model()
    url = url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"
    try:
        resp = _session.post(
            url,
            json={
                "model": mdl,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            },
            headers={"Authorization": f"Bearer {key}"},
            timeout=30,
        )
        if resp.status_code == 200:
            return True, "连接成功，API 可用。"
        msg = _classify_error(resp.status_code)
        return False, f"连接失败（HTTP {resp.status_code}）：{msg}"
    except Exception as e:
        return False, f"网络错误：{e}"


def _classify_error(status: int) -> str:
    if status == 401:
        return "API 密钥无效或已被删除"
    if status == 402:
        return "账户余额不足/欠费"
    if status == 403:
        return "密钥无权访问该模型"
    if status == 429:
        return "请求过多或配额用尽"
    if 400 <= status < 500:
        return "请求参数错误"
    return "服务端错误"


def _has_chinese(text: str) -> bool:
    """检测文本是否包含中文字符"""
    return bool(re.search(r'[一-鿿]', text))


def translate_text(text: str, source_lang: str = "英文", target_lang: str = "中文") -> str:
    """
    翻译单段学术文本。
    如果已经是目标语言，直接返回原文。
    API 失败时抛 TranslationError（code 区分原因）。
    """
    if not text or not text.strip():
        return ""
    # 已包含中文则跳过翻译
    if _has_chinese(text):
        return text

    key = get_api_key()
    if not key:
        raise TranslationError(0, "未配置 API Key，请到设置 → AI 翻译 → 配置 API 填写。")

    prompt = (
        f"请将以下{source_lang}学术论文内容翻译为{target_lang}，"
        f"保持学术严谨性和专业术语准确性。"
        f"只返回翻译结果，不要添加任何解释或额外内容。\n\n{text}"
    )

    resp = _session.post(
        get_api_url(),
        json={
            "model": get_model(),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 4096,
        },
        headers={"Authorization": f"Bearer {key}"},
        timeout=60,
    )
    if resp.status_code == 200:
        data = resp.json()
        translated = data["choices"][0]["message"]["content"].strip()
        return translated
    raise TranslationError(resp.status_code, _classify_error(resp.status_code))


def translate_paper(paper: dict) -> dict:
    """
    翻译单篇论文的标题和摘要。
    返回更新后的 paper dict（添加 title_cn, abstract_cn）。
    任何 API 失败都会向上抛 TranslationError，由调用方中断整体流程。
    """
    title = paper.get("title", "")
    abstract = paper.get("abstract", "")
    _k = get_api_key()

    if title and not _has_chinese(title) and _k:
        paper["title_cn"] = translate_text(title)
    else:
        paper["title_cn"] = paper.get("title_cn", "")

    if abstract and abstract != "无摘要" and not _has_chinese(abstract) and _k:
        paper["abstract_cn"] = translate_text(abstract)
    else:
        paper["abstract_cn"] = paper.get("abstract_cn", "")

    return paper


def translate_papers(papers: list[dict], enabled: bool = True) -> list[dict]:
    """
    批量翻译论文列表。
    只在 enabled=True 且已配置 API Key 时执行翻译。
    API 级失败（401/402/403/429/无key/网络错误）时立即抛 TranslationError，
    由调用方（检索 / 每日推送）中断流程并提示用户。
    """
    _k = get_api_key()
    if not enabled or not _k:
        return papers

    for p in papers:
        translate_paper(p)

    return papers

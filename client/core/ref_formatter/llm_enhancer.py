"""LLM 增强层（可选）：自定义格式解析、智能修复、自定义格式格式化。

复用核心 translator 模块的 LLM 配置（llm_provider / llm_base_url / llm_model /
.env DEEPSEEK_API_KEY），做 OpenAI 兼容 chat 调用。未配置 API Key 时优雅降级。
"""

import requests


class RefLLMError(Exception):
    pass


class RefLLMEnhancer:
    """参考文献 LLM 增强。"""

    def __init__(self):
        self._chat_cache = {}

    # ── 底层 chat ────────────────────────────────────────
    def chat(self, prompt: str, system: str = None, max_tokens: int = 2048,
             temperature: float = 0.2) -> str:
        """OpenAI 兼容 chat 调用。未配置 Key 抛 RefLLMError。"""
        try:
            from core import translator
            key = translator.get_api_key()
            if not key:
                raise RefLLMError(
                    "未配置 API Key，请到「设置 → AI 翻译 → 配置 API」填写后再使用自定义格式。")
            url = translator.get_api_url()
            model = translator.get_model()
        except RefLLMError:
            raise
        except Exception as e:
            raise RefLLMError(f"LLM 配置读取失败：{e}")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            resp = requests.post(
                url,
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                headers={"Authorization": f"Bearer {key}"},
                timeout=90,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
            raise RefLLMError(f"LLM 调用失败（HTTP {resp.status_code}）：{resp.text[:200]}")
        except requests.RequestException as e:
            raise RefLLMError(f"LLM 网络错误：{e}")

    # ── 自定义格式解析 ───────────────────────────────────
    def parse_custom_style(self, requirements: str) -> str:
        """解析期刊格式要求，返回可读的规则摘要（LLM 提取）。"""
        prompt = (
            "你是参考文献格式专家。请从下面的期刊格式要求中，提取出参考文献的\n"
            "条目格式规则，用简洁的中文分条列出（作者顺序、字段顺序、标点、编号方式）。\n"
            "只返回规则，不要其他内容。\n\n"
            f"格式要求：\n{requirements}"
        )
        return self.chat(prompt, max_tokens=1024)

    def format_with_custom_style(self, ref: dict, rules: str) -> str:
        """按用户提供的自定义规则格式化单条参考文献。"""
        ref_json = _ref_to_compact(ref)
        prompt = (
            "请严格按照下面的自定义格式规则，把一条参考文献重新排版。\n"
            f"规则：\n{rules}\n\n"
            f"参考文献：\n{ref_json}\n\n"
            "只返回排版后的条目文本，不要编号、不要解释。"
        )
        text = self.chat(prompt, max_tokens=1024)
        return text.strip() or ref.get("raw", "")

    def smart_repair(self, ref_text: str) -> str:
        """智能修复不规范参考文献。"""
        prompt = (
            "下面这条参考文献格式不规范，请修复为标准格式（保留原信息，补全缺失字段\n"
            "尽量少改动）。只返回修复后的文本，不要编号、不要解释。\n\n"
            f"{ref_text}"
        )
        try:
            text = self.chat(prompt, max_tokens=1024)
            return text.strip() or ref_text
        except Exception:
            return ref_text


def _ref_to_compact(ref: dict) -> str:
    keys = ["type", "authors", "title", "year", "journal", "volume", "issue",
            "pages", "publisher", "conference", "school", "doi", "url"]
    parts = []
    for k in keys:
        v = ref.get(k)
        if v:
            parts.append(f"{k}={v}")
    return "; ".join(parts) if parts else ref.get("raw", "")

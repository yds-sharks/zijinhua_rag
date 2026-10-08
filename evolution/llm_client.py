"""OpenAI 兼容协议的 LLM 统一客户端。

支持 OpenAI / DeepSeek / Qwen 等所有兼容 chat.completions 协议的服务，
仅需在 config.yaml 中调整 api_base 与 model；API Key 通过环境变量注入，不落盘。
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional


class LLMClient:
    """统一 LLM 调用入口。

    用法：
        client = LLMClient(cfg)
        text = client.chat("你是...", "用户问题")
        data = client.chat_json("...", "返回 JSON")
    """

    def __init__(self, cfg: Dict[str, Any]):
        llm_cfg = cfg.get("llm", {})
        self.api_base = llm_cfg.get("api_base", "https://api.openai.com/v1")
        self.api_key_env = llm_cfg.get("api_key_env", "OPENAI_API_KEY")
        self.model = llm_cfg.get("model", "gpt-4o-mini")
        self.temperature = float(llm_cfg.get("temperature", 0.0))
        self.max_retries = int(llm_cfg.get("max_retries", 3))
        self.timeout = float(llm_cfg.get("timeout", 60.0))
        self._client: Optional[Any] = None

    # ---------- 配置 ----------

    @property
    def api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "")
        if not key:
            raise RuntimeError(
                f"未配置 LLM API Key：请先设置环境变量 {self.api_key_env}，"
                f"例如 export {self.api_key_env}='sk-...'"
            )
        return key

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("缺少 openai 包：pip install openai") from exc
            self._client = OpenAI(
                base_url=self.api_base,
                api_key=self.api_key,
                timeout=self.timeout,
            )
        return self._client

    # ---------- 调用 ----------

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        """单轮对话。json_mode=True 时要求模型输出 JSON。"""
        client = self._get_client()
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                kwargs: Dict[str, Any] = dict(
                    model=self.model,
                    temperature=self.temperature,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                resp = client.chat.completions.create(**kwargs)
                return resp.choices[0].message.content or ""
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"LLM 调用失败（重试 {self.max_retries} 次）：{last_exc}") from last_exc

    def chat_json(self, system: str, user: str) -> Any:
        """单轮对话并解析 JSON 输出（带容错）。"""
        return self._loads_lenient(self.chat(system, user, json_mode=True))

    # ---------- 工具 ----------

    @staticmethod
    def _loads_lenient(text: str) -> Any:
        """容错解析 JSON：兼容 ```json 包裹、前后噪声。"""
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise

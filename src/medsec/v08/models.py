"""Raw-text model provider used by both native substrate adapters."""
from __future__ import annotations

import os
from pathlib import Path


def local_deepseek_key() -> str:
    value = os.environ.get("DEEPSEEK_API_KEY", "")
    if value:
        return value
    path = Path(".env")
    if path.is_file():
        for line in path.read_text().splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                value = line.split("=", 1)[1].strip().strip('"\'')
                if value:
                    return value
    raise RuntimeError("DEEPSEEK_API_KEY is missing")


class DeepSeekTextModel:
    def __init__(self, name: str = "deepseek-flash", *, json_mode: bool = False):
        from openai import OpenAI

        self.name = name
        self.json_mode = json_mode
        self.client = OpenAI(api_key=local_deepseek_key(), base_url="https://api.deepseek.com",
                             timeout=120, max_retries=1)
        self.last_response = None

    def __call__(self, messages: list[dict]) -> str:
        options = {"model": self.name, "messages": messages, "temperature": 0,
                   "max_tokens": 1800, "extra_body": {"thinking": {"type": "disabled"}}}
        if self.json_mode:
            options["response_format"] = {"type": "json_object"}
        response = self.client.chat.completions.create(**options)
        content = response.choices[0].message.content
        if not content:
            raise ValueError("empty DeepSeek response")
        self.last_response = {"response_id": response.id, "model": response.model,
                              "usage": response.usage.model_dump() if response.usage else None}
        return content

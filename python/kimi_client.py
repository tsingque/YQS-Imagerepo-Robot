#!/usr/bin/env python3
"""Kimi vision API client for YQS-Imagerepo."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from env_loader import load_env
from glm_client import build_user_prompt, extract_json_object, image_to_data_url


PYTHON_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PYTHON_DIR.parent
DEFAULT_KIMI_ENDPOINT = "https://api.moonshot.cn/v1/chat/completions"
DEFAULT_KIMI_MODEL = "kimi-k2.6"


class KimiClientError(RuntimeError):
    pass


def kimi_api_key() -> str:
    return (
        os.getenv("KIMI_API_KEY", "").strip()
        or os.getenv("MOONSHOT_API_KEY", "").strip()
    )


def recognize_image(image_path: Path, rules_prompt: str, metadata: dict[str, str]) -> dict:
    load_env(PROJECT_DIR)

    api_key = kimi_api_key()
    if not api_key:
        raise KimiClientError("缺少 KIMI_API_KEY 或 MOONSHOT_API_KEY。请在项目根目录 .env 中配置。")

    endpoint = os.getenv("KIMI_API_BASE", DEFAULT_KIMI_ENDPOINT).strip()
    model = os.getenv("KIMI_MODEL", DEFAULT_KIMI_MODEL).strip()
    timeout = int(os.getenv("KIMI_TIMEOUT_SECONDS", os.getenv("GLM_TIMEOUT_SECONDS", "120")))

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": build_user_prompt(rules_prompt, image_path, metadata)},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
                ],
            }
        ],
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise KimiClientError(f"Kimi HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise KimiClientError(f"Kimi 网络请求失败: {exc}") from exc

    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise KimiClientError(f"Kimi 返回结构异常: {response_payload}") from exc

    result = extract_json_object(content)
    result.setdefault("source_file", image_path.name)
    result.setdefault("source_path", metadata.get("source_path", ""))
    usage = response_payload.get("usage")
    if isinstance(usage, dict):
        result["_token_usage"] = {**usage, "model": model}
    return result

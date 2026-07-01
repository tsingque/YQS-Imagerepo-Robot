"""Zhipu GLM vision MCP server for YQS ImageRepoBot."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


DEFAULT_ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEFAULT_MODEL = "glm-5v-turbo"
DEFAULT_PROJECT_ROOT = "/app/yqs_project"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}

mcp = FastMCP("zhipu-vision")


def project_root() -> Path:
    return Path(os.getenv("YQS_PROJECT_ROOT", DEFAULT_PROJECT_ROOT)).resolve()


def load_env_file() -> None:
    env_path = project_root() / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def resolve_project_path(image_path: str) -> Path:
    root = project_root()
    candidate = Path(image_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("图片路径不在 YQS 项目目录内。")
    if not candidate.is_file():
        raise ValueError(f"图片不存在: {image_path}")
    if candidate.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError("只支持图片文件。")
    return candidate


def image_to_data_url(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {"result": value}
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    return None


def call_zhipu_vision(image_path: Path, prompt: str, *, json_mode: bool) -> str:
    load_env_file()
    api_key = os.getenv("GLM_API_KEY", "").strip() or os.getenv("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("缺少 GLM_API_KEY。请在项目根目录 .env 或 DeerFlow 环境变量中配置。")

    endpoint = os.getenv("GLM_API_BASE", DEFAULT_ENDPOINT).strip()
    model = os.getenv("GLM_VISION_MODEL", os.getenv("GLM_MODEL", DEFAULT_MODEL)).strip()
    timeout = int(os.getenv("GLM_TIMEOUT_SECONDS", "120"))
    text_prompt = prompt.strip() or "请用中文简要说明这张图片的内容、用途和关键信息。"

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text_prompt},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
                ],
            }
        ],
        "temperature": 0.2,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"智谱 HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"智谱网络请求失败: {exc}") from exc

    try:
        return response_payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"智谱返回结构异常: {response_payload}") from exc


@mcp.tool()
def zhipu_describe_image(image_path: str, prompt: str = "") -> dict[str, Any]:
    """Use Zhipu GLM vision to understand one image from the YQS project."""
    path = resolve_project_path(image_path)
    content = call_zhipu_vision(path, prompt, json_mode=False)
    return {
        "image_path": path.relative_to(project_root()).as_posix(),
        "model": os.getenv("GLM_VISION_MODEL", os.getenv("GLM_MODEL", DEFAULT_MODEL)),
        "description": content,
    }


@mcp.tool()
def zhipu_recognize_image_json(image_path: str, prompt: str) -> dict[str, Any]:
    """Use Zhipu GLM vision and ask it to return structured JSON for one image."""
    path = resolve_project_path(image_path)
    content = call_zhipu_vision(path, prompt, json_mode=True)
    parsed = extract_json_object(content)
    return {
        "image_path": path.relative_to(project_root()).as_posix(),
        "model": os.getenv("GLM_VISION_MODEL", os.getenv("GLM_MODEL", DEFAULT_MODEL)),
        "result": parsed if parsed is not None else {"raw_text": content},
    }


if __name__ == "__main__":
    mcp.run()

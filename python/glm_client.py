#!/usr/bin/env python3
"""GLM vision API client for YQS-Imagerepo."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from env_loader import load_env


PYTHON_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PYTHON_DIR.parent
DEFAULT_GLM_ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEFAULT_GLM_MODEL = "glm-5v-turbo"


class GLMClientError(RuntimeError):
    pass


def image_to_data_url(image_path: Path) -> str:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def extract_json_object(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start:end + 1])

    raise GLMClientError("GLM 返回内容不是合法 JSON。")


def build_user_prompt(rules_prompt: str, image_path: Path, metadata: dict[str, str]) -> str:
    return "\n".join([
        rules_prompt,
        "",
        "请识别下面这张图片，并仅返回一个合法 JSON 对象作为程序内部中间结果。",
        "注意：最终产物仍然由程序写入 案例素材清单_表格.md、案例素材清单.xlsx 和 素材分辨率.csv。",
        "这批图片主要用于 PPT 自动调用，请默认从正向用途描述图片，优先使用“适合用于…… / 可用于…… / 推荐用于……”等表达。",
        "不要默认输出“不适合用于……”；只有图片严重损坏、明显无关或无法识别时，才在 notes 中说明限制。",
        "如果文件元信息包含飞书多维表格字段，请把“名字”和“描述”作为高置信度人工输入；“是否可商用”只来自表格字段，AI 不负责判断、改变或审核商用权限。",
        "不要输出“版权需确认”“建议确认授权”“不适合商用”等版权审核话术；source_copyright 应按“来源/来源二级分类/有”或“来源/来源二级分类/无”表达。",
        "图片分类必须优先使用四类之一：背景、内容、概念、信息。",
        "",
        "内部 JSON 字段必须包含：",
        "category, suggested_filename, case_name, image_content, ppt_usage, caption, key_data, source_copyright, status, resolution, suggested_folder, quality_status, confidence, notes",
        "",
        "文件元信息：",
        f"- source_file: {image_path.name}",
        f"- source_path: {metadata.get('source_path', '')}",
        f"- resolution: {metadata.get('resolution', '')}",
        f"- file_size: {metadata.get('file_size', '')}",
        f"- bitable_record_id: {metadata.get('record_id', '')}",
        f"- bitable_name: {metadata.get('名字', '')}",
        f"- bitable_project: {metadata.get('项目', '')}",
        f"- bitable_material_name: {metadata.get('素材名', '')}",
        f"- bitable_description: {metadata.get('描述', '')}",
        f"- bitable_source: {metadata.get('来源', '')}",
        f"- bitable_source_subcategory: {metadata.get('来源二级分类', '')}",
        f"- bitable_commercial: {metadata.get('是否可商用') or metadata.get('是否可用', '')}",
        f"- bitable_original_attachment: {metadata.get('原始附件名', '')}",
    ])


def recognize_image(image_path: Path, rules_prompt: str, metadata: dict[str, str]) -> dict:
    load_env(PROJECT_DIR)

    api_key = os.getenv("GLM_API_KEY", "").strip()
    if not api_key:
        raise GLMClientError("缺少 GLM_API_KEY。请在项目根目录 .env 中配置。")

    endpoint = os.getenv("GLM_API_BASE", DEFAULT_GLM_ENDPOINT).strip()
    model = os.getenv("GLM_MODEL", DEFAULT_GLM_MODEL).strip()
    timeout = int(os.getenv("GLM_TIMEOUT_SECONDS", "120"))

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
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
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
        raise GLMClientError(f"GLM HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GLMClientError(f"GLM 网络请求失败: {exc}") from exc

    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GLMClientError(f"GLM 返回结构异常: {response_payload}") from exc

    result = extract_json_object(content)
    result.setdefault("source_file", image_path.name)
    result.setdefault("source_path", metadata.get("source_path", ""))
    usage = response_payload.get("usage")
    if isinstance(usage, dict):
        result["_token_usage"] = {**usage, "model": model}
    return result

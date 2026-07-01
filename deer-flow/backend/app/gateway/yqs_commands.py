"""YQS material workflow command bridge for DeerFlow chat runs."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from fastapi import Request

from app.gateway.deps import get_run_manager, get_stream_bridge
from deerflow.runtime import DisconnectMode, RunRecord, RunStatus

START_KEYWORDS = ("启动素材处理", "启动")
STATUS_KEYWORDS = ("状态", "素材状态", "处理状态")
DEFAULT_TIMEOUT_SECONDS = 60 * 30


def project_root() -> Path:
    configured = os.getenv("YQS_PROJECT_ROOT") or os.getenv("DEER_FLOW_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[4]


def runner_python() -> str:
    configured = os.getenv("YQS_RUNNER_PYTHON")
    if configured:
        return configured
    container_venv_python = Path("/app/backend/.venv/bin/python")
    if container_venv_python.exists():
        return str(container_venv_python)
    return "python3"


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


def extract_latest_user_text(body: Any) -> str:
    raw_input = getattr(body, "input", None) or {}
    messages = raw_input.get("messages") if isinstance(raw_input, dict) else None
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        role = message.get("role") or message.get("type")
        if role in {"user", "human"}:
            return _message_content_to_text(message.get("content")).strip()
    return ""


def classify_yqs_command(text: str) -> str | None:
    normalized = "".join(text.strip().split())
    if not normalized:
        return None
    if normalized in STATUS_KEYWORDS:
        return "status"
    if normalized in START_KEYWORDS or normalized.startswith("启动素材处理"):
        return "start"
    if normalized.startswith("请启动素材处理") or normalized.startswith("帮我启动素材处理"):
        return "start"
    return None


def _parse_runner_stdout(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {"ok": False, "reply": "素材处理流程没有返回结果。"}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        return {"ok": False, "reply": text[-2000:]}


def run_yqs_direct(timeout_seconds: int | None = None) -> dict[str, Any]:
    root = project_root()
    proc = subprocess.run(
        [runner_python(), "python/deerflow_runner.py", "--direct"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=timeout_seconds or DEFAULT_TIMEOUT_SECONDS,
        env={**os.environ, "DEER_FLOW_PROJECT_ROOT": str(root), "YQS_PROJECT_ROOT": str(root)},
        check=False,
    )
    payload = _parse_runner_stdout(proc.stdout)
    if proc.returncode != 0:
        payload.setdefault("ok", False)
        payload.setdefault("reply", "素材处理流程执行失败，请在 Dashboard 查看状态。")
        payload["stderr"] = proc.stderr[-4000:]
    return payload


def read_yqs_status() -> dict[str, Any]:
    root = project_root()
    state_path = root / "runtime" / "deerflow_agent_state.json"
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {"message": "状态文件读取失败。"}
    else:
        state = {"message": "尚未启动素材处理流程。"}

    counts: dict[str, int] = {}
    for key, relative in {
        "raw": "image_compressor/images_raw",
        "compressed": "image_compressor/images_compressed",
        "recognized": "image_compressor/images_recognized",
        "finished": "case_materials",
    }.items():
        directory = root / relative
        counts[key] = sum(1 for path in directory.rglob("*") if path.is_file()) if directory.is_dir() else 0
    return {"ok": True, "state": state, "counts": counts}


def format_status_reply(status: dict[str, Any]) -> str:
    counts = status.get("counts", {})
    state = status.get("state", {})
    running = "运行中" if state.get("running") else "未运行"
    message = str(state.get("message") or "暂无状态。")
    return (
        f"素材处理状态：{running}。\n"
        f"raw {counts.get('raw', 0)} 张，compressed {counts.get('compressed', 0)} 张，"
        f"recognized {counts.get('recognized', 0)} 张，finished {counts.get('finished', 0)} 张。\n"
        f"最近状态：{message}"
    )


def build_assistant_message(run_id: str, reply: str) -> dict[str, Any]:
    return {
        "id": f"yqs-command-{run_id}",
        "type": "ai",
        "role": "assistant",
        "content": reply,
    }


async def persist_assistant_message(request: Request | None, run_id: str, thread_id: str, message: dict[str, Any]) -> None:
    if request is None:
        return
    event_store = getattr(getattr(request, "app", None).state, "run_event_store", None)
    if event_store is None:
        return
    await event_store.put(
        thread_id=thread_id,
        run_id=run_id,
        event_type="llm.ai.response",
        category="message",
        content=message,
        metadata={"caller": "yqs_command"},
    )


async def _run_command_task(run_id: str, thread_id: str, command: str, bridge, run_manager, request: Request | None = None) -> None:
    await run_manager.set_status(run_id, RunStatus.running)
    await bridge.publish(run_id, "metadata", {"run_id": run_id, "thread_id": thread_id})
    try:
        if command == "status":
            reply = format_status_reply(read_yqs_status())
            ok = True
        else:
            result = await asyncio.to_thread(run_yqs_direct)
            ok = bool(result.get("ok"))
            reply = str(result.get("reply") or result.get("message") or "素材处理流程已结束。")
        message = build_assistant_message(run_id, reply)
        await bridge.publish(run_id, "values", {"messages": [message]})
        await bridge.publish(run_id, "messages", [message, {"langgraph_node": "yqs_command"}])
        await persist_assistant_message(request, run_id, thread_id, message)
        await run_manager.set_status(run_id, RunStatus.success if ok else RunStatus.error, error=None if ok else reply)
    except Exception as exc:
        reply = f"素材处理流程执行异常：{exc}"
        message = build_assistant_message(run_id, reply)
        await bridge.publish(run_id, "values", {"messages": [message]})
        await persist_assistant_message(request, run_id, thread_id, message)
        await run_manager.set_status(run_id, RunStatus.error, error=str(exc))
    finally:
        await bridge.publish_end(run_id)


async def start_yqs_command_run(body: Any, thread_id: str, request: Request, owner_user_id: str | None = None) -> RunRecord | None:
    command = classify_yqs_command(extract_latest_user_text(body))
    if command is None:
        return None

    disconnect = DisconnectMode.cancel if getattr(body, "on_disconnect", "cancel") == "cancel" else DisconnectMode.continue_
    run_manager = get_run_manager(request)
    record = await run_manager.create_or_reject(
        thread_id,
        getattr(body, "assistant_id", None),
        on_disconnect=disconnect,
        metadata={**(getattr(body, "metadata", None) or {}), "yqs_command": command},
        kwargs={"input": getattr(body, "input", None), "config": getattr(body, "config", None)},
        multitask_strategy=getattr(body, "multitask_strategy", "reject"),
        user_id=owner_user_id,
    )
    bridge = get_stream_bridge(request)
    record.task = asyncio.create_task(_run_command_task(record.run_id, thread_id, command, bridge, run_manager, request))
    return record

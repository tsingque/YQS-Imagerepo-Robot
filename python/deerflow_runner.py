#!/usr/bin/env python3
"""YQS DeerFlow workflow runner."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

PYTHON_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PYTHON_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from env_loader import load_env
import yqs_deerflow_tools as yqs_tools

RUNTIME_DIR = PROJECT_DIR / "runtime"
STATE_PATH = RUNTIME_DIR / "deerflow_agent_state.json"
LOCK_PATH = RUNTIME_DIR / "deerflow_agent_state.lock"

WORKFLOW_PROMPT = """你是 YQS-Imagerepo 的素材处理调度员。请按固定顺序完成一次素材处理：
1. 先调用 sync_bitable_to_raw，从飞书多维表格拉取待处理图片附件到 images_raw；如果未配置多维表格则跳过。
2. 再查看素材库状态。
3. 调用 compress_raw_images，把 images_raw 压缩到 images_compressed。飞书多维表格和飞书机器人都会把图片放进 images_raw，不要寻找或读取 trans_repo。
4. 调用 run_glm_recognition，对压缩后的图片进行识图。不要直接读取原图，不要修改识图规则。
5. 再查看一次素材库状态。
6. 如果飞书已配置，发送一条简短中文总结。

不要调用 append_md_table_to_xlsx，除非明确发现只是要补录已有 Markdown 表格。
最终用中文返回本次处理摘要，包括 raw 更新状态、压缩、识图成功/失败和输出位置。
"""


def now_label() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {
            "running": False,
            "mode": "",
            "message": "尚未启动 DeerFlow 托管处理。",
            "updated_at": "",
            "started_at": "",
            "finished_at": "",
            "summary": {},
            "error": "",
        }
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"running": False, "message": "DeerFlow 状态文件读取失败。"}


def write_state(**updates: Any) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    state = read_state()
    state.update(updates)
    state["updated_at"] = now_label()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _status_count(status: dict[str, Any], key: str) -> int:
    counts = status.get("counts", {}) if isinstance(status, dict) else {}
    try:
        return int(counts.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _first_errors(result: dict[str, Any], limit: int = 3) -> list[str]:
    summary = result.get("summary", {}) if isinstance(result, dict) else {}
    errors = summary.get("errors", []) if isinstance(summary, dict) else []
    formatted: list[str] = []
    for item in errors[:limit] if isinstance(errors, list) else []:
        if isinstance(item, dict):
            name = str(item.get("file", "")).strip()
            error = str(item.get("error", "")).strip()
            formatted.append(f"{name}: {error}" if name else error)
        else:
            formatted.append(str(item))
    return [text for text in formatted if text]


def _recognition_counts(result: dict[str, Any]) -> tuple[int, int]:
    summary = result.get("summary", {}) if isinstance(result, dict) else {}
    try:
        completed = int(summary.get("completed", 0) or 0)
    except (TypeError, ValueError):
        completed = 0
    try:
        failed = int(summary.get("failed", 0) or 0)
    except (TypeError, ValueError):
        failed = 0
    return completed, failed


def _token_usage_text(result: dict[str, Any]) -> str:
    summary = result.get("summary", {}) if isinstance(result, dict) else {}
    usage = summary.get("token_usage", {}) if isinstance(summary, dict) else {}
    try:
        total = int(usage.get("total_tokens", 0) or 0)
    except (TypeError, ValueError):
        total = 0
    if total <= 0:
        return ""
    prompt = int(usage.get("prompt_tokens", 0) or 0)
    completion = int(usage.get("completion_tokens", 0) or 0)
    calls = int(usage.get("calls", 0) or 0)
    return f"本次 AI token 用量：{total}（输入 {prompt}，输出 {completion}，调用 {calls} 次）。"


def _reply_for_result(result: dict[str, Any]) -> str:
    if result.get("reply"):
        return str(result["reply"])
    if result.get("message"):
        return str(result["message"])
    return "素材处理流程已结束。"


class WorkflowLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: int | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self.fd, str(os.getpid()).encode("utf-8"))
            return True
        except FileExistsError:
            return False

    def release(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def _run_with_agent() -> dict[str, Any]:
    from deerflow.client import DeerFlowClient

    write_state(mode="agent", message="DeerFlow Agent 正在编排素材处理。")
    client = DeerFlowClient(
        config_path=str(PROJECT_DIR / "config.yaml"),
        model_name=os.getenv("YQS_DEERFLOW_MODEL", "glm-agent"),
        thinking_enabled=False,
        subagent_enabled=False,
        plan_mode=False,
        environment="local",
    )
    response = client.chat(WORKFLOW_PROMPT, thread_id="yqs-imagerepo-workflow")
    return {
        "ok": True,
        "mode": "agent",
        "message": "DeerFlow Agent 托管处理完成。",
        "agent_response": response,
        "status": yqs_tools.repository_status(),
    }


def _run_direct_fallback(reason: str = "") -> dict[str, Any]:
    write_state(mode="direct-fallback", message="正在用 DeerFlow 工具顺序执行素材处理。", fallback_reason=reason)
    steps: list[dict[str, Any]] = []

    def run_step(name: str, fn) -> dict[str, Any]:
        write_state(message=f"正在执行：{name}")
        try:
            result = fn()
        except Exception as exc:
            result = {"ok": False, "error": str(exc), "traceback": traceback.format_exc(limit=5)}
        steps.append({"name": name, "result": result})
        return result

    sync_result = run_step("同步飞书多维表格", yqs_tools.sync_bitable_to_raw)
    if not sync_result.get("ok", False):
        errors = sync_result.get("errors", []) if isinstance(sync_result, dict) else []
        error_text = ""
        if isinstance(errors, list) and errors:
            first = errors[0]
            error_text = str(first.get("error") if isinstance(first, dict) else first)
        reply = "多维表格同步失败，请检查飞书多维表格权限和配置。"
        if error_text:
            reply += f"错误摘要：{error_text}"
        return {
            "ok": False,
            "mode": "direct-fallback",
            "message": "多维表格同步失败。",
            "reply": reply,
            "fallback_reason": reason,
            "steps": steps,
            "status": sync_result,
        }

    initial_status = run_step("查看素材库状态", yqs_tools.repository_status)
    raw_before = _status_count(initial_status, "raw")
    compressed_before = _status_count(initial_status, "compressed")
    if raw_before <= 0 and compressed_before <= 0:
        reply = "暂无图片，请先通过飞书发送图片。"
        return {
            "ok": True,
            "mode": "direct-fallback",
            "message": reply,
            "reply": reply,
            "skipped": True,
            "fallback_reason": reason,
            "steps": steps,
            "status": initial_status,
        }

    compress_result: dict[str, Any] = {"ok": True, "skipped": True, "message": "raw 为空，跳过压缩。"}
    if raw_before > 0:
        compress_result = run_step("压缩 images_raw", yqs_tools.compress_raw_images)
        if not compress_result.get("ok"):
            reply = "素材处理流程未完成：图片压缩失败，请在 Dashboard 查看错误详情。"
            return {
                "ok": False,
                "mode": "direct-fallback",
                "message": "压缩失败。",
                "reply": reply,
                "fallback_reason": reason,
                "steps": steps,
                "status": initial_status,
            }
    else:
        steps.append({"name": "压缩 images_raw", "result": compress_result})

    after_compress_status = run_step("查看压缩后状态", yqs_tools.repository_status)
    compressed_ready = _status_count(after_compress_status, "compressed")
    if compressed_ready <= 0:
        reply = "暂无图片，请先压缩。"
        return {
            "ok": True,
            "mode": "direct-fallback",
            "message": reply,
            "reply": reply,
            "skipped": True,
            "fallback_reason": reason,
            "steps": steps,
            "status": after_compress_status,
        }

    recognition_result = run_step("AI 识图压缩图", lambda: yqs_tools.run_glm_recognition(limit=0, dry_run=False))

    final_status = run_step("查看处理后状态", yqs_tools.repository_status)
    feishu_status = final_status.get("feishu", {}) if isinstance(final_status, dict) else {}
    completed, failed = _recognition_counts(recognition_result)
    deleted_raw = compress_result.get("deleted_raw", 0)
    compressed_count = compress_result.get("compressed", compress_result.get("compressed_after", compressed_ready))
    output_paths = recognition_result.get("outputs", {}) if isinstance(recognition_result, dict) else {}
    error_lines = _first_errors(recognition_result)
    token_usage_text = _token_usage_text(recognition_result)
    reply_parts = [
        "已启动素材处理流程：",
        f"raw 图片 {raw_before} 张，压缩成功 {compressed_count} 张，删除 raw 原图 {deleted_raw} 张，AI 识图成功 {completed} 张，失败 {failed} 张。",
    ]
    if output_paths:
        reply_parts.append(
            "结果已写入 "
            + "、".join(str(value) for value in output_paths.values() if value)
            + "。"
        )
    if token_usage_text:
        reply_parts.append(token_usage_text)
    if error_lines:
        reply_parts.append("错误摘要：" + "；".join(error_lines) + "。")
    if feishu_status.get("configured"):
        run_step(
            "发送飞书总结",
            lambda: yqs_tools.send_feishu_summary("".join(reply_parts)),
        )
        reply_parts.append("已发送飞书通知。")

    ok = all(step["result"].get("ok", False) or step["result"].get("skipped") for step in steps)
    reply = "".join(reply_parts)
    return {
        "ok": ok,
        "mode": "direct-fallback",
        "message": "DeerFlow 工具顺序处理完成。" if ok else "托管处理完成，但有步骤失败。",
        "reply": reply,
        "fallback_reason": reason,
        "steps": steps,
        "status": final_status,
    }


def run_managed_workflow(force_direct: bool = False) -> dict[str, Any]:
    load_env(PROJECT_DIR)
    lock = WorkflowLock(LOCK_PATH)
    if not lock.acquire():
        reply = "素材处理任务正在运行，请稍后查看状态。"
        return {
            "ok": False,
            "running": True,
            "message": reply,
            "reply": reply,
            "status": read_state(),
        }
    write_state(
        running=True,
        started_at=now_label(),
        finished_at="",
        error="",
        summary={},
        message="DeerFlow 托管处理已启动。",
    )
    try:
        if force_direct or os.getenv("YQS_DEERFLOW_MODE", "agent").lower() in {"direct", "fallback"}:
            summary = _run_direct_fallback("YQS_DEERFLOW_MODE=direct")
        else:
            try:
                summary = _run_with_agent()
            except Exception as exc:
                summary = _run_direct_fallback(f"DeerFlow Agent 暂不可用，已降级执行：{exc}")
        write_state(
            running=False,
            finished_at=now_label(),
            message=summary.get("reply") or summary.get("message", "托管处理完成。"),
            summary=summary,
            error="" if summary.get("ok") else summary.get("message", ""),
        )
        return summary
    except Exception as exc:
        error = str(exc)
        write_state(
            running=False,
            finished_at=now_label(),
            message=f"DeerFlow 托管处理失败：{error}",
            error=error,
            summary={"ok": False, "error": error, "traceback": traceback.format_exc(limit=8)},
        )
        raise
    finally:
        lock.release()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the YQS DeerFlow-managed material workflow.")
    parser.add_argument("--direct", action="store_true", help="Run the deterministic tool sequence without calling the DeerFlow agent model.")
    parser.add_argument("--status", action="store_true", help="Print the current DeerFlow workflow status.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.status:
        print(json.dumps(read_state(), ensure_ascii=False, indent=2))
        return
    result = run_managed_workflow(force_direct=args.direct)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

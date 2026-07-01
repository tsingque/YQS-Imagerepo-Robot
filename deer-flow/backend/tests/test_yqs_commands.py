from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.gateway import yqs_commands
from deerflow.runtime import MemoryStreamBridge, RunManager, RunStatus
from deerflow.runtime.events.store.memory import MemoryRunEventStore


def _body(text: str):
    return SimpleNamespace(
        input={"messages": [{"role": "user", "content": text}]},
        assistant_id=None,
        metadata={},
        config={},
        multitask_strategy="reject",
        on_disconnect="cancel",
    )


def test_classify_yqs_command_detects_start_and_status_only():
    assert yqs_commands.classify_yqs_command("启动") == "start"
    assert yqs_commands.classify_yqs_command("请启动素材处理") == "start"
    assert yqs_commands.classify_yqs_command("状态") == "status"
    assert yqs_commands.classify_yqs_command("帮我写一段启动仪式文案") is None


def test_runner_python_prefers_configured_executable(monkeypatch):
    monkeypatch.setenv("YQS_RUNNER_PYTHON", "/tmp/yqs-python")
    assert yqs_commands.runner_python() == "/tmp/yqs-python"


@pytest.mark.asyncio
async def test_start_yqs_command_run_publishes_summary_events(monkeypatch):
    bridge = MemoryStreamBridge()
    run_manager = RunManager()
    event_store = MemoryRunEventStore()
    request = MagicMock()
    request.app.state.stream_bridge = bridge
    request.app.state.run_manager = run_manager
    request.app.state.run_event_store = event_store

    monkeypatch.setattr(yqs_commands, "run_yqs_direct", lambda timeout_seconds=None: {"ok": True, "reply": "已启动素材处理流程：成功 2 张。"})

    record = await yqs_commands.start_yqs_command_run(_body("启动"), "thread-yqs", request, owner_user_id=None)
    assert record is not None
    await record.task

    assert record.status == RunStatus.success
    events = []
    async for entry in bridge.subscribe(record.run_id):
        events.append(entry)
    assert [event.event for event in events] == ["metadata", "values", "messages", "__end__"]
    assert events[1].data["messages"][-1]["content"] == "已启动素材处理流程：成功 2 张。"
    assert events[1].data["messages"][-1]["id"] == f"yqs-command-{record.run_id}"
    assert events[2].data[0]["id"] == f"yqs-command-{record.run_id}"
    persisted = await event_store.list_messages_by_run("thread-yqs", record.run_id)
    assert persisted[-1]["event_type"] == "llm.ai.response"
    assert persisted[-1]["content"]["content"] == "已启动素材处理流程：成功 2 张。"


@pytest.mark.asyncio
async def test_start_yqs_command_run_returns_none_for_normal_chat():
    request = MagicMock()
    request.app.state.stream_bridge = MemoryStreamBridge()
    request.app.state.run_manager = RunManager()
    assert await yqs_commands.start_yqs_command_run(_body("你好"), "thread-yqs", request, owner_user_id=None) is None

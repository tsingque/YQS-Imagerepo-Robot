import asyncio
import json
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.commands import KNOWN_CHANNEL_COMMANDS
from app.channels.feishu import FeishuChannel
from app.channels.message_bus import (
    PENDING_CLARIFICATION_METADATA_KEY,
    RESOLVED_FROM_PENDING_CLARIFICATION_METADATA_KEY,
    InboundMessage,
    MessageBus,
    OutboundMessage,
)
from app.channels.store import ChannelStore


def _pending(
    topic_id: str,
    *,
    thread_id: str | None = None,
    source_message_id: str | None = None,
    card_message_id: str | None = None,
    created_at: float = 9999999999,
) -> dict:
    return {
        "thread_id": thread_id or f"deer-thread-{topic_id}",
        "topic_id": topic_id,
        "source_message_id": source_message_id or topic_id,
        "card_message_id": card_message_id or f"card-{topic_id}",
        "created_at": created_at,
    }


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_feishu_on_message_plain_text():
    bus = MessageBus()
    config = {"app_id": "test", "app_secret": "test"}
    channel = FeishuChannel(bus, config)

    # Create mock event
    event = MagicMock()
    event.event.message.chat_id = "chat_1"
    event.event.message.message_id = "msg_1"
    event.event.message.root_id = None
    event.event.message.chat_type = "p2p"
    event.event.sender.sender_id.open_id = "user_1"

    # Plain text content
    content_dict = {"text": "Hello world"}
    event.event.message.content = json.dumps(content_dict)

    # Call _on_message
    channel._on_message(event)

    # Since main_loop isn't running in this synchronous test, we can't easily assert on bus,
    # but we can intercept _make_inbound to check the parsed text.
    with pytest.MonkeyPatch.context() as m:
        mock_make_inbound = MagicMock()
        m.setattr(channel, "_make_inbound", mock_make_inbound)
        channel._on_message(event)

        mock_make_inbound.assert_called_once()
        assert mock_make_inbound.call_args[1]["text"] == "Hello world"


def test_feishu_is_not_running_when_ws_thread_exits():
    bus = MessageBus()
    channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test"})
    channel._running = True
    channel._thread = MagicMock()
    channel._thread.is_alive.return_value = False

    assert channel.is_running is False


def test_feishu_event_handler_ignores_non_content_message_events():
    import lark_oapi as lark

    bus = MessageBus()
    channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test"})

    event_handler = channel._build_event_handler(lark)

    assert "p2.im.message.receive_v1" in event_handler._processorMap
    assert "p2.im.message.message_read_v1" in event_handler._processorMap
    assert "p2.im.message.reaction.created_v1" in event_handler._processorMap
    assert "p2.im.message.reaction.deleted_v1" in event_handler._processorMap
    assert "p2.im.message.recalled_v1" in event_handler._processorMap


def test_feishu_on_message_rich_text():
    bus = MessageBus()
    config = {"app_id": "test", "app_secret": "test"}
    channel = FeishuChannel(bus, config)

    # Create mock event
    event = MagicMock()
    event.event.message.chat_id = "chat_1"
    event.event.message.message_id = "msg_1"
    event.event.message.root_id = None
    event.event.message.chat_type = "group"
    event.event.sender.sender_id.open_id = "user_1"

    # Rich text content (topic group / post)
    content_dict = {"content": [[{"tag": "text", "text": "Paragraph 1, part 1."}, {"tag": "text", "text": "Paragraph 1, part 2."}], [{"tag": "at", "text": "@bot"}, {"tag": "text", "text": " Paragraph 2."}]]}
    event.event.message.content = json.dumps(content_dict)

    with pytest.MonkeyPatch.context() as m:
        mock_make_inbound = MagicMock()
        m.setattr(channel, "_make_inbound", mock_make_inbound)
        channel._on_message(event)

        mock_make_inbound.assert_called_once()
        parsed_text = mock_make_inbound.call_args[1]["text"]

        # Expected text:
        # Paragraph 1, part 1. Paragraph 1, part 2.
        #
        # Paragraph 2.
        assert "Paragraph 1, part 1. Paragraph 1, part 2." in parsed_text
        assert "Paragraph 2." in parsed_text
        assert "@bot" not in parsed_text
        assert "\n\n" in parsed_text


def test_feishu_receive_file_replaces_placeholders_in_order():
    async def go():
        bus = MessageBus()
        channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test"})

        msg = InboundMessage(
            channel_name="feishu",
            chat_id="chat_1",
            user_id="user_1",
            text="before [image] middle [file] after",
            thread_ts="msg_1",
            files=[{"image_key": "img_key"}, {"file_key": "file_key"}],
        )

        channel._receive_single_file = AsyncMock(side_effect=["/mnt/user-data/uploads/a.png", "/mnt/user-data/uploads/b.pdf"])

        result = await channel.receive_file(msg, "thread_1")

        assert result.text == "before /mnt/user-data/uploads/a.png middle /mnt/user-data/uploads/b.pdf after"

    _run(go())


def test_feishu_receive_file_syncs_sandbox_with_explicit_user_id(tmp_path, monkeypatch):
    async def go():
        from deerflow.config.paths import Paths

        bus = MessageBus()
        channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test"})
        channel._GetMessageResourceRequest = MagicMock()
        builder = MagicMock()
        builder.message_id.return_value = builder
        builder.file_key.return_value = builder
        builder.type.return_value = builder
        builder.build.return_value = object()
        channel._GetMessageResourceRequest.builder.return_value = builder

        response = MagicMock()
        response.success.return_value = True
        response.file = BytesIO(b"file-bytes")
        response.file_name = "report.md"
        channel._api_client = MagicMock()
        channel._api_client.im.v1.message_resource.get.return_value = response

        provider = MagicMock()
        provider.acquire.return_value = "aio-1"
        sandbox = MagicMock()
        provider.get.return_value = sandbox

        monkeypatch.setattr("app.channels.feishu.get_paths", lambda: Paths(base_dir=tmp_path))
        monkeypatch.setattr("app.channels.feishu.get_sandbox_provider", lambda: provider)
        monkeypatch.setattr("app.channels.feishu.get_effective_user_id", lambda: "default")

        virtual_path = await channel._receive_single_file("message-1", "file-key", "file", "thread-1", user_id="ou-user")

        assert virtual_path == "/mnt/user-data/uploads/report.md"
        assert (tmp_path / "users" / "ou-user" / "threads" / "thread-1" / "user-data" / "uploads" / "report.md").read_bytes() == b"file-bytes"
        provider.acquire.assert_called_once_with("thread-1", user_id="ou-user")
        sandbox.update_file.assert_called_once_with("/mnt/user-data/uploads/report.md", b"file-bytes")

    _run(go())


def test_feishu_on_message_extracts_image_and_file_keys():
    bus = MessageBus()
    channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test"})

    event = MagicMock()
    event.event.message.chat_id = "chat_1"
    event.event.message.message_id = "msg_1"
    event.event.message.root_id = None
    event.event.message.chat_type = "p2p"
    event.event.sender.sender_id.open_id = "user_1"

    # Rich text with one image and one file element.
    event.event.message.content = json.dumps(
        {
            "content": [
                [
                    {"tag": "text", "text": "See"},
                    {"tag": "img", "image_key": "img_123"},
                    {"tag": "file", "file_key": "file_456"},
                ]
            ]
        }
    )

    with pytest.MonkeyPatch.context() as m:
        mock_make_inbound = MagicMock()
        m.setattr(channel, "_make_inbound", mock_make_inbound)
        channel._on_message(event)

        mock_make_inbound.assert_called_once()
        files = mock_make_inbound.call_args[1]["files"]
        assert files == [{"image_key": "img_123"}, {"file_key": "file_456"}]
        assert "[image]" in mock_make_inbound.call_args[1]["text"]
        assert "[file]" in mock_make_inbound.call_args[1]["text"]


def test_feishu_on_message_reuses_stored_parent_topic_for_card_replies():
    bus = MessageBus()
    store = ChannelStore(path=Path(tempfile.mkdtemp()) / "store.json")
    store.set_thread_id(
        "feishu",
        "chat_1",
        "deer-thread-1",
        topic_id="om_clarification_card",
        user_id="user_1",
    )
    channel = FeishuChannel(
        bus,
        {"app_id": "test", "app_secret": "test", "channel_store": store},
    )

    event = MagicMock()
    event.event.message.chat_id = "chat_1"
    event.event.message.message_id = "msg_reply"
    event.event.message.root_id = "om_unknown_root"
    event.event.message.parent_id = "om_clarification_card"
    event.event.message.thread_id = None
    event.event.sender.sender_id.open_id = "user_1"
    event.event.message.content = json.dumps({"text": "prod"})

    with pytest.MonkeyPatch.context() as m:
        mock_make_inbound = MagicMock()
        m.setattr(channel, "_make_inbound", mock_make_inbound)
        channel._on_message(event)

        inbound = mock_make_inbound.return_value
        assert inbound.topic_id == "om_clarification_card"
        assert mock_make_inbound.call_args.kwargs["metadata"]["topic_id"] == "om_clarification_card"


def _make_text_event(
    text: str,
    *,
    chat_id: str = "chat_1",
    message_id: str = "msg_1",
    user_id: str = "user_1",
    chat_type: str = "group",
    root_id: str | None = None,
    parent_id: str | None = None,
    thread_id: str | None = None,
):
    event = MagicMock()
    event.event.message.chat_id = chat_id
    event.event.message.message_id = message_id
    event.event.message.root_id = root_id
    event.event.message.parent_id = parent_id
    event.event.message.thread_id = thread_id
    event.event.message.chat_type = chat_type
    event.event.sender.sender_id.open_id = user_id
    event.event.message.content = json.dumps({"text": text})
    return event


def test_feishu_group_plain_text_without_mention_is_ignored():
    bus = MessageBus()
    channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test"})

    with pytest.MonkeyPatch.context() as m:
        mock_make_inbound = MagicMock()
        m.setattr(channel, "_make_inbound", mock_make_inbound)
        channel._on_message(_make_text_event("普通消息", message_id="msg_plain", chat_type="group"))

        mock_make_inbound.assert_not_called()


def test_feishu_group_mention_text_is_published_without_mention_prefix():
    bus = MessageBus()
    channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test"})

    event = _make_text_event("", message_id="msg_mention", chat_type="group")
    event.event.message.content = json.dumps({"content": [[{"tag": "at", "text": "@机器人"}, {"tag": "text", "text": " 状态"}]]})

    with pytest.MonkeyPatch.context() as m:
        mock_make_inbound = MagicMock()
        m.setattr(channel, "_make_inbound", mock_make_inbound)
        channel._on_message(event)

        mock_make_inbound.assert_called_once()
        assert mock_make_inbound.call_args.kwargs["text"] == "状态"


def test_feishu_group_yqs_command_without_mention_is_still_published():
    bus = MessageBus()
    channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test"})

    with pytest.MonkeyPatch.context() as m:
        mock_make_inbound = MagicMock()
        m.setattr(channel, "_make_inbound", mock_make_inbound)
        channel._on_message(_make_text_event("启动", message_id="msg_start", chat_type="group"))

        mock_make_inbound.assert_called_once()
        assert mock_make_inbound.call_args.kwargs["text"] == "启动"


def test_feishu_form_command_replies_with_bitable_form_link(monkeypatch):
    async def go():
        bus = MessageBus()
        channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test"})
        channel._reply_card = AsyncMock(return_value="card_1")
        monkeypatch.setenv("FEISHU_BITABLE_FORM_URL", "https://example.feishu.cn/form")

        handled = await channel._handle_yqs_direct_command("表单", "msg_form", "chat_1")

        assert handled is True
        channel._reply_card.assert_called_once()
        assert "图片上传表单" in channel._reply_card.call_args.args[1]
        assert "https://example.feishu.cn/form" in channel._reply_card.call_args.args[1]

    _run(go())


def test_feishu_echo_command_syncs_knowledge_base(monkeypatch):
    async def go():
        bus = MessageBus()
        channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test"})
        channel._reply_card = AsyncMock(return_value="card_1")
        sync = MagicMock(
            return_value={
                "ok": True,
                "root": "/tmp/yqs/case_materials",
                "space_name": "YQS PPT 图片素材库",
                "space_url": "https://example.feishu.cn/drive/folder/folder_1",
                "created_space": True,
                "total": 3,
                "uploaded": 2,
                "skipped": 1,
                "created_folders": 2,
                "reader_granted": True,
                "folder_permission_granted": True,
                "folder_permission_role": "full_access",
                "errors": [],
            }
        )
        monkeypatch.setattr(channel, "_sync_yqs_echo_target", sync)

        handled = await channel._handle_yqs_direct_command("回显", "msg_echo", "chat_1")

        assert handled is True
        assert sync.call_count == 1
        assert sync.call_args.args == ("",)
        card = channel._reply_card.call_args.args[1]
        assert "飞书文件夹回显完成" in card
        assert "飞书文件夹：YQS PPT 图片素材库" in card
        assert "[打开文件夹](https://example.feishu.cn/drive/folder/folder_1)" in card
        assert "云盘权限：已给本次发起人开通可管理权限（可修改/删除）" in card
        assert "已上传：2 张" in card
        assert "已跳过：1 张" in card

    _run(go())


def test_feishu_plain_reply_consumes_pending_clarification_topic():
    bus = MessageBus()
    store = ChannelStore(path=Path(tempfile.mkdtemp()) / "store.json")
    store.set_thread_id("feishu", "chat_1", "deer-thread-1", topic_id="om_original", user_id="user_1")
    channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test", "channel_store": store})
    channel._pending_clarifications[channel._pending_key("chat_1", "user_1")] = [_pending("om_original", thread_id="deer-thread-1", card_message_id="om_card")]

    with pytest.MonkeyPatch.context() as m:
        mock_make_inbound = MagicMock()
        m.setattr(channel, "_make_inbound", mock_make_inbound)
        channel._on_message(_make_text_event("2", message_id="msg_plain_2"))

        inbound = mock_make_inbound.return_value
        metadata = mock_make_inbound.call_args.kwargs["metadata"]
        assert inbound.topic_id == "om_original"
        assert metadata["topic_id"] == "om_original"
        assert metadata[RESOLVED_FROM_PENDING_CLARIFICATION_METADATA_KEY] is True
        assert channel._pending_key("chat_1", "user_1") not in channel._pending_clarifications


def test_feishu_pending_clarification_is_consumed_once():
    bus = MessageBus()
    channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test"})
    channel._pending_clarifications[channel._pending_key("chat_1", "user_1")] = [_pending("om_original", thread_id="deer-thread-1", card_message_id="om_card")]

    with pytest.MonkeyPatch.context() as m:
        created = []

        def fake_make_inbound(**kwargs):
            inbound = InboundMessage(channel_name="feishu", **kwargs)
            created.append(inbound)
            return inbound

        mock_make_inbound = MagicMock(side_effect=fake_make_inbound)
        m.setattr(channel, "_make_inbound", mock_make_inbound)
        channel._on_message(_make_text_event("2", message_id="msg_first"))
        channel._on_message(_make_text_event("next", message_id="msg_second"))

        first_inbound = created[0]
        first_metadata = mock_make_inbound.call_args_list[0].kwargs["metadata"]
        assert first_inbound.topic_id == "om_original"
        assert first_metadata["topic_id"] == "om_original"
        assert first_metadata[RESOLVED_FROM_PENDING_CLARIFICATION_METADATA_KEY] is True
        assert len(created) == 1


def test_feishu_expired_pending_clarification_is_ignored(monkeypatch):
    bus = MessageBus()
    channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test"})
    monkeypatch.setattr("app.channels.feishu.time.time", lambda: 10_000.0)
    channel._pending_clarifications[channel._pending_key("chat_1", "user_1")] = [_pending("om_original", thread_id="deer-thread-1", card_message_id="om_card", created_at=0.0)]

    with pytest.MonkeyPatch.context() as m:
        mock_make_inbound = MagicMock()
        m.setattr(channel, "_make_inbound", mock_make_inbound)
        channel._on_message(_make_text_event("2", message_id="msg_plain_2"))

        metadata = mock_make_inbound.call_args.kwargs["metadata"]
        assert metadata["topic_id"] == "msg_plain_2"
        assert metadata[RESOLVED_FROM_PENDING_CLARIFICATION_METADATA_KEY] is False
        assert channel._pending_key("chat_1", "user_1") not in channel._pending_clarifications


def test_feishu_command_does_not_consume_pending_clarification():
    bus = MessageBus()
    channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test"})
    key = channel._pending_key("chat_1", "user_1")
    channel._pending_clarifications[key] = [_pending("om_original", thread_id="deer-thread-1", card_message_id="om_card")]

    with pytest.MonkeyPatch.context() as m:
        mock_make_inbound = MagicMock()
        m.setattr(channel, "_make_inbound", mock_make_inbound)
        channel._on_message(_make_text_event("/status", message_id="msg_command"))

        metadata = mock_make_inbound.call_args.kwargs["metadata"]
        assert mock_make_inbound.call_args.kwargs["msg_type"].value == "command"
        assert metadata["topic_id"] == "msg_command"
        assert metadata[RESOLVED_FROM_PENDING_CLARIFICATION_METADATA_KEY] is False
        assert key in channel._pending_clarifications


def test_feishu_remembers_pending_clarification_only_after_final_card_success():
    bus = MessageBus()
    channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test"})
    outbound = OutboundMessage(
        channel_name="feishu",
        chat_id="chat_1",
        thread_id="deer-thread-1",
        text="clarify?",
        thread_ts="om_original",
        metadata={
            PENDING_CLARIFICATION_METADATA_KEY: True,
            "user_id": "user_1",
            "topic_id": "om_original",
            "message_id": "om_original",
        },
    )

    channel._remember_pending_clarification(outbound, None)
    assert channel._pending_clarifications == {}

    channel._remember_pending_clarification(outbound, "om_card")
    pending = channel._pending_clarifications[channel._pending_key("chat_1", "user_1")][0]
    assert pending["topic_id"] == "om_original"
    assert pending["thread_id"] == "deer-thread-1"
    assert pending["card_message_id"] == "om_card"


def test_feishu_multiple_pending_clarifications_are_consumed_in_order():
    bus = MessageBus()
    channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test"})
    key = channel._pending_key("chat_1", "user_1")
    channel._pending_clarifications[key] = [
        _pending("om_first", thread_id="deer-thread-1"),
        _pending("om_second", thread_id="deer-thread-2"),
    ]

    with pytest.MonkeyPatch.context() as m:
        created = []

        def fake_make_inbound(**kwargs):
            inbound = InboundMessage(channel_name="feishu", **kwargs)
            created.append(inbound)
            return inbound

        m.setattr(channel, "_make_inbound", MagicMock(side_effect=fake_make_inbound))
        channel._on_message(_make_text_event("first answer", message_id="msg_first"))
        channel._on_message(_make_text_event("second answer", message_id="msg_second"))

        assert [msg.topic_id for msg in created] == ["om_first", "om_second"]
        assert key not in channel._pending_clarifications


def test_feishu_explicit_reply_prefers_stored_mapping_over_pending():
    bus = MessageBus()
    store = ChannelStore(path=Path(tempfile.mkdtemp()) / "store.json")
    store.set_thread_id("feishu", "chat_1", "deer-thread-card", topic_id="om_card", user_id="user_1")
    channel = FeishuChannel(bus, {"app_id": "test", "app_secret": "test", "channel_store": store})
    key = channel._pending_key("chat_1", "user_1")
    channel._pending_clarifications[key] = [_pending("om_pending", thread_id="deer-thread-pending")]

    with pytest.MonkeyPatch.context() as m:
        mock_make_inbound = MagicMock()
        m.setattr(channel, "_make_inbound", mock_make_inbound)
        channel._on_message(
            _make_text_event(
                "answer",
                message_id="msg_reply",
                root_id="om_unknown",
                parent_id="om_card",
            )
        )

        metadata = mock_make_inbound.call_args.kwargs["metadata"]
        assert metadata["topic_id"] == "om_card"
        assert metadata[RESOLVED_FROM_PENDING_CLARIFICATION_METADATA_KEY] is False
        assert key in channel._pending_clarifications


@pytest.mark.parametrize("command", sorted(KNOWN_CHANNEL_COMMANDS))
def test_feishu_recognizes_all_known_slash_commands(command):
    """Every entry in KNOWN_CHANNEL_COMMANDS must be classified as a command."""
    bus = MessageBus()
    config = {"app_id": "test", "app_secret": "test"}
    channel = FeishuChannel(bus, config)

    event = MagicMock()
    event.event.message.chat_id = "chat_1"
    event.event.message.message_id = "msg_1"
    event.event.message.root_id = None
    event.event.message.chat_type = "p2p"
    event.event.sender.sender_id.open_id = "user_1"
    event.event.message.content = json.dumps({"text": command})

    with pytest.MonkeyPatch.context() as m:
        mock_make_inbound = MagicMock()
        m.setattr(channel, "_make_inbound", mock_make_inbound)
        channel._on_message(event)

        mock_make_inbound.assert_called_once()
        assert mock_make_inbound.call_args[1]["msg_type"].value == "command", f"{command!r} should be classified as COMMAND"


@pytest.mark.parametrize(
    "text",
    [
        "/unknown",
        "/mnt/user-data/outputs/prd/technical-design.md",
        "/etc/passwd",
        "/not-a-command at all",
    ],
)
def test_feishu_treats_unknown_slash_text_as_chat(text):
    """Slash-prefixed text that is not a known command must be classified as CHAT."""
    bus = MessageBus()
    config = {"app_id": "test", "app_secret": "test"}
    channel = FeishuChannel(bus, config)

    event = MagicMock()
    event.event.message.chat_id = "chat_1"
    event.event.message.message_id = "msg_1"
    event.event.message.root_id = None
    event.event.message.chat_type = "p2p"
    event.event.sender.sender_id.open_id = "user_1"
    event.event.message.content = json.dumps({"text": text})

    with pytest.MonkeyPatch.context() as m:
        mock_make_inbound = MagicMock()
        m.setattr(channel, "_make_inbound", mock_make_inbound)
        channel._on_message(event)

        mock_make_inbound.assert_called_once()
        assert mock_make_inbound.call_args[1]["msg_type"].value == "chat", f"{text!r} should be classified as CHAT"

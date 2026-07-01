#!/usr/bin/env python3
"""Feishu client for YQS-Imagerepo notifications."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from env_loader import load_env


PYTHON_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PYTHON_DIR.parent

FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"
TOKEN_PATH = "/auth/v3/tenant_access_token/internal"
MESSAGE_PATH = "/im/v1/messages"


class FeishuClientError(RuntimeError):
    pass


def feishu_config_status() -> dict:
    load_env(PROJECT_DIR)
    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    receive_id = get_receive_id()
    return {
        "configured": bool(app_id and app_secret and receive_id),
        "hasAppId": bool(app_id),
        "hasAppSecret": bool(app_secret),
        "receiveIdType": get_receive_id_type(),
        "hasReceiveId": bool(receive_id),
        "notifyOnRecognition": os.getenv("FEISHU_NOTIFY_ON_RECOGNITION", "true").lower() != "false",
    }


def get_receive_id_type() -> str:
    load_env(PROJECT_DIR)
    return os.getenv("FEISHU_RECEIVE_ID_TYPE", "chat_id").strip() or "chat_id"


def get_receive_id() -> str:
    load_env(PROJECT_DIR)
    return (
        os.getenv("FEISHU_RECEIVE_ID", "").strip()
        or os.getenv("FEISHU_CHAT_ID", "").strip()
    )


def request_json(url: str, payload: dict, headers: dict[str, str] | None = None, timeout: int = 30) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FeishuClientError(f"飞书 HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise FeishuClientError(f"飞书网络请求失败: {exc}") from exc


def get_tenant_access_token() -> str:
    load_env(PROJECT_DIR)
    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise FeishuClientError("缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET。请在 .env 中配置。")

    payload = {
        "app_id": app_id,
        "app_secret": app_secret,
    }
    response = request_json(FEISHU_BASE_URL + TOKEN_PATH, payload)
    code = response.get("code", 0)
    if code != 0:
        raise FeishuClientError(f"获取 tenant_access_token 失败: {response}")
    token = response.get("tenant_access_token")
    if not token:
        raise FeishuClientError(f"飞书 token 返回为空: {response}")
    return token


def send_text_message(text: str) -> dict:
    load_env(PROJECT_DIR)
    receive_id = get_receive_id()
    receive_id_type = get_receive_id_type()
    if not receive_id:
        raise FeishuClientError("缺少 FEISHU_RECEIVE_ID 或 FEISHU_CHAT_ID。请在 .env 中配置。")

    token = get_tenant_access_token()
    query = urllib.parse.urlencode({"receive_id_type": receive_id_type})
    url = FEISHU_BASE_URL + MESSAGE_PATH + "?" + query
    payload = {
        "receive_id": receive_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }
    response = request_json(url, payload, headers={"Authorization": f"Bearer {token}"})
    code = response.get("code", 0)
    if code != 0:
        raise FeishuClientError(f"发送飞书消息失败: {response}")
    return response


def build_recognition_summary(summary: dict) -> str:
    return "\n".join([
        "YQS-Imagerepo AI 识图完成",
        f"成功：{summary.get('completed', 0)} 张",
        f"失败：{summary.get('failed', 0)} 张",
        f"跳过：{summary.get('skipped', 0)} 张",
        f"开始：{summary.get('started_at', '')}",
        f"结束：{summary.get('finished_at', '')}",
        "",
        "已更新：案例素材清单_表格.md / 案例素材清单.xlsx / 素材分辨率.csv",
    ])


def notify_recognition_finished(summary: dict) -> None:
    load_env(PROJECT_DIR)
    if os.getenv("FEISHU_NOTIFY_ON_RECOGNITION", "true").lower() == "false":
        return
    if not feishu_config_status()["configured"]:
        return
    send_text_message(build_recognition_summary(summary))

#!/usr/bin/env python3
"""Feishu Bitable client for YQS material input records."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import feishu_client
from env_loader import load_env


PYTHON_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PYTHON_DIR.parent

FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"


class FeishuBitableError(RuntimeError):
    pass


def _env(name: str, default: str = "") -> str:
    load_env(PROJECT_DIR)
    return os.getenv(name, default).strip()


def configured() -> bool:
    return bool(_env("FEISHU_BITABLE_APP_TOKEN") and _env("FEISHU_BITABLE_TABLE_ID"))


def bitable_status() -> dict[str, Any]:
    return {
        "configured": configured(),
        "hasAppToken": bool(_env("FEISHU_BITABLE_APP_TOKEN")),
        "hasTableId": bool(_env("FEISHU_BITABLE_TABLE_ID")),
        "hasViewId": bool(_env("FEISHU_BITABLE_VIEW_ID")),
        "batchLimit": int(_env("YQS_BITABLE_BATCH_LIMIT", "100") or "100"),
    }


class FeishuBitableClient:
    def __init__(
        self,
        app_token: str | None = None,
        table_id: str | None = None,
        view_id: str | None = None,
    ) -> None:
        load_env(PROJECT_DIR)
        self.app_token = app_token or _env("FEISHU_BITABLE_APP_TOKEN")
        self.table_id = table_id or _env("FEISHU_BITABLE_TABLE_ID")
        self.view_id = view_id or _env("FEISHU_BITABLE_VIEW_ID")

    def configured(self) -> bool:
        return bool(self.app_token and self.table_id)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {feishu_client.get_tenant_access_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        if query:
            path = path + "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v not in (None, "")})
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            FEISHU_BASE_URL + path,
            data=data,
            method=method,
            headers=self._headers(),
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise FeishuBitableError(f"飞书多维表格 HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise FeishuBitableError(f"飞书多维表格网络请求失败: {exc}") from exc

    def _data_or_raise(self, response: dict[str, Any]) -> dict[str, Any]:
        code = response.get("code", 0)
        if code != 0:
            raise FeishuBitableError(f"飞书多维表格返回失败: {response}")
        data = response.get("data")
        return data if isinstance(data, dict) else {}

    def create_app(self, name: str = "YQS PPT 图片资产库") -> dict[str, Any]:
        data = self._data_or_raise(self.request("POST", "/bitable/v1/apps", {"name": name}))
        app = data.get("app") if isinstance(data.get("app"), dict) else data
        self.app_token = str(app.get("app_token") or self.app_token or "")
        return app

    def create_table(self, name: str = "图片资产输入") -> dict[str, Any]:
        if not self.app_token:
            raise FeishuBitableError("缺少 FEISHU_BITABLE_APP_TOKEN，无法创建数据表。")
        data = self._data_or_raise(
            self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables", {"table": {"name": name}})
        )
        table = data.get("table") if isinstance(data.get("table"), dict) else data
        self.table_id = str(table.get("table_id") or self.table_id or "")
        return table

    def create_field(self, field_name: str, field_type: int = 1) -> dict[str, Any]:
        if not self.configured():
            raise FeishuBitableError("缺少 app_token/table_id，无法创建字段。")
        payload: dict[str, Any] = {"field_name": field_name, "type": field_type}
        data = self._data_or_raise(
            self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields", payload)
        )
        return data.get("field") if isinstance(data.get("field"), dict) else data

    def delete_field(self, field_id: str) -> dict[str, Any]:
        if not self.configured():
            raise FeishuBitableError("缺少 app_token/table_id，无法删除字段。")
        data = self._data_or_raise(
            self.request("DELETE", f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields/{field_id}")
        )
        return {"ok": True, "data": data}

    def update_field(self, field_id: str, field_name: str, field_type: int = 1) -> dict[str, Any]:
        if not self.configured():
            raise FeishuBitableError("缺少 app_token/table_id，无法更新字段。")
        data = self._data_or_raise(
            self.request(
                "PUT",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields/{field_id}",
                {"field_name": field_name, "type": field_type},
            )
        )
        return data.get("field") if isinstance(data.get("field"), dict) else data

    def list_fields(self) -> list[dict[str, Any]]:
        if not self.configured():
            return []
        data = self._data_or_raise(
            self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields")
        )
        items = data.get("items", [])
        return items if isinstance(items, list) else []

    def ensure_schema(self, fields: dict[str, int]) -> dict[str, Any]:
        existing = {str(field.get("field_name")) for field in self.list_fields()}
        created = []
        for field_name, field_type in fields.items():
            if field_name in existing:
                continue
            created.append(self.create_field(field_name, field_type))
        return {"ok": True, "created": created, "existing": sorted(existing)}

    def grant_tenant_readable(self, doc_type: str = "bitable") -> dict[str, Any]:
        """Allow users in the tenant to read the Bitable via link."""
        if not self.app_token:
            raise FeishuBitableError("缺少 FEISHU_BITABLE_APP_TOKEN，无法设置云文档阅读权限。")
        payload = {
            "link_share_entity": "tenant_readable",
            "security_entity": "anyone_can_view",
            "comment_entity": "anyone_can_view",
            "share_entity": "anyone",
        }
        data = self._data_or_raise(
            self.request(
                "PATCH",
                f"/drive/v2/permissions/{self.app_token}/public",
                payload,
                query={"type": doc_type},
            )
        )
        return {"ok": True, "data": data}

    def grant_tenant_editable(self, doc_type: str = "bitable") -> dict[str, Any]:
        """Allow users in the tenant to edit the Bitable via link."""
        if not self.app_token:
            raise FeishuBitableError("缺少 FEISHU_BITABLE_APP_TOKEN，无法设置云文档编辑权限。")
        payload = {
            "link_share_entity": "tenant_editable",
            "security_entity": "anyone_can_view",
            "comment_entity": "anyone_can_view",
            "share_entity": "anyone",
        }
        data = self._data_or_raise(
            self.request(
                "PATCH",
                f"/drive/v2/permissions/{self.app_token}/public",
                payload,
                query={"type": doc_type},
            )
        )
        return {"ok": True, "data": data}

    def add_reader_member(self, member_id: str, member_type: str = "openid", doc_type: str = "bitable") -> dict[str, Any]:
        """Add one user/department/chat as a read-only collaborator."""
        if not self.app_token:
            raise FeishuBitableError("缺少 FEISHU_BITABLE_APP_TOKEN，无法添加阅读协作者。")
        payload = {
            "member_type": member_type,
            "member_id": member_id,
            "perm": "view",
        }
        data = self._data_or_raise(
            self.request(
                "POST",
                f"/drive/v1/permissions/{self.app_token}/members",
                payload,
                query={"type": doc_type},
            )
        )
        return {"ok": True, "data": data}

    def list_views(self) -> list[dict[str, Any]]:
        if not self.configured():
            return []
        data = self._data_or_raise(
            self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/views")
        )
        items = data.get("items", [])
        return items if isinstance(items, list) else []

    def create_form_view(self, view_name: str = "图片上传表单视图") -> dict[str, Any]:
        """Create a Bitable form view for image submissions."""
        if not self.configured():
            raise FeishuBitableError("缺少 app_token/table_id，无法创建表单视图。")
        for view in self.list_views():
            if view.get("view_name") == view_name and view.get("view_type") == "form":
                return {"ok": True, "view": view, "existing": True}
        payload = {
            "view_name": view_name,
            "view_type": "form",
        }
        data = self._data_or_raise(
            self.request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/views",
                payload,
            )
        )
        view = data.get("view") if isinstance(data.get("view"), dict) else data
        if view.get("view_type") != "form":
            return {
                "ok": False,
                "view": view,
                "message": "飞书 API 未返回表单视图，可能当前接口不支持创建表单视图。",
            }
        return {"ok": True, "view": view}

    def list_records(self, page_size: int | None = None) -> list[dict[str, Any]]:
        if not self.configured():
            return []
        limit = page_size or int(_env("YQS_BITABLE_BATCH_LIMIT", "100") or "100")
        query = {"page_size": limit, "view_id": self.view_id or None}
        data = self._data_or_raise(
            self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records", query=query)
        )
        items = data.get("items", [])
        return items if isinstance(items, list) else []

    def update_record(self, record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        if not self.configured():
            return {"ok": False, "skipped": True, "message": "未配置飞书多维表格。"}
        data = self._data_or_raise(
            self.request(
                "PUT",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{record_id}",
                {"fields": fields},
            )
        )
        return data.get("record") if isinstance(data.get("record"), dict) else data

    def download_attachment(self, attachment: dict[str, Any], target_path: Path) -> Path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        url = str(attachment.get("tmp_url") or attachment.get("url") or "").strip()
        if url:
            request_url = url
        else:
            file_token = str(attachment.get("file_token") or attachment.get("token") or "").strip()
            if not file_token:
                raise FeishuBitableError(f"附件缺少 file_token: {attachment}")
            request_url = FEISHU_BASE_URL + f"/drive/v1/medias/{urllib.parse.quote(file_token)}/download"

        request = urllib.request.Request(request_url, headers={"Authorization": f"Bearer {feishu_client.get_tenant_access_token()}"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                content = response.read()
                content_type = response.headers.get("Content-Type", "")
            if "json" in content_type.lower() or content.lstrip().startswith(b"{"):
                payload = json.loads(content.decode("utf-8"))
                tmp_urls = (((payload.get("data") or {}).get("tmp_download_urls")) or [])
                tmp_url = ""
                if isinstance(tmp_urls, list) and tmp_urls:
                    first = tmp_urls[0]
                    if isinstance(first, dict):
                        tmp_url = str(first.get("tmp_download_url") or "").strip()
                if tmp_url:
                    with urllib.request.urlopen(urllib.request.Request(tmp_url), timeout=120) as tmp_response:
                        content = tmp_response.read()
                else:
                    raise FeishuBitableError(f"飞书附件下载接口没有返回可用 tmp_download_url: {payload}")
            target_path.write_bytes(content)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise FeishuBitableError(f"下载飞书附件失败 HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise FeishuBitableError(f"下载飞书附件网络失败: {exc}") from exc
        return target_path

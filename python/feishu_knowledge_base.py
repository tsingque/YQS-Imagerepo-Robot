#!/usr/bin/env python3
"""Sync classified YQS material images into a Feishu Drive folder."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import feishu_client
from env_loader import load_env


PYTHON_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PYTHON_DIR.parent

FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"
DEFAULT_SPACE_NAME = "YQS PPT 图片素材库"
DEFAULT_FOLDER_OBJ_TYPE = "docx"
DRIVE_FOLDER_TARGET = "drive_folder"
WIKI_TARGET = "wiki"
CASE_MATERIALS_DIR = PROJECT_DIR / "case_materials"
STATE_PATH = PROJECT_DIR / "runtime" / "feishu_knowledge_sync_state.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


class FeishuKnowledgeBaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalMaterialImage:
    path: Path
    relative_path: str
    folder_parts: tuple[str, ...]
    fingerprint: dict[str, int]


def _env(name: str, default: str = "") -> str:
    load_env(PROJECT_DIR)
    return os.getenv(name, default).strip()


def _as_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = data.get("items", [])
    return items if isinstance(items, list) else []


def iter_case_material_images(root: Path | str = CASE_MATERIALS_DIR) -> list[LocalMaterialImage]:
    root_path = Path(root)
    if not root_path.is_dir():
        return []

    images: list[LocalMaterialImage] = []
    for path in sorted(root_path.rglob("*"), key=lambda item: item.relative_to(root_path).as_posix()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        relative = path.relative_to(root_path)
        stat = path.stat()
        images.append(
            LocalMaterialImage(
                path=path,
                relative_path=relative.as_posix(),
                folder_parts=tuple(part for part in relative.parent.parts if part != "."),
                fingerprint={"size": stat.st_size, "mtime_ns": stat.st_mtime_ns},
            )
        )
    return images


def load_sync_state(path: Path | str = STATE_PATH) -> dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists():
        return {"version": 1, "files": {}}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "files": {}}
    if not isinstance(state, dict):
        return {"version": 1, "files": {}}
    files = state.get("files")
    if not isinstance(files, dict):
        state["files"] = {}
    state.setdefault("version", 1)
    return state


def save_sync_state(state: dict[str, Any], path: Path | str = STATE_PATH) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(state_path)


class FeishuKnowledgeBaseClient:
    def __init__(
        self,
        *,
        space_name: str | None = None,
        space_id: str | None = None,
        root_node_token: str | None = None,
        drive_folder_token: str | None = None,
        target_type: str | None = None,
        parent_type: str | None = None,
        folder_obj_type: str | None = None,
        user_access_token: str | None = None,
    ) -> None:
        load_env(PROJECT_DIR)
        self.space_name = space_name or _env("FEISHU_KNOWLEDGE_SPACE_NAME", DEFAULT_SPACE_NAME)
        self.space_id = space_id or _env("FEISHU_KNOWLEDGE_SPACE_ID")
        self.root_node_token = root_node_token or _env("FEISHU_KNOWLEDGE_ROOT_NODE_TOKEN")
        self.drive_folder_token = (
            drive_folder_token
            or _env("FEISHU_ECHO_DRIVE_FOLDER_TOKEN")
            or _env("FEISHU_KNOWLEDGE_DRIVE_FOLDER_TOKEN")
            or _env("FEISHU_KNOWLEDGE_FOLDER_TOKEN")
        )
        configured_target = target_type or _env("FEISHU_ECHO_TARGET_TYPE")
        if self.drive_folder_token:
            configured_target = DRIVE_FOLDER_TARGET
        self.target_type = configured_target or DRIVE_FOLDER_TARGET
        if self.target_type == DRIVE_FOLDER_TARGET and not self.drive_folder_token:
            self.drive_folder_token = self.root_node_token
        default_parent_type = "explorer" if self.target_type == DRIVE_FOLDER_TARGET else "wiki"
        self.parent_type = (
            parent_type
            or _env("FEISHU_ECHO_PARENT_TYPE")
            or default_parent_type
        )
        self.folder_obj_type = folder_obj_type or _env("FEISHU_KNOWLEDGE_FOLDER_OBJ_TYPE", DEFAULT_FOLDER_OBJ_TYPE)
        self.user_access_token = (
            user_access_token
            or _env("FEISHU_KNOWLEDGE_USER_ACCESS_TOKEN")
            or _env("FEISHU_USER_ACCESS_TOKEN")
        )

    def _access_token(self, *, require_user: bool = False) -> str:
        if require_user:
            if self.user_access_token:
                return self.user_access_token
            raise FeishuKnowledgeBaseError(
                "当前回显已改为飞书文件夹模式。请配置 FEISHU_ECHO_DRIVE_FOLDER_TOKEN。"
            )
        return self.user_access_token or feishu_client.get_tenant_access_token()

    def _headers(self, *, require_user: bool = False, content_type: str | None = "application/json; charset=utf-8") -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._access_token(require_user=require_user)}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        *,
        require_user: bool = False,
        timeout: int = 60,
    ) -> dict[str, Any]:
        if query:
            filtered = {key: value for key, value in query.items() if value not in (None, "")}
            if filtered:
                path = path + "?" + urllib.parse.urlencode(filtered)
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            FEISHU_BASE_URL + path,
            data=data,
            method=method,
            headers=self._headers(require_user=require_user),
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise FeishuKnowledgeBaseError(f"飞书回显 HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise FeishuKnowledgeBaseError(f"飞书回显网络请求失败: {exc}") from exc

    def multipart_request(
        self,
        path: str,
        fields: dict[str, Any],
        file_field: str,
        file_path: Path,
        *,
        timeout: int = 180,
    ) -> dict[str, Any]:
        boundary = f"----YQSFeishuBoundary{int(time.time() * 1000)}"
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        chunks: list[bytes] = []
        for name, value in fields.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )
        file_bytes = file_path.read_bytes()
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{file_field}"; '
                    f'filename="{file_path.name}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                file_bytes,
                b"\r\n",
                f"--{boundary}--\r\n".encode("utf-8"),
            ]
        )
        request = urllib.request.Request(
            FEISHU_BASE_URL + path,
            data=b"".join(chunks),
            method="POST",
            headers=self._headers(content_type=f"multipart/form-data; boundary={boundary}"),
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise FeishuKnowledgeBaseError(f"上传飞书文件夹文件失败 HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise FeishuKnowledgeBaseError(f"上传飞书文件夹文件网络失败: {exc}") from exc

    def _data_or_raise(self, response: dict[str, Any]) -> dict[str, Any]:
        code = response.get("code", 0)
        if code != 0:
            raise FeishuKnowledgeBaseError(f"飞书接口返回失败: {response}")
        data = response.get("data")
        return data if isinstance(data, dict) else {}

    def list_drive_files(self, folder_token: str) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        page_token = ""
        while True:
            data = self._data_or_raise(
                self.request(
                    "GET",
                    "/drive/v1/files",
                    query={
                        "page_size": 200,
                        "page_token": page_token,
                        "folder_token": folder_token,
                    },
                )
            )
            page_files = data.get("files", [])
            if isinstance(page_files, list):
                files.extend(page_files)
            if not data.get("has_more"):
                break
            page_token = str(data.get("next_page_token") or "")
            if not page_token:
                break
        return files

    def create_drive_folder(self, name: str, parent_folder_token: str) -> dict[str, Any]:
        data = self._data_or_raise(
            self.request(
                "POST",
                "/drive/v1/files/create_folder",
                payload={"name": name, "folder_token": parent_folder_token},
            )
        )
        return data

    def ensure_drive_folder_path(self, folder_parts: tuple[str, ...]) -> dict[str, Any]:
        parent_token = self.drive_folder_token or self.root_node_token
        if not parent_token:
            raise FeishuKnowledgeBaseError(
                "缺少飞书文件夹 token。请配置 FEISHU_ECHO_DRIVE_FOLDER_TOKEN。"
            )

        ensured: list[dict[str, Any]] = []
        for title in folder_parts:
            existing = next(
                (
                    item
                    for item in self.list_drive_files(parent_token)
                    if str(item.get("name") or "").strip() == title
                    and str(item.get("type") or "").strip() == "folder"
                ),
                None,
            )
            if existing:
                folder = existing
                created = False
            else:
                folder = self.create_drive_folder(title, parent_token)
                created = True
            parent_token = str(folder.get("token") or "")
            if not parent_token:
                raise FeishuKnowledgeBaseError(f"飞书文件夹缺少 token: {folder}")
            ensured.append({"title": title, "node_token": parent_token, "created": created})
        return {"node_token": parent_token, "nodes": ensured}

    def list_spaces(self) -> list[dict[str, Any]]:
        spaces: list[dict[str, Any]] = []
        page_token = ""
        while True:
            data = self._data_or_raise(
                self.request(
                    "GET",
                    "/wiki/v2/spaces",
                    query={"page_size": 50, "page_token": page_token},
                )
            )
            spaces.extend(_as_items(data))
            if not data.get("has_more"):
                break
            page_token = str(data.get("page_token") or "")
            if not page_token:
                break
        return spaces

    def create_space(self, name: str) -> dict[str, Any]:
        data = self._data_or_raise(
            self.request(
                "POST",
                "/wiki/v2/spaces",
                payload={"name": name, "description": "YQS 本地 PPT 图片素材库自动回显同步空间"},
                require_user=True,
            )
        )
        space = data.get("space") if isinstance(data.get("space"), dict) else data
        self.space_id = str(space.get("space_id") or self.space_id or "")
        return space

    def ensure_space(self) -> dict[str, Any]:
        if self.target_type == DRIVE_FOLDER_TARGET:
            folder_token = self.drive_folder_token or self.root_node_token
            if not folder_token:
                raise FeishuKnowledgeBaseError(
                    "缺少飞书文件夹 token。请配置 FEISHU_ECHO_DRIVE_FOLDER_TOKEN。"
                )
            self.drive_folder_token = folder_token
            return {
                "space_id": f"drive:{folder_token}",
                "name": self.space_name,
                "created": False,
                "target_type": DRIVE_FOLDER_TARGET,
                "root_node_token": folder_token,
            }

        if self.space_id:
            return {"space_id": self.space_id, "name": self.space_name, "created": False, "configured": True}

        for space in self.list_spaces():
            if str(space.get("name") or "").strip() == self.space_name:
                self.space_id = str(space.get("space_id") or "")
                return {"space_id": self.space_id, "name": self.space_name, "created": False, "space": space}

        space = self.create_space(self.space_name)
        return {"space_id": self.space_id, "name": self.space_name, "created": True, "space": space}

    def list_nodes(self, space_id: str, parent_node_token: str = "") -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        page_token = ""
        while True:
            data = self._data_or_raise(
                self.request(
                    "GET",
                    f"/wiki/v2/spaces/{urllib.parse.quote(space_id)}/nodes",
                    query={
                        "page_size": 50,
                        "page_token": page_token,
                        "parent_node_token": parent_node_token,
                    },
                )
            )
            nodes.extend(_as_items(data))
            if not data.get("has_more"):
                break
            page_token = str(data.get("page_token") or "")
            if not page_token:
                break
        return nodes

    def create_node(self, space_id: str, title: str, parent_node_token: str = "") -> dict[str, Any]:
        payload = {
            "title": title,
            "obj_type": self.folder_obj_type,
            "node_type": "origin",
        }
        if parent_node_token:
            payload["parent_node_token"] = parent_node_token
        data = self._data_or_raise(
            self.request("POST", f"/wiki/v2/spaces/{urllib.parse.quote(space_id)}/nodes", payload=payload)
        )
        node = data.get("node") if isinstance(data.get("node"), dict) else data
        return node

    def ensure_folder_path(self, space_id: str, folder_parts: tuple[str, ...]) -> dict[str, Any]:
        if self.target_type == DRIVE_FOLDER_TARGET:
            return self.ensure_drive_folder_path(folder_parts)

        parent_node_token = self.root_node_token
        ensured: list[dict[str, Any]] = []
        for title in folder_parts:
            existing = next(
                (
                    node
                    for node in self.list_nodes(space_id, parent_node_token)
                    if str(node.get("title") or "").strip() == title
                ),
                None,
            )
            if existing:
                node = existing
                created = False
            else:
                node = self.create_node(space_id, title, parent_node_token)
                created = True
            parent_node_token = str(node.get("node_token") or "")
            if not parent_node_token:
                raise FeishuKnowledgeBaseError(f"飞书知识库节点缺少 node_token: {node}")
            ensured.append({"title": title, "node_token": parent_node_token, "created": created})
        return {"node_token": parent_node_token, "nodes": ensured}

    def upload_file(self, parent_node_token: str, image_path: Path) -> dict[str, Any]:
        file_bytes = image_path.read_bytes()
        data = self._data_or_raise(
            self.multipart_request(
                "/drive/v1/files/upload_all",
                {
                    "file_name": image_path.name,
                    "parent_type": self.parent_type,
                    "parent_node": parent_node_token,
                    "size": len(file_bytes),
                    "checksum": hashlib.md5(file_bytes).hexdigest(),
                },
                "file",
                image_path,
            )
        )
        return data


def sync_case_materials_to_knowledge_base(
    *,
    root: Path | str = CASE_MATERIALS_DIR,
    state_path: Path | str = STATE_PATH,
    client: FeishuKnowledgeBaseClient | None = None,
    force_upload: bool | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    sync_client = client or FeishuKnowledgeBaseClient()
    force = (
        force_upload
        if force_upload is not None
        else _env("FEISHU_ECHO_FORCE_UPLOAD", "false").lower() == "true"
    )
    summary: dict[str, Any] = {
        "ok": True,
        "root": str(root_path),
        "space_name": sync_client.space_name,
        "space_id": "",
        "target_type": getattr(sync_client, "target_type", WIKI_TARGET),
        "created_space": False,
        "total": 0,
        "uploaded": 0,
        "skipped": 0,
        "failed": 0,
        "created_folders": 0,
        "ensured_folders": 0,
        "errors": [],
    }

    space = sync_client.ensure_space()
    summary["space_id"] = space.get("space_id", "")
    summary["created_space"] = bool(space.get("created"))

    images = iter_case_material_images(root_path)
    summary["total"] = len(images)
    state = load_sync_state(state_path)
    files_state: dict[str, Any] = state.setdefault("files", {})
    folder_cache: dict[tuple[str, ...], str] = {}
    state_changed = False

    for image in images:
        previous = files_state.get(image.relative_path)
        if not force and isinstance(previous, dict) and previous.get("fingerprint") == image.fingerprint:
            summary["skipped"] += 1
            continue

        folder_parts = image.folder_parts or ("通用素材库",)
        try:
            if folder_parts not in folder_cache:
                folder_info = sync_client.ensure_folder_path(str(summary["space_id"]), folder_parts)
                folder_cache[folder_parts] = str(folder_info.get("node_token") or "")
                nodes = folder_info.get("nodes", [])
                if isinstance(nodes, list):
                    summary["ensured_folders"] += len(nodes)
                    summary["created_folders"] += sum(1 for node in nodes if isinstance(node, dict) and node.get("created"))
            parent_node_token = folder_cache[folder_parts]
            if not parent_node_token:
                raise FeishuKnowledgeBaseError(f"无法确认知识库目录节点: {'/'.join(folder_parts)}")
            uploaded = sync_client.upload_file(parent_node_token, image.path)
            files_state[image.relative_path] = {
                "fingerprint": image.fingerprint,
                "space_id": summary["space_id"],
                "parent_node_token": parent_node_token,
                "file_token": uploaded.get("file_token", ""),
                "uploaded_at": int(time.time()),
            }
            summary["uploaded"] += 1
            state_changed = True
        except Exception as exc:
            summary["failed"] += 1
            summary["errors"].append({"path": image.relative_path, "error": str(exc)})

    summary["ok"] = summary["failed"] == 0
    if state_changed:
        save_sync_state(state, state_path)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync case_materials images into a Feishu Drive folder.")
    parser.add_argument("--root", default=str(CASE_MATERIALS_DIR), help="Local case_materials directory.")
    parser.add_argument("--state", default=str(STATE_PATH), help="Local sync state JSON path.")
    parser.add_argument("--force", action="store_true", help="Upload files even when local fingerprint is unchanged.")
    args = parser.parse_args()
    print(
        json.dumps(
            sync_case_materials_to_knowledge_base(root=args.root, state_path=args.state, force_upload=args.force),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import feishu_knowledge_base as kb


class FakeKnowledgeClient:
    def __init__(self) -> None:
        self.space_name = "YQS Test Space"
        self.space_id = "space_1"
        self.ensure_space_calls = 0
        self.folder_calls: list[tuple[str, ...]] = []
        self.upload_calls: list[tuple[str, Path]] = []
        self.target_type = kb.DRIVE_FOLDER_TARGET
        self.reader_calls: list[str] = []

    def ensure_space(self) -> dict:
        self.ensure_space_calls += 1
        return {"space_id": self.space_id, "name": self.space_name, "created": True}

    def ensure_folder_path(self, space_id: str, folder_parts: tuple[str, ...]) -> dict:
        self.folder_calls.append(folder_parts)
        return {
            "node_token": "node_" + "_".join(folder_parts),
            "nodes": [{"title": part, "node_token": f"node_{part}", "created": True} for part in folder_parts],
        }

    def upload_file(self, parent_node_token: str, image_path: Path) -> dict:
        self.upload_calls.append((parent_node_token, image_path))
        return {"file_token": "file_" + image_path.stem}

    def grant_drive_folder_reader(self, open_id: str) -> dict:
        self.reader_calls.append(open_id)
        return {"ok": True, "member_id": open_id, "perm": kb.DRIVE_FOLDER_REQUESTER_PERMISSION}


class FeishuKnowledgeBaseTests(unittest.TestCase):
    def test_iter_case_material_images_preserves_folder_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "项目A" / "二级分类" / "湖面.jpg"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"jpg")
            (root / "项目A" / ".DS_Store").write_bytes(b"ignored")

            images = kb.iter_case_material_images(root)

        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].relative_path, "项目A/二级分类/湖面.jpg")
        self.assertEqual(images[0].folder_parts, ("项目A", "二级分类"))

    def test_sync_uploads_images_to_matching_knowledge_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "case_materials"
            state = Path(tmp) / "state.json"
            first = root / "项目A" / "图1.png"
            second = root / "项目B" / "图2.jpg"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            client = FakeKnowledgeClient()

            summary = kb.sync_case_materials_to_knowledge_base(root=root, state_path=state, client=client, force_upload=False)

            self.assertTrue(summary["ok"])
            self.assertEqual(summary["uploaded"], 2)
            self.assertEqual(summary["skipped"], 0)
            self.assertEqual(client.ensure_space_calls, 1)
            self.assertEqual(client.reader_calls, [])
            self.assertEqual(client.folder_calls, [("项目A",), ("项目B",)])
            self.assertEqual([path.name for _, path in client.upload_calls], ["图1.png", "图2.jpg"])
            self.assertTrue(state.exists())

    def test_sync_grants_reader_for_requester_open_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "case_materials"
            state = Path(tmp) / "state.json"
            image = root / "项目A" / "图1.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"first")
            client = FakeKnowledgeClient()

            summary = kb.sync_case_materials_to_knowledge_base(
                root=root,
                state_path=state,
                client=client,
                force_upload=False,
                reader_open_id="ou_user_1",
            )

            self.assertTrue(summary["reader_granted"])
            self.assertTrue(summary["folder_permission_granted"])
            self.assertEqual(summary["folder_permission_role"], "full_access")
            self.assertEqual(client.reader_calls, ["ou_user_1"])
            self.assertTrue(summary["ok"])

    def test_sync_skips_unchanged_files_from_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "case_materials"
            state = Path(tmp) / "state.json"
            image = root / "项目A" / "图1.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"same")
            client = FakeKnowledgeClient()

            first = kb.sync_case_materials_to_knowledge_base(root=root, state_path=state, client=client, force_upload=False)
            second = kb.sync_case_materials_to_knowledge_base(root=root, state_path=state, client=client, force_upload=False)

            self.assertEqual(first["uploaded"], 1)
            self.assertEqual(second["uploaded"], 0)
            self.assertEqual(second["skipped"], 1)
            self.assertEqual(len(client.upload_calls), 1)

    def test_drive_folder_target_ensures_nested_folders(self):
        client = kb.FeishuKnowledgeBaseClient(
            target_type="drive_folder",
            drive_folder_token="root_folder",
        )
        responses = [
            {"code": 0, "data": {"files": [{"name": "项目A", "type": "folder", "token": "folder_a"}], "has_more": False}},
            {"code": 0, "data": {"files": [], "has_more": False}},
            {"code": 0, "data": {"token": "folder_b", "url": "https://example.feishu.cn/drive/folder/folder_b"}},
        ]

        with patch.object(client, "request", side_effect=responses) as request:
            folder = client.ensure_folder_path("", ("项目A", "二级分类"))

        self.assertEqual(folder["node_token"], "folder_b")
        self.assertEqual(folder["nodes"][0]["node_token"], "folder_a")
        self.assertFalse(folder["nodes"][0]["created"])
        self.assertTrue(folder["nodes"][1]["created"])
        self.assertEqual(request.call_args_list[0].args[:2], ("GET", "/drive/v1/files"))
        self.assertEqual(request.call_args_list[0].kwargs["query"]["folder_token"], "root_folder")
        self.assertEqual(request.call_args_list[1].kwargs["query"]["folder_token"], "folder_a")
        self.assertEqual(request.call_args_list[2].args[:2], ("POST", "/drive/v1/files/create_folder"))
        self.assertEqual(request.call_args_list[2].kwargs["payload"], {"name": "二级分类", "folder_token": "folder_a"})

    def test_forbidden_drive_folder_error_explains_cloud_drive_limit(self):
        error = kb._format_feishu_http_error("飞书回显", 403, '{"code":1061004,"msg":"forbidden."}')

        self.assertIn("飞书云盘文件夹权限不足", error)
        self.assertIn("协作者里通常搜不到机器人", error)
        self.assertIn("用户授权", error)

    def test_drive_folder_target_auto_creates_root_folder_when_token_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "echo_folder.json"
            with patch.object(kb, "ECHO_FOLDER_STATE_PATH", state_path):
                client = kb.FeishuKnowledgeBaseClient(
                    space_name="YQS Test Space",
                    target_type="drive_folder",
                    drive_folder_token="",
                )
                response = {
                    "code": 0,
                    "data": {
                        "token": "created_folder",
                        "url": "https://example.feishu.cn/drive/folder/created_folder",
                    },
                }

                with patch.object(client, "request", return_value=response) as request:
                    space = client.ensure_space()

            self.assertTrue(space["created"])
            self.assertEqual(space["root_node_token"], "created_folder")
            self.assertEqual(space["url"], "https://example.feishu.cn/drive/folder/created_folder")
            self.assertTrue(state_path.exists())
            self.assertIn("created_folder", state_path.read_text(encoding="utf-8"))
            self.assertEqual(request.call_args.args[:2], ("POST", "/drive/v1/files/create_folder"))
            self.assertEqual(request.call_args.kwargs["payload"], {"name": "YQS Test Space", "folder_token": ""})

    def test_drive_folder_reader_grant_does_not_trust_stale_local_cache_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "echo_folder.json"
            state_path.write_text(
                '{"drive_folder_token": "folder_1", "reader_open_ids": ["ou_user_1"]}',
                encoding="utf-8",
            )
            client = kb.FeishuKnowledgeBaseClient(target_type="drive_folder", drive_folder_token="folder_1")
            client.echo_folder_state_path = state_path

            with patch.object(client, "request", return_value={"code": 0, "data": {"member": "ok"}}) as request:
                result = client.grant_drive_folder_reader("ou_user_1")

        self.assertTrue(result["ok"])
        self.assertEqual(request.call_args.args[:2], ("POST", "/drive/v1/permissions/folder_1/members"))
        self.assertEqual(
            request.call_args.kwargs["payload"],
            {"member_type": "openid", "member_id": "ou_user_1", "perm": "full_access"},
        )

    def test_delete_drive_folder_uses_folder_delete_api(self):
        client = kb.FeishuKnowledgeBaseClient(target_type="drive_folder", drive_folder_token="folder_1")

        with patch.object(client, "request", return_value={"code": 0, "data": {"task_id": "task_1"}}) as request:
            result = client.delete_drive_folder()

        self.assertTrue(result["ok"])
        self.assertEqual(result["task_id"], "task_1")
        self.assertEqual(request.call_args.args[:2], ("DELETE", "/drive/v1/files/folder_1"))
        self.assertEqual(request.call_args.kwargs["query"], {"type": "folder"})

    def test_check_drive_task_uses_task_check_api(self):
        client = kb.FeishuKnowledgeBaseClient(target_type="drive_folder", drive_folder_token="folder_1")

        with patch.object(client, "request", return_value={"code": 0, "data": {"status": "success"}}) as request:
            result = client.check_drive_task("task_1")

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "success")
        self.assertEqual(request.call_args.args[:2], ("GET", "/drive/v1/files/task_check"))
        self.assertEqual(request.call_args.kwargs["query"], {"task_id": "task_1"})

    def test_upload_file_omits_checksum_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "图1.png"
            image.write_bytes(b"image")
            client = kb.FeishuKnowledgeBaseClient(
                target_type="drive_folder",
                drive_folder_token="root_folder",
            )

            with patch.object(client, "multipart_request", return_value={"code": 0, "data": {"file_token": "file_1"}}) as request:
                uploaded = client.upload_file("parent_folder", image)

        self.assertEqual(uploaded["file_token"], "file_1")
        fields = request.call_args.args[1]
        self.assertEqual(fields["file_name"], "图1.png")
        self.assertEqual(fields["parent_type"], "explorer")
        self.assertEqual(fields["parent_node"], "parent_folder")
        self.assertEqual(fields["size"], 5)
        self.assertNotIn("checksum", fields)


if __name__ == "__main__":
    unittest.main()

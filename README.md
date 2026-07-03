# YQS-Imagerepo Robot

YQS-Imagerepo Robot 是一个给办公室 PPT 素材沉淀用的自动化工具。

它做四件事：

1. 从飞书多维表格表单收集图片和人工字段。
2. 把图片下载到本地，压缩后交给 AI 识图。
3. 按 `项目` 字段把图片归类到本地素材库。
4. 把归类后的素材同步回飞书云盘文件夹，方便团队查看、修改和删除。

当前仓库：

```text
https://github.com/tsingque/YQS-Imagerepo-Robot
https://gitee.com/yuki0301/YQS-Imagerepo-Robot
```

## 日常使用

同事只需要记住三个入口。

| 场景 | 在飞书群里发送 | 结果 |
| --- | --- | --- |
| 获取上传入口 | `表单` | 机器人返回飞书多维表格表单链接 |
| 启动素材处理 | `启动` | 系统拉取表单图片、压缩、AI 识图、归类 |
| 同步成品素材 | `回显` | 系统把 `case_materials/` 同步到飞书云盘文件夹 |

群聊里的普通消息默认不会回复。需要普通问答时，请 `@机器人`。

## 当前输入字段

飞书多维表格表单以人工维护为准，本地脚本不会默认改表单结构。

当前建议只保留这些输入字段：

| 字段 | 用途 |
| --- | --- |
| `项目` | 决定本地和云盘里的归档文件夹；为空时进入通用素材库 |
| `名字` | 素材名称；不要再写 `项目-名字` |
| `描述` | 人工备注、使用场景、补充说明 |
| `文件` | 图片附件 |
| `来源` | 一级来源，例如拍摄、下载、截图、AI 生成、渲染 |
| `来源二级分类` | 二级分类，当前暂定为 `计划` |
| `是否可商用` | 入库开关；`是` 才进入处理流程 |

处理状态、AI 识图结果、本地路径、token 用量等运行数据只保存在本地，不写回飞书多维表格。

## 机器人指令

这些中文指令不需要 @ 机器人。

| 指令 | 别名 | 作用 |
| --- | --- | --- |
| `启动` | `启动素材处理` | 执行完整素材处理流程 |
| `状态` | `素材状态`、`处理状态` | 查看当前处理状态 |
| `表单` | `图片表单`、`上传表单`、`素材表单` | 返回飞书多维表格表单链接 |
| `回显` | `图片回显`、`文件夹回显`、`同步文件夹` | 同步本地成品素材到飞书云盘文件夹 |

DeerFlow 通道还支持这些通用斜杠命令：

| 指令 | 作用 |
| --- | --- |
| `/help` | 查看 DeerFlow 通道命令 |
| `/new` | 开一个新的对话线程 |
| `/status` | 查看当前对话线程 |
| `/models` | 查看可用模型 |
| `/memory` | 查看 memory 状态 |
| `/bootstrap` | 启动 setup/bootstrap 会话 |

## 完整流程

### 1. 表单上传

用户在飞书群里发：

```text
表单
```

机器人会返回 `FEISHU_BITABLE_FORM_URL` 配置的表单链接。

用户在表单里填写 `项目 / 名字 / 描述 / 文件 / 来源 / 来源二级分类 / 是否可商用`。

### 2. 启动处理

用户在飞书群里发：

```text
启动
```

系统执行：

```text
读取飞书多维表格
  -> 下载可商用图片附件到 image_compressor/images_raw/
  -> 压缩到 image_compressor/images_compressed/
  -> AI 识图
  -> 写入 案例素材清单_表格.md / 案例素材清单.xlsx / 素材分辨率.csv
  -> 按 项目 字段移动图片到 case_materials/
  -> 更新 runtime 状态文件
```

归档规则：

| 表单 `项目` | 本地归档 |
| --- | --- |
| 有值 | `case_materials/项目/` |
| 空 | `case_materials/通用素材库/` |

识图失败的图片会留在 `image_compressor/images_compressed/`，方便重试。

### 3. 回显到飞书云盘

用户在飞书群里发：

```text
回显
```

系统会把本地 `case_materials/` 同步到飞书云盘文件夹。

规则：

- 首次回显时，如果没有配置 `FEISHU_ECHO_DRIVE_FOLDER_TOKEN`，系统自动创建 `YQS PPT 图片素材库` 文件夹。
- 文件夹 token 和链接写入 `runtime/feishu_echo_drive_folder.json`。
- 云端目录结构和本地 `case_materials/` 保持一致。
- 已上传且文件大小、修改时间未变化的图片会跳过。
- 本次发起人会被自动授予 `full_access` 可管理权限，可以查看、修改和删除云盘文件夹内容。

回显目标是飞书云盘文件夹，不再使用飞书知识库。

## 本地目录

| 路径 | 用途 |
| --- | --- |
| `image_compressor/images_raw/` | 从飞书表格或机器人收到的原图 |
| `image_compressor/images_compressed/` | 压缩后的待识图图片 |
| `case_materials/` | 正式素材库，按项目归档 |
| `案例素材清单_表格.md` | Markdown 素材清单 |
| `案例素材清单.xlsx` | Excel 素材清单 |
| `素材分辨率.csv` | 图片分辨率记录 |
| `runtime/` | 本地运行状态、同步状态、token 用量 |
| `python/` | YQS 项目脚本 |
| `deer-flow/` | DeerFlow Web、飞书 Bot 和通道服务 |
| `scripts/` | 部署、配置、清理脚本 |

常见状态文件：

| 文件 | 用途 |
| --- | --- |
| `runtime/deerflow_agent_state.json` | `启动` / Dashboard 一键托管状态 |
| `runtime/recognition_state.json` | AI 识图进度 |
| `runtime/processed_files.json` | 已处理图片记录 |
| `runtime/ai_token_usage.json` | AI token 用量 |
| `runtime/bitable_sync_state.json` | 多维表格同步状态 |
| `runtime/feishu_echo_drive_folder.json` | 自动创建的飞书云盘文件夹 token 和链接 |
| `runtime/feishu_knowledge_sync_state.json` | 回显同步去重状态；名称保留历史兼容 |

## 启动服务

### 一键启动

在项目根目录：

```bash
./start_all.command
```

默认地址：

```text
Dashboard:    http://127.0.0.1:8765
DeerFlow Web: http://127.0.0.1:2026
```

### 分开启动

启动 DeerFlow / 飞书 Bot：

```bash
cd deer-flow
make docker-start
```

启动 Dashboard：

```bash
./start_dashboard.command
```

让办公室同事通过局域网访问 Dashboard：

```bash
YQS_DASHBOARD_HOST=0.0.0.0 ./start_dashboard.command
```

同事访问：

```text
http://工作站IP:8765
```

### 修改 `.env` 后重启

Docker gateway 读取的是 `deer-flow/.env`。

如果改了飞书、多维表格、表单链接或模型配置，建议重新创建容器：

```bash
cd deer-flow
make docker-stop
make docker-start
```

只 `docker restart deer-flow-gateway` 不一定会重新注入 env_file。

## 首次部署

推荐 Ubuntu 24.04 工作站。

基础依赖：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip make curl docker.io docker-compose-plugin
```

克隆项目：

```bash
git clone https://github.com/tsingque/YQS-Imagerepo-Robot.git
cd YQS-Imagerepo-Robot
```

打开配置向导：

```bash
bash scripts/configure_env_ubuntu.sh
```

默认访问：

```text
http://127.0.0.1:8787
```

如果工作站没有浏览器，可以在自己电脑上做 SSH 端口转发：

```bash
ssh -L 8787:127.0.0.1:8787 用户名@工作站IP
```

然后在自己电脑打开：

```text
http://127.0.0.1:8787
```

配置向导会写入：

```text
.env
deer-flow/.env
deer-flow/frontend/.env
```

旧文件会备份为 `.bak.<时间戳>`。

## 关键环境变量

不要把真实 `.env` 提交到 Git。

### AI 识图

```text
AI_PROVIDER=kimi
KIMI_API_KEY=
KIMI_MODEL=kimi-k2.6
KIMI_API_BASE=https://api.moonshot.cn/v1/chat/completions

GLM_API_KEY=
GLM_MODEL=glm-5v-turbo
GLM_OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
```

### 飞书应用

```text
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_RECEIVE_ID_TYPE=chat_id
FEISHU_RECEIVE_ID=
```

### 飞书多维表格和表单

```text
FEISHU_BITABLE_APP_TOKEN=
FEISHU_BITABLE_TABLE_ID=
FEISHU_BITABLE_VIEW_ID=
FEISHU_BITABLE_FORM_VIEW_ID=
FEISHU_BITABLE_FORM_URL=
FEISHU_WEB_BASE_URL=https://www.feishu.cn
```

`表单` 命令优先使用 `FEISHU_BITABLE_FORM_URL`。

### 飞书云盘回显

```text
FEISHU_ECHO_DRIVE_FOLDER_TOKEN=
FEISHU_ECHO_PARENT_TYPE=explorer
FEISHU_ECHO_FORCE_UPLOAD=false
```

`FEISHU_ECHO_DRIVE_FOLDER_TOKEN` 建议留空，让系统自动创建应用自有文件夹。只有在应用身份已经拥有目标文件夹权限时，才填写已有文件夹 token。

## 飞书权限要求

飞书开放平台应用至少需要覆盖以下能力：

- 接收群消息和事件订阅。
- 下载多维表格附件。
- 读取多维表格记录。
- 上传文件到云空间。
- 创建云盘文件夹。
- 给云盘文件夹添加协作者。
- 删除系统自己创建的云盘文件夹时，需要删除文件夹权限。

常见权限名称会因飞书后台展示语言而不同，通常在这些范围里：

```text
drive:drive
drive:file
docs:permission.member:create
space:document:delete
bitable:app
bitable:bitable
```

如果你使用手动创建的云盘文件夹，应用身份不一定天然有权限。最稳妥的方式是让系统自动创建文件夹。

## 多维表格校验

校验当前表格和字段：

```bash
python3 python/setup_bitable.py
```

默认只读校验，不创建字段、不删除字段、不修改表单。

只有明确需要脚本补齐表格结构时才执行：

```bash
python3 python/setup_bitable.py --apply
```

日常不要对手动维护的表单使用：

```bash
python3 python/setup_bitable.py --apply --prune-extra
```

## 清空测试环境

运营环境最后一次测试前，推荐用清理脚本。

先预览：

```bash
bash scripts/clear_project_environment.sh --dry-run --yes
```

只清空本地流程数据：

```bash
bash scripts/clear_project_environment.sh --yes
```

同时清空本地环境配置：

```bash
bash scripts/clear_project_environment.sh --yes --include-env
```

同时删除当前记录的飞书回显云盘文件夹：

```bash
bash scripts/clear_project_environment.sh --yes --include-feishu-echo-folder
```

把备份放到项目外：

```bash
YQS_CLEAN_BACKUP_DIR=/var/backups/yqs bash scripts/clear_project_environment.sh --yes --include-env --include-feishu-echo-folder
```

脚本会把可恢复数据移动到 `.cleanup_backups/<时间戳>/`，然后重建空目录。

会清理或重置：

- `runtime/`
- `case_materials/`
- `image_compressor/images_raw/`
- `image_compressor/images_compressed/`
- `image_compressor/images_recognized/`
- `案例素材清单_表格.md`
- `案例素材清单.xlsx`
- `素材分辨率.csv`

不会删除 `.env.example` 这类模板文件。

## 手动调试

直接跑完整 deterministic 流程：

```bash
python3 python/deerflow_runner.py --direct
```

查看托管状态：

```bash
python3 python/deerflow_runner.py --status
```

手动同步多维表格附件：

```bash
python3 python/bitable_sync.py
```

手动回显到飞书云盘：

```bash
python3 -B python/feishu_knowledge_base.py --root case_materials
```

给指定飞书 open_id 开当前回显文件夹可管理权限：

```bash
python3 -B python/feishu_knowledge_base.py --grant-reader-open-id ou_xxx
```

删除当前记录的回显文件夹：

```bash
python3 -B python/feishu_knowledge_base.py --delete-echo-folder --clear-echo-folder-state
```

查询飞书删除文件夹异步任务：

```bash
python3 -B python/feishu_knowledge_base.py --task-id 任务ID
```

## 排查

### 群里发 `表单` 没有返回正确链接

检查：

- `deer-flow/.env` 是否配置了 `FEISHU_BITABLE_FORM_URL`。
- `deer-flow/.env` 是否配置了 `FEISHU_BITABLE_FORM_VIEW_ID`。
- 修改 `.env` 后是否执行了 `make docker-stop && make docker-start`。

容器内验证：

```bash
docker exec deer-flow-gateway sh -c 'printenv FEISHU_BITABLE_FORM_URL'
```

### 群里发 `启动` 后提示暂无图片

检查：

- 多维表格里是否有附件。
- 附件字段是否叫 `文件`。
- `是否可商用` 是否为 `是`。
- `FEISHU_BITABLE_APP_TOKEN` 和 `FEISHU_BITABLE_TABLE_ID` 是否配置在 `deer-flow/.env`。
- 飞书应用是否有读取多维表格和下载附件权限。

### 群里发 `回显` 后看不到云盘文件夹

检查：

- 回显卡片里是否有“云盘权限：已给本次发起人开通可管理权限”。
- `runtime/feishu_echo_drive_folder.json` 是否存在。
- 如果你手动填写了 `FEISHU_ECHO_DRIVE_FOLDER_TOKEN`，确认应用身份确实有该文件夹权限。
- 优先让 `FEISHU_ECHO_DRIVE_FOLDER_TOKEN` 留空，由系统自动创建文件夹。

### Bot 没反应

重启 Docker 服务：

```bash
cd deer-flow
make docker-stop
make docker-start
```

查看日志：

```bash
cd deer-flow
make docker-logs-gateway
```

### Dashboard 访问不了

本机访问：

```text
http://127.0.0.1:8765
```

局域网访问需要这样启动：

```bash
YQS_DASHBOARD_HOST=0.0.0.0 ./start_dashboard.command
```

## 测试

常用测试：

```bash
python3 -m unittest tests.test_feishu_knowledge_base tests.test_clear_project_environment_script
python3 -m unittest discover tests
```

脚本语法检查：

```bash
bash -n scripts/clear_project_environment.sh
```

Docker 内飞书 parser 测试需要容器里有 pytest：

```bash
docker exec deer-flow-gateway sh -c 'cd /app/yqs_project/deer-flow/backend && uv run pytest tests/test_feishu_parser.py -q'
```

## Git 和安全

不要提交：

- `.env`
- `deer-flow/.env`
- `deer-flow/frontend/.env`
- `.cleanup_backups/`
- `runtime/`
- `case_materials/`
- `image_compressor/images_raw/`
- `image_compressor/images_compressed/`
- `image_compressor/images_recognized/`
- 本地生成的素材表格变更，除非你明确要把样例数据纳入版本

`.gitignore` 和 `.dockerignore` 已经尽量排除运行状态、密钥和图片队列。

提交前建议检查：

```bash
git status --short
git diff --cached --name-only
```

如果看到 `xlsx`、`csv`、素材图片或 `.env` 进入暂存区，先移出暂存区再提交。

## 当前已支持

- 飞书多维表格表单作为主输入入口。
- `表单` 命令返回表单链接。
- `启动` 命令执行完整素材处理流程。
- `状态` 命令查看进度。
- `回显` 命令把本地成品素材同步到飞书云盘文件夹。
- 回显文件夹自动创建。
- 回显发起人自动获得 `full_access` 可管理权限。
- 云端目录结构和本地 `case_materials/` 保持一致。
- 图片来源一级分类和二级分类进入识图上下文。
- `项目` 字段决定归档目录，`项目-名字` 写法已废弃。
- 群聊普通消息默认静默，明确命令或 @ 机器人才回复。
- Dashboard 查看状态、手动压缩、AI 识图和一键托管。
- AI token 用量记录和告警。
- 一键清空当前测试环境。

# YQS ImageRepoBot 使用说明

这是一个办公室素材收集、压缩、AI 识图和素材清单生成工具。

当前项目已整理为独立 Git 项目，DeerFlow 代码已作为本项目的一部分纳入版本管理，不再保留原 DeerFlow 仓库的 `.git` 关系。

GitHub 仓库：

```text
https://github.com/tsingque/YQS-Imagerepo-Robot
```

日常只需要记住三件事：

- 同事在飞书多维表格上传图片，并填写 `项目 / 名字 / 描述 / 文件 / 来源 / 来源二级分类 / 是否可商用`。
- 系统会先从飞书多维表格拉取待处理图片到 `image_compressor/images_raw/`，再继续压缩和 AI 识图。
- 可以在 Dashboard 人工查看和操作素材处理。
- 也可以在 DeerFlow 对话里输入「启动」，让系统按固定流程自动处理。

飞书 Bot 直接收图仍保留为兼容入口，但主入口建议使用飞书多维表格。

## 当前定位

本项目不是图片审核系统，而是一个 PPT 图片资产沉淀系统：

- 飞书多维表格负责收集人工输入和图片附件。
- 本地服务负责拉取、压缩、识别、归档和生成素材清单。
- DeerFlow 负责按固定流程触发和编排处理。
- Dashboard 负责人工查看、手动操作和一键托管。

多维表格里只保留这些输入字段：

```text
项目 / 名字 / 描述 / 文件 / 来源 / 来源二级分类 / 是否可商用
```

处理状态、AI 识别结果、本地路径、token 用量等运行信息只保存在本地，不写回飞书多维表格。

## 一、启动方式

### 方式 1：一键启动 Dashboard 和 DeerFlow

在项目根目录运行：

```bash
./start_all.command
```

这会先启动本地 Dashboard，再启动 DeerFlow Web。

Dashboard 默认地址：

```text
http://127.0.0.1:8765
```

DeerFlow Web 默认地址：

```text
http://127.0.0.1:2026
```

### 方式 2：分别启动

启动飞书收图 Bot / DeerFlow：

```bash
cd deer-flow
make docker-start
```

启动 Dashboard：

```bash
./start_dashboard.command
```

如果要让办公室同事访问 Dashboard：

```bash
YQS_DASHBOARD_HOST=0.0.0.0 ./start_dashboard.command
```

同事访问地址：

```text
http://工作站IP:8765
```

### Ubuntu 24.04 工作站迁移

在 Ubuntu 工作站首次部署时，建议先安装基础依赖：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip make curl
```

然后克隆项目：

```bash
git clone https://github.com/tsingque/YQS-Imagerepo-Robot.git
cd YQS-Imagerepo-Robot
```

运行 `.env` 网页配置向导：

```bash
bash scripts/configure_env_ubuntu.sh
```

脚本会在本机启动一个临时网页服务，默认地址：

```text
http://127.0.0.1:8787
```

在浏览器里填完后点击「保存配置文件」。如果工作站没有图形界面，可以在自己电脑上通过 SSH 端口转发访问：

```bash
ssh -L 8787:127.0.0.1:8787 用户名@工作站IP
```

然后在自己电脑浏览器打开：

```text
http://127.0.0.1:8787
```

这个网页会引导填写：

- GLM / Kimi 识图配置
- 飞书应用 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`
- 飞书多维表格 `app_token / table_id / view_id`
- DeerFlow 后端模型配置
- Dashboard token、内部 token、Cookie secret 等服务密钥

脚本会生成或更新：

```text
.env
deer-flow/.env
deer-flow/frontend/.env
```

旧配置备份会保留为 `.bak.<时间戳>`。

### 校验飞书多维表格

确保 `.env` 中已有：

```text
FEISHU_APP_ID=...
FEISHU_APP_SECRET=...
```

并在飞书开放平台给应用开启多维表格创建、读取、写入、附件下载和云文档权限设置相关权限后，运行：

```bash
python3 python/setup_bitable.py
```

脚本默认只做只读校验，不会创建字段、删除字段或修改提交表单；本地代码以你在飞书里手动维护的表单字段为准。校验会输出当前表格里识别到的字段、缺失字段、表单视图，以及需要写入 `.env` 的：

```text
FEISHU_BITABLE_APP_TOKEN
FEISHU_BITABLE_TABLE_ID
FEISHU_BITABLE_VIEW_ID
```

如果确实需要让脚本创建或补齐表格结构，必须显式执行：

```bash
python3 python/setup_bitable.py --apply
```

如果还要删除不在预期范围内的字段，需额外加 `--prune-extra`。日常不要对手动维护的提交表单使用这个参数。

当前多维表格建议只保留以下字段：

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `项目` | 文本 | 素材所属项目；为空时进入通用素材库 |
| `名字` | 文本 | 素材名称，不再使用 `项目-名字` 写法 |
| `描述` | 文本 | 人工备注、时间、使用场景、特殊说明 |
| `文件` | 附件 | 图片附件 |
| `来源` | 单选 | 拍摄 / 下载 / 截图 / AI生成 / 渲染 |
| `来源二级分类` | 单选或文本 | 暂定为 `计划`，后续按来源体系细化 |
| `是否可商用` | 单选 | 是 / 否 |

其中 `来源`、`来源二级分类` 和 `是否可商用` 可以在飞书里设置为选项字段。系统会读取选项的显示值。

使用 `--apply` 时，如果需要让单位内用户能直接打开这张表，脚本会额外尝试设置“组织内有链接可编辑”。飞书要求补开以下权限之一，推荐优先开：

```text
docs:permission.setting:write_only
```

如果权限页显示中文名称，通常在“云文档/权限设置”附近，含义是允许应用修改云文档权限设置。飞书错误提示中也可能列出可替代的更高权限，例如：

```text
drive:drive
drive:file
bitable:bitable
docs:doc
sheets:spreadsheet
wiki:wiki
docx:document
```

### 飞书文件夹回显配置

群聊发送 `回显` 会把本地成品素材同步到飞书云空间文件夹。你创建的文件夹链接：

```text
https://wu35s592xy.feishu.cn/drive/folder/QDMwfuA16lSavSdosZ2cUKGNnG7
```

对应配置如下：

```text
FEISHU_ECHO_DRIVE_FOLDER_TOKEN=QDMwfuA16lSavSdosZ2cUKGNnG7
FEISHU_ECHO_PARENT_TYPE=explorer
FEISHU_ECHO_FORCE_UPLOAD=false
```

## 二、两种控制方式

### 1. 人工控制：Dashboard

打开：

```text
http://127.0.0.1:8765
```

Dashboard 可以做这些事：

- 查看 raw / compressed / recognized / finished 数量
- 查看待处理图片预览
- 手动压缩 `images_raw`
- 检查压缩图相似度
- 手动启动 AI 识图
- 点击「一键托管」执行完整流程
- 查看 DeerFlow 托管状态

Dashboard 的「一键托管」和 DeerFlow 的「启动」使用同一个 runner，都会写入：

```text
runtime/deerflow_agent_state.json
```

### 2. 自动控制：DeerFlow 对话

在 DeerFlow 对话中输入：

```text
启动
```

或：

```text
启动素材处理
```

系统会按固定顺序执行：

```text
同步飞书多维表格待处理记录
  -> 下载可用图片附件到 images_raw
  -> 检查 images_raw
  -> 压缩到 images_compressed
  -> 删除已成功压缩的 raw 原图
  -> AI 识图 images_compressed
  -> 写入素材清单
  -> 按多维表格 `项目` 字段移动成功识图图片到 case_materials
  -> 发送飞书通知
  -> DeerFlow 返回中文摘要
```

查询当前进度：

```text
状态
```

私聊普通聊天仍走 DeerFlow 原有对话逻辑；群聊普通消息默认静默，需要 @ 机器人或发送明确命令。

飞书群聊里现在有两个轻量命令：

```text
表单
回显
```

发送 `表单` 时，机器人会把图片上传表单链接发到当前群聊。发送 `回显` 时，机器人会把本地 `case_materials/` 中已经处理并归类好的图片上传到已配置的飞书文件夹；云端目录结构会尽量和本地保持一致。

除 `启动`、`状态`、`表单`、`回显` 这类明确命令，以及对机器人卡片的回复外，飞书群聊普通消息默认不再触发回复；需要普通问答时请 @ 机器人。

如果在飞书里给机器人发送：

```text
启动
```

机器人会直接执行同一套素材处理流程。此前“文本消息不回复”的限制已经解除。

## 三、完整使用流程

### 1. 飞书多维表格上传图片

在飞书多维表格中新增一行，并填写：

| 字段 | 用途 |
| --- | --- |
| `项目` | 素材所属项目，例如 `minduck`、`均胜智能座舱` |
| `名字` | 素材主名称，例如 `minduck图标` |
| `描述` | 人工备注，例如 `2026-minduck图标`、`董办-xxx生活照片` |
| `文件` | 图片附件 |
| `来源` | 拍摄 / 下载 / 截图 / AI生成 / 渲染 |
| `来源二级分类` | 暂定填写 `计划` |
| `是否可商用` | `是` 进入处理流程；`否` 同步后跳过 |

多维表格和表单只保留这些输入字段。处理状态、AI 识别结果、本地路径等信息只保存在本地运行状态和素材清单里，不写回飞书表格。

`是否可商用` 是入库开关：`是` 表示已确认有商用权限，可以下载、压缩、识图并进入素材库；`否` 表示不处理、不进入素材库。AI 只读取这个字段，不判断或改变商用权限。

### 2. 飞书文件夹回显

`回显` 会把本地成品素材库同步到飞书文件夹，而不是把图片直接发回群聊。

同步源：

```text
case_materials/
```

同步规则：

- 本地 `case_materials/项目/图片.jpg` 会进入飞书目标位置的 `项目/图片.jpg`。
- 本地存在多级目录时，云端会按相同层级创建文件夹。
- 已上传且本地文件大小和修改时间未变化的图片会跳过，避免重复上传。
- 系统只使用 `FEISHU_ECHO_DRIVE_FOLDER_TOKEN` 指向的飞书文件夹，不需要 user token。

### 3. 兼容入口：飞书 Bot 收图片

在飞书里打开 ImageRepoBot，直接发送图片或截图。

Bot 会回复类似：

```text
素材已入库

已收到 1 张图片，已保存到 images_raw。
当前已有 12 张图片在待处理区。
```

收到的图片会进入：

```text
image_compressor/images_raw/
```

### 4. 启动处理

二选一：

- 在 Dashboard 点击「一键托管」
- 在 DeerFlow 输入「启动」

处理完成后会生成或更新：

```text
案例素材清单_表格.md
案例素材清单.xlsx
素材分辨率.csv
```

成功识图后的图片会直接移动到正式素材库：

```text
case_materials/
```

多维表格以 `项目` 字段决定归档位置：

- `项目` 有值：图片会进入 `case_materials/项目/`。如果项目文件夹不存在，系统会自动创建。
- `项目` 为空：图片会进入 `case_materials/通用素材库/`。

原来的 `项目-名字` 写法已经废弃，`名字` 字段只写素材名称。

例如：

| 多维表格项目 | 多维表格名字 | 归档位置 |
| --- | --- |
| `董办` | `张三生活照` | `case_materials/董办/` |
| 空 | `minduck图标` | `case_materials/通用素材库/` |

AI 识图 token 用量会记录在 `runtime/ai_token_usage.json`。如果设置 `AI_TOKEN_WARN_TOTAL` 为大于 0 的数字，累计 token 达到阈值时会写入 `runtime/alerts.json`。

识图失败的 compressed 图片会保留在：

```text
image_compressor/images_compressed/
```

方便后续重试，不会误删。

## 四、常用目录和状态文件

| 路径 | 用途 |
| --- | --- |
| `image_compressor/images_raw/` | 飞书收到的原图，等待压缩 |
| `image_compressor/images_compressed/` | 压缩后的待识图图片 |
| `case_materials/` | 正式素材库，按项目或通用素材库归档 |
| `案例素材清单_表格.md` | Markdown 素材清单 |
| `案例素材清单.xlsx` | Excel 素材清单 |
| `素材分辨率.csv` | 图片分辨率记录 |
| `runtime/deerflow_agent_state.json` | DeerFlow / Dashboard 共享托管状态 |
| `runtime/recognition_state.json` | AI 识图进度 |
| `runtime/ai_token_usage.json` | AI token 调用监控 |
| `runtime/processed_files.json` | 已识图文件记录 |
| `python/` | 项目脚本 |
| `deer-flow/` | DeerFlow 和飞书 Bot 服务 |
| `scripts/configure_env_ubuntu.sh` | Ubuntu 工作站 `.env` 网页配置向导启动脚本 |
| `scripts/configure_env_web.py` | `.env` 网页配置向导服务 |

飞书图片来源记录在：

```text
image_compressor/images_raw/_feishu_sources.jsonl
```

## 五、命令行调试

直接执行完整 deterministic 流程：

```bash
python3 python/deerflow_runner.py --direct
```

查看托管状态：

```bash
python3 python/deerflow_runner.py --status
```

如果 `images_raw` 和 `images_compressed` 都没有图片，runner 会返回：

```text
暂无图片，请先在飞书多维表格上传图片，或通过飞书 Bot 发送图片。
```

如果已有任务正在运行，重复启动会返回：

```text
素材处理任务正在运行，请稍后查看状态。
```

## 六、办公室部署建议

建议把项目部署在一台公司办公室 Ubuntu 24.04 工作站上。

工作站需要：

- 长期开机
- 能联网
- 能运行 Docker / Docker Compose
- 能登录飞书 Bot
- 和同事在同一个办公室网络里

最好让 IT 给这台工作站固定一个 IP，例如：

```text
192.168.1.88
```

这样同事和老板就可以固定访问：

```text
http://192.168.1.88:8765
```

如果工作站没有图形界面，可以只运行 DeerFlow Docker 服务和 Dashboard 后端；同事通过局域网 IP 访问 Dashboard。

## 七、重启和排查

如果飞书 Bot 没反应，重启 DeerFlow / Bot：

```bash
cd deer-flow
make docker-start
```

如果 Dashboard 打不开，重新启动：

```bash
./start_dashboard.command
```

如果办公室同事访问不了，确认 Dashboard 是用这个方式启动的：

```bash
YQS_DASHBOARD_HOST=0.0.0.0 ./start_dashboard.command
```

如果 DeerFlow 输入「启动」没有触发素材流程，检查：

- DeerFlow Web 是否已启动
- 项目根目录是否存在 `deer-flow/`
- `DEER_FLOW_PROJECT_ROOT` 或 `YQS_PROJECT_ROOT` 是否指向本项目根目录
- `.env` 是否配置了 Kimi / GLM / 飞书相关密钥
- 飞书机器人所在容器是否已经使用最新代码重新启动

如果飞书里提示“暂无图片”，但你已经在多维表格传了图片，优先检查：

- `.env` 里是否有 `FEISHU_BITABLE_APP_TOKEN`
- `.env` 里是否有 `FEISHU_BITABLE_TABLE_ID`
- 应用是否有多维表格读取和附件下载权限
- 多维表格的附件字段是否叫 `文件`
- `是否可商用` 是否填写为 `是`

如果要清空本地素材状态和多维表格记录：

```bash
python3 python/reset_material_state.py
```

该脚本会清空本地 MD / CSV / XLSX 数据内容但保留文件格式，并清空当前配置的飞书多维表格记录。执行前会把现有图片归档到桌面文件夹。

## 八、当前已支持

- 飞书多维表格作为主输入源
- 多维表格只读校验，写入结构需显式 `--apply`
- 多维表格字段：`项目 / 名字 / 描述 / 文件 / 来源 / 来源二级分类 / 是否可商用`
- 多维表格附件下载到 `images_raw`
- `是否可商用 = 否` 时跳过处理
- `项目` 字段决定归档文件夹，`项目-名字` 写法已废弃
- 飞书群聊发送 `表单` 会返回表单链接
- 飞书群聊发送 `回显` 会把 `case_materials/` 同步到飞书文件夹
- 飞书文件夹模式可直接使用已创建文件夹 token，不需要 user token
- 飞书群聊普通消息默认静默，@ 机器人或发送明确命令才回复
- 成品素材直接进入 `case_materials/项目` 或 `case_materials/通用素材库`
- 飞书 Bot 自动接收图片
- 图片直接进入 `images_raw`
- 飞书卡片回复收图结果
- Dashboard 查看素材状态
- Dashboard 手动压缩、识图、查重
- Dashboard 一键托管完整流程
- DeerFlow 输入「启动」执行完整流程
- DeerFlow 输入「状态」查看当前进度
- Dashboard 和 DeerFlow 共享同一个状态文件
- raw 只在压缩成功后删除
- compressed 只在识图成功后移动
- 识图失败的 compressed 图片保留用于重试
- AI 识图 prompt 已改为 PPT 调用导向，默认输出“适合用于 xxx”
- AI token 用量记录到 `runtime/ai_token_usage.json`
- 多维表格容量和大批量拉取告警写入 `runtime/alerts.json`

## 九、Git 与安全

本项目根目录已经是 Git 仓库，当前远端可设置为：

```bash
git remote add origin https://github.com/tsingque/YQS-Imagerepo-Robot.git
```

常规提交和推送：

```bash
git status
git add .
git commit -m "Update project"
git push
```

不要提交以下内容：

- `.env`
- `deer-flow/.env`
- `deer-flow/frontend/.env`
- `runtime/`
- 本地 raw / compressed 图片队列
- 桌面上的一次性密钥备份文档

`.gitignore` 已经默认排除这些文件。迁移到公司工作站后，使用 `scripts/configure_env_ubuntu.sh` 打开网页向导重新生成 `.env`，不要把旧密钥长期留在仓库或桌面文档里。

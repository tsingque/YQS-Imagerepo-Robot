# YQS-Imagerepo 技术版：部署与集成说明

## 一、系统职责

YQS-Imagerepo 是一个本地优先的素材处理系统。

当前系统职责包括：

- 本地图片接收
- 图片移动和清理
- 图片压缩
- 素材状态 Dashboard
- AI 识图规则管理
- Markdown 表格处理
- Excel 追加
- 分辨率索引维护
- 后续飞书和 DeerFlow 集成预留

## 二、运行环境

推荐环境：

```text
macOS
Python 3.9+
Pillow
openpyxl
```

检查 Python：

```bash
python3 --version
```

安装依赖：

```bash
pip3 install -r image_compressor/requirements.txt
pip3 install openpyxl
```

## 三、目录结构

```text
YQS-Material-Repository-Project/
  case_materials/
  dashboard/
    index.html
    styles.css
    app.js
  docs/
  feishu_trans_repo/
  image_compressor/
    images_raw/
    images_compressed/
    compression_report.md
    requirements.txt
  md_trans_repo/
  python/
    compress.py
    md_table_to_material_xlsx.py
    prepare_feishu_raw.py
    server.py
  rules/
    image_recognition.md
  案例素材清单_表格.md
  案例素材清单.xlsx
  素材分辨率.csv
  start_dashboard.command
```

## 四、启动 Dashboard

一键启动：

```bash
./start_dashboard.command
```

手动启动：

```bash
python3 python/server.py
```

默认监听：

```text
127.0.0.1:8765
```

访问：

```text
http://127.0.0.1:8765
```

## 五、后端 API

当前 `python/server.py` 提供：

```text
GET  /api/status
GET  /api/file?path=...
POST /api/load-images
POST /api/clear-images-raw
```

### `/api/status`

返回各目录图片数量、大小和预览图。

统计目录：

- `feishu_trans_repo/`
- `image_compressor/images_raw/`
- `image_compressor/images_compressed/`
- `case_materials/`

### `/api/load-images`

调用 `prepare_feishu_raw.py` 中的逻辑：

- 从 `feishu_trans_repo/` 加载图片
- 移动到 `image_compressor/images_raw/`
- 删除源目录中的 `.py`

### `/api/clear-images-raw`

清空：

```text
image_compressor/images_raw/
```

不影响：

```text
case_materials/
```

## 六、脚本说明

### `python/prepare_feishu_raw.py`

功能：

- 兼容 `feishu_trans_repo` 和 `feishu-trans-repo`
- 递归查找图片
- 移动图片到 `image_compressor/images_raw/`
- 重名自动加后缀
- 删除源目录中的 `.py` 文件

命令：

```bash
python3 python/prepare_feishu_raw.py --dry-run
python3 python/prepare_feishu_raw.py
```

### `python/compress.py`

功能：

- 读取 `image_compressor/images_raw/`
- 输出到 `image_compressor/images_compressed/`
- 生成 `image_compressor/compression_report.md`

压缩策略：

- JPG/JPEG：quality 85
- WebP：quality 85
- PNG：优先无损，必要时量化
- 最长边大于 2560px 时缩放

命令：

```bash
python3 python/compress.py
```

### `python/md_table_to_material_xlsx.py`

功能：

- 读取 `案例素材清单_表格.md`
- 生成时间戳 temp workbook
- 追加 temp 行到 `案例素材清单.xlsx`
- 保持目标 Excel 主表结构
- 将 temp 移动到 `md_trans_repo/`

目标 Excel 主表结构：

```text
Sheet: 案例素材清单
Columns:
文件名
案例名称
图片内容
想放在哪（章节/论点）
配图说明文字（图注/要点）
关键数据
来源/版权
状态
存放文件夹
```

Markdown 表格结构：

```text
分类
文件名
案例名称
图片内容
想放在哪（章节/论点）
配图说明文字（图注/要点）
关键数据
来源/版权
状态
```

映射规则：

```text
分类 -> 存放文件夹
```

命令：

```bash
python3 python/md_table_to_material_xlsx.py --dry-run
python3 python/md_table_to_material_xlsx.py
```

## 七、大模型识图约束

识图规则文件：

```text
rules/image_recognition.md
```

模型输入：

- 图片文件
- 原始文件名
- 文件路径
- 分辨率
- 文件大小

模型输出最终必须落到：

```text
案例素材清单_表格.md
案例素材清单.xlsx
素材分辨率.csv
```

JSON 只允许作为内部中间对象，不作为最终产物。

### 字段约束

模型必须生成：

- 分类
- 文件名
- 案例名称
- 图片内容
- PPT 用途
- 图注
- 关键数据
- 来源/版权
- 状态
- 分辨率

### 命名约束

如果原文件名没有中文，必须生成中文语义化文件名。

示例：

```text
image1.png -> 均胜_Joyspace+_智能座舱交互界面.png
IMG_8821.jpg -> 智慧船舱_驾驶台实拍图.jpg
```

### 版权约束

模型不能假设第三方授权。

默认：

- 第三方品牌 Logo：需确认授权使用范围
- 第三方案例素材：需确认授权使用范围
- 地图素材：需确认使用合规性

### 不确定性约束

模型不得编造。

无法判断时：

```text
状态 = 需人工确认
分类 = 其他_待判断
```

## 八、模型 Provider 预留

当前系统已提供 GLM 批量识图 worker，并支持后续继续扩展其他模型 Provider。

建议 `.env`：

```bash
AI_PROVIDER=glm
GLM_API_KEY=your_key
GLM_MODEL=glm-5v-turbo
```

当前已实现：

```text
python/glm_client.py          # GLM API 调用
python/recognition_worker.py  # 批量识图 worker
python/material_writers.py    # 写入 MD / XLSX / CSV
```

执行流程：

```text
read image from image_compressor/images_compressed
  -> call GLM vision model
  -> parse internal structured result
  -> update 案例素材清单_表格.md
  -> update 素材分辨率.csv
  -> append 案例素材清单.xlsx
  -> move image to image_compressor/images_recognized/
```

命令：

```bash
python3 python/recognition_worker.py --dry-run
python3 python/recognition_worker.py
```

## 九、飞书与 DeerFlow 集成预留

当前已接入飞书消息通知，尚未接入飞书图片上传事件和 DeerFlow 编排。

预留架构：

```text
Feishu
  -> feishu_trans_repo/
  -> DeerFlow runner
  -> prepare_feishu_raw
  -> compress
  -> recognition_worker
  -> material_writers
  -> notify Feishu
```

建议后续新增：

```text
python/feishu_client.py
python/deerflow_runner.py
runtime/deerflow_state.json
runtime/processed_files.json
```

飞书 `.env` 配置：

```bash
FEISHU_APP_ID=your_feishu_app_id
FEISHU_APP_SECRET=your_feishu_app_secret
FEISHU_RECEIVE_ID_TYPE=chat_id
FEISHU_RECEIVE_ID=your_chat_id
FEISHU_NOTIFY_ON_RECOGNITION=true
```

当前飞书能力：

- Dashboard 显示飞书配置状态
- Dashboard 可发送测试通知
- GLM 识图完成后可自动发送处理结果通知

当前飞书未启用：

- 飞书事件回调
- 飞书图片自动下载
- 飞书卡片按钮

## 十、部署步骤

### 1. 拉取或复制项目

确保目录完整：

```text
dashboard/
python/
rules/
image_compressor/
case_materials/
```

### 2. 安装依赖

```bash
pip3 install -r image_compressor/requirements.txt
pip3 install openpyxl
```

### 3. 创建必要目录

```bash
mkdir -p feishu_trans_repo
mkdir -p image_compressor/images_raw
mkdir -p image_compressor/images_compressed
mkdir -p md_trans_repo
```

### 4. 启动服务

```bash
./start_dashboard.command
```

### 5. 验证页面

访问：

```text
http://127.0.0.1:8765
```

确认能看到：

- 当前图片总数
- 待加载
- images_raw
- 压缩输出
- Codex 成品图

### 6. 验证脚本

```bash
python3 python/prepare_feishu_raw.py --dry-run
python3 python/md_table_to_material_xlsx.py --dry-run
```

## 十一、运维注意事项

- 所有新增 Python 脚本放入 `python/`
- 所有规则放入 `rules/`
- 不要在 Dashboard 前端暴露 API Key
- 不要把 `.env` 提交或发送给外部
- Excel 追加前优先跑 `--dry-run`
- 大批量识图前先抽样验证
- 正式素材库入库前保留人工确认
- 自动入库应晚于人工确认机制上线

## 十二、常用命令

```bash
./start_dashboard.command
python3 python/server.py
python3 python/prepare_feishu_raw.py --dry-run
python3 python/prepare_feishu_raw.py
python3 python/compress.py
python3 python/md_table_to_material_xlsx.py --dry-run
python3 python/md_table_to_material_xlsx.py
```

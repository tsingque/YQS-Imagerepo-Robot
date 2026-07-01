# YQS-Imagerepo 全工作流程与部署流程

## 一、系统定位

YQS-Imagerepo 是面向售前方案、智能座舱案例材料和 PPT 自动化生成的图片素材中台。

系统已完成从“图片收集、预处理、压缩、AI 识图、结构化入表、可视化管理、人工复核”到“后续入库复用”的完整闭环设计。它不是单纯的图片文件夹，而是一套可被业务人员查看、可被 AI 理解、可被后续自动化流程调用的素材管理系统。

系统核心目标包括：

- 将零散图片转化为结构化素材资产
- 降低人工找图、命名、分类和填表成本
- 为售前 PPT、方案文档和案例页生成提供统一素材入口
- 保持素材库对业务人员友好，对 AI 工作流可读

## 二、当前目录结构

项目根目录采用以下结构：

```text
YQS-Material-Repository-Project/
  case_materials/                 # 正式素材库
  dashboard/                      # 本地可视化管理页面
  docs/                           # 项目文档
  feishu_trans_repo/              # 飞书或外部图片临时接收目录
  image_compressor/
    images_raw/                   # 待处理原始图片
    images_compressed/            # 压缩输出图片
    compression_report.md         # 压缩报告
  md_trans_repo/                  # Markdown 转 Excel 的临时产物归档
  python/                         # 所有 Python 脚本
  rules/
    image_recognition.md          # AI 识图规则 Prompt
  案例素材清单_表格.md             # 单表结构素材清单，供程序处理
  案例素材清单.xlsx                # 业务查看和交付用 Excel
  素材分辨率.csv                  # 图片分辨率索引
  start_dashboard.command         # 一键启动脚本
```

## 三、素材流转全流程

### 1. 图片进入临时接收区

外部图片统一先进入：

```text
feishu_trans_repo/
```

该目录作为外部素材入口，适合接收来自飞书、人工拖拽、截图导出或其他系统同步过来的图片。

系统要求：

- 不直接把外部图片放入正式素材库
- 不直接写入 `case_materials/`
- 所有新图片先进入临时接收区，再由工具加载到处理区

### 2. 加载图片到待处理目录

系统已提供脚本：

```bash
python3 python/prepare_feishu_raw.py
```

它负责：

- 从 `feishu_trans_repo/` 读取图片
- 移动到 `image_compressor/images_raw/`
- 自动跳过非图片文件
- 删除临时目录中的 `.py` 文件
- 避免重名覆盖，必要时自动生成后缀

可预览执行：

```bash
python3 python/prepare_feishu_raw.py --dry-run
```

### 3. 图片压缩与标准化

待处理图片进入：

```text
image_compressor/images_raw/
```

系统已提供压缩脚本：

```bash
python3 python/compress.py
```

压缩输出进入：

```text
image_compressor/images_compressed/
```

压缩策略：

- JPG/JPEG：质量 85
- WebP：质量 85
- PNG：优先无损压缩，较大图片自动量化
- 图片最长边超过 2560px 时等比缩放
- 原始图片不覆盖，压缩结果单独输出

系统同时生成：

```text
image_compressor/compression_report.md
```

### 4. AI 识图与结构化

系统的 AI 识图规则已沉淀在：

```text
rules/image_recognition.md
```

识图过程以压缩后的图片和文件元信息为输入，生成面向素材清单的字段，而不是只做简单视觉描述。系统默认识别 `image_compressor/images_compressed/` 中的压缩图，以降低图片 token 和调用成本。

识图结果最终写入以下文件：

```text
案例素材清单_表格.md
案例素材清单.xlsx
素材分辨率.csv
```

系统不把 JSON 或单独 Markdown 作为最终产物。JSON 只允许作为程序内部中间结构。

### 5. Markdown 表格转 Excel

系统已提供脚本：

```bash
python3 python/md_table_to_material_xlsx.py
```

它负责：

- 读取 `案例素材清单_表格.md`
- 生成带处理时间的 `temp.xlsx`
- 将 temp 中的数据追加到 `案例素材清单.xlsx`
- 保持 `案例素材清单.xlsx` 的工作表结构、表头和样式
- 将 temp 文件移动到 `md_trans_repo/`

预览执行：

```bash
python3 python/md_table_to_material_xlsx.py --dry-run
```

正式执行：

```bash
python3 python/md_table_to_material_xlsx.py
```

### 6. 正式素材库归档

正式素材库位于：

```text
case_materials/
```

当前正式分类包括：

- `品牌标识_自有`
- `品牌标识_合作伙伴`
- `地图素材`
- `产品素材_Minduck`
- `案例实拍_智慧船舶`
- `案例素材_均胜智能座舱`
- `案例素材_常熟汽车`

系统原则：

- AI 可以建议入库目录和语义化文件名
- 重要素材入库前保留人工复核空间
- 进入正式素材库的图片必须具备业务含义、清晰分类和可读命名

## 四、可视化 Dashboard

系统已提供本地可视化管理页面。

启动方式：

```bash
./start_dashboard.command
```

或：

```bash
python3 python/server.py
```

默认访问地址：

```text
http://127.0.0.1:8765
```

Dashboard 已展示：

- 当前图片总数
- `feishu_trans_repo/` 待加载图片数
- `image_compressor/images_raw/` 待处理图片数
- `image_compressor/images_compressed/` 压缩输出数量
- `case_materials/` 成品素材数量
- 图片预览
- 加载到 `images_raw`
- 清空 `images_raw`

Dashboard 的定位是给老板、业务人员和非技术使用者操作。复杂流程隐藏在后端脚本和任务编排中。

## 五、大模型识图约束

### 1. 模型职责

大模型只负责识别、归类、命名建议和结构化字段生成，不直接决定正式入库。

模型必须输出适合写入素材清单的字段：

- 分类
- 文件名
- 案例名称
- 图片内容
- 想放在哪（章节/论点）
- 配图说明文字（图注/要点）
- 关键数据
- 来源/版权
- 状态
- 分辨率

### 2. 命名约束

如果原始文件名不包含中文，模型必须根据识图结果生成中文语义化文件名。

示例：

```text
image1.png -> 均胜_Joyspace+_智能座舱交互界面.png
IMG_8821.jpg -> 智慧船舱_驾驶台实拍图.jpg
logo.png -> JOMEC_品牌标识.png
```

新文件名必须同步写入：

- `案例素材清单_表格.md`
- `案例素材清单.xlsx`
- `素材分辨率.csv`

### 3. 分类约束

模型优先使用现有分类：

- 品牌标识_自有
- 品牌标识_合作伙伴
- 地图素材
- 产品素材_Minduck
- 案例实拍_智慧船舶
- 案例素材_智能座舱
- 其他_待判断

如果图片能明确识别客户或项目，可以建议更具体的新目录，例如：

```text
案例素材_某客户智能座舱
```

### 4. 分辨率约束

模型或执行器必须结合图片分辨率判断可用性：

- 宽度 ≥ 1920 或高度 ≥ 1080：适合作为 PPT 主视觉或大图
- 宽度 ≥ 1280 或高度 ≥ 720：适合作为案例页主图或界面展示
- Logo 和图标可以较小，但必须判断清晰度
- 宽高均小于 400 的复杂截图应标记为需高清版本
- 模糊、裁切严重、水印明显、文字不可读的图片应标记为需优化或不建议使用

### 5. 版权约束

模型不能假设第三方素材已授权。

默认规则：

- 自有品牌、自研产品、自有实拍：`自有，需确认`
- 第三方品牌 Logo：`第三方品牌标识，需确认授权使用范围`
- 第三方案例素材：`第三方案例素材，需确认授权使用范围`
- 地图素材：`地图素材来源待确认，需确认使用合规性`
- 奖项标识：`第三方奖项标识，需确认授权使用范围`

### 6. 不确定性约束

模型不得编造客户名称、项目背景、授权状态或技术参数。

当无法判断时：

- 状态写 `需人工确认`
- 分类写 `其他_待判断`
- 图注保持保守
- 不进入自动正式入库流程

## 六、部署流程

### 1. 本地环境要求

推荐环境：

```text
macOS
Python 3.9+
openpyxl
Pillow
```

项目已使用 Python 脚本作为主执行环境。

检查 Python：

```bash
python3 --version
```

安装依赖：

```bash
pip3 install -r image_compressor/requirements.txt
pip3 install openpyxl
```

如果后续启用 GLM 或其他视觉模型，需要额外安装对应 SDK 或 HTTP 请求库。

### 2. 环境变量配置

项目根目录使用 `.env` 保存模型和外部系统配置。

示例：

```bash
AI_PROVIDER=glm
GLM_API_KEY=your_glm_api_key
GLM_MODEL=glm-5v-turbo

FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_RECEIVE_ID_TYPE=chat_id
FEISHU_RECEIVE_ID=
FEISHU_NOTIFY_ON_RECOGNITION=true
```

当前阶段已接入飞书消息通知，尚未接入飞书图片上传事件回调。

安全要求：

- `.env` 不上传、不转发、不写入文档正文
- API Key 只允许后端 Python 读取
- Dashboard 前端不暴露任何模型 Key

### 3. 启动 Dashboard

双击：

```text
start_dashboard.command
```

或在终端运行：

```bash
./start_dashboard.command
```

如果需要手动启动：

```bash
python3 python/server.py
```

启动后访问：

```text
http://127.0.0.1:8765
```

### 4. 标准处理命令

加载外部图片：

```bash
python3 python/prepare_feishu_raw.py
```

压缩图片：

```bash
python3 python/compress.py
```

MD 表格追加到 Excel：

```bash
python3 python/md_table_to_material_xlsx.py
```

## 七、日常使用流程

### 业务人员流程

1. 打开 Dashboard
2. 查看当前待处理图片数量
3. 点击加载图片到 `images_raw`
4. 先完成图片压缩，再等待 AI 识图或技术人员触发识图流程
5. 查看更新后的 Excel 清单
6. 对需确认素材进行人工复核

### 技术人员流程

1. 将外部图片放入 `feishu_trans_repo/`
2. 运行 `prepare_feishu_raw.py`
3. 运行 `compress.py`
4. 执行 AI 识图流程
5. 更新 `案例素材清单_表格.md`
6. 运行 `md_table_to_material_xlsx.py`
7. 检查 `案例素材清单.xlsx`
8. 根据复核结果整理正式素材库

## 八、数据产物说明

### 案例素材清单_表格.md

程序处理用主表。

特点：

- 单张 Markdown 表格
- 包含 `分类` 列
- 适合被脚本解析和追加

### 案例素材清单.xlsx

业务交付和查看用主表。

特点：

- 保留正式 Excel 表结构
- 包含 `案例素材清单` 和 `填写说明` 工作表
- 每次由脚本追加数据行

### 素材分辨率.csv

图片分辨率索引。

字段：

```csv
filename,resolution
```

要求：

- 文件名必须与清单中的文件名一致
- 如果 AI 重命名图片，CSV 同步使用新文件名

## 九、飞书与 DeerFlow 集成

系统已接入飞书消息通知，并预留 DeerFlow 编排和飞书图片上传事件接入位置。

当前飞书能力：

- Dashboard 显示飞书配置状态
- Dashboard 可发送测试通知
- GLM 识图完成后可自动发送处理结果通知

当前尚未启用：

- 飞书事件回调
- 飞书图片自动下载
- 飞书卡片按钮

后续接入方向：

```text
飞书上传图片
  ↓
feishu_trans_repo/
  ↓
DeerFlow 编排任务
  ↓
加载 / 压缩 / 识图 / 写表 / 通知
  ↓
Dashboard 展示结果
```

DeerFlow 后续承担流程编排职责，不替代 Dashboard，也不直接面向业务人员。

飞书后续承担：

- 图片输入入口
- 处理完成通知
- 人工确认提醒
- 结果链接分发

## 十、运维与注意事项

- 所有 Python 脚本统一放在 `python/`
- 新增规则统一放在 `rules/`
- 临时转换产物归档到 `md_trans_repo/`
- 不要直接修改压缩输出目录作为正式素材库
- 不要将未识别、未命名、未确认版权的图片放入 `case_materials/`
- Excel 追加前建议先运行 `--dry-run`
- 大批量识图前建议先抽样 5 到 10 张验证模型输出质量
- 自动入库功能必须晚于人工复核功能上线

## 十一、当前启动入口汇总

```bash
./start_dashboard.command
python3 python/server.py
python3 python/prepare_feishu_raw.py --dry-run
python3 python/prepare_feishu_raw.py
python3 python/compress.py
python3 python/md_table_to_material_xlsx.py --dry-run
python3 python/md_table_to_material_xlsx.py
```

## 十二、系统一句话总结

YQS-Imagerepo 已形成从外部图片接收、素材预处理、AI 识图、结构化清单生成、Excel 追加、可视化管理到正式素材库沉淀的完整素材中台工作流，并为后续飞书与 DeerFlow 自动化编排预留了稳定接口。

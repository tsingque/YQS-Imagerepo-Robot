# YQS-Imagerepo 一线使用版：操作手册

## 你需要知道的三个文件夹

### 1. 外部图片先放这里

```text
feishu_trans_repo/
```

新图片、飞书下载图片、截图、临时素材，先放到这个文件夹。

不要直接放进正式素材库。

### 2. 待处理图片在这里

```text
image_compressor/images_raw/
```

这里是系统准备处理的图片。

### 3. 正式素材库在这里

```text
case_materials/
```

这里是已经确认可复用的正式素材。

不确定、没识别、没命名、版权没确认的图片不要直接放进去。

## 每天怎么用

### 第一步：打开页面

双击项目里的：

```text
start_dashboard.command
```

或在终端运行：

```bash
./start_dashboard.command
```

打开后访问：

```text
http://127.0.0.1:8765
```

## Dashboard 上能看什么

页面会显示：

- 当前图片总数
- 待加载图片数量
- `images_raw` 待处理图片数量
- 压缩输出图片数量
- 正式素材库成品图数量
- 图片预览
- 飞书通知配置状态

如果技术人员已经配置好飞书，页面可以点击 `发送测试通知`，确认飞书群能收到系统消息。

## 新图片处理流程

### 1. 把图片放到临时目录

把图片放进：

```text
feishu_trans_repo/
```

### 2. 在页面点击加载

在 Dashboard 点击：

```text
加载到 images_raw
```

系统会把图片移动到：

```text
image_compressor/images_raw/
```

### 3. 查看数量是否变化

页面里的 `images_raw` 数量会增加。

如果没有变化，检查：

- 图片是不是放错文件夹
- 图片格式是不是常见图片格式
- 文件夹里是不是空的

## 清空待处理图片

如果确认 `images_raw` 里的图片不需要了，可以在 Dashboard 点击：

```text
清空 images_raw
```

页面会弹出确认框。

注意：这个操作会删除 `image_compressor/images_raw/` 里的文件，不会删除正式素材库。

## 压缩图片

如果需要压缩图片，运行：

```bash
python3 python/compress.py
```

压缩后的图片会进入：

```text
image_compressor/images_compressed/
```

AI 识图默认使用这里的压缩后图片，不直接识别原始大图，这样可以降低模型 token 和调用成本。

压缩报告会生成在：

```text
image_compressor/compression_report.md
```

## 素材清单怎么更新

系统使用两份主要清单：

```text
案例素材清单_表格.md
案例素材清单.xlsx
```

`案例素材清单_表格.md` 是程序处理用的单表。

`案例素材清单.xlsx` 是给人查看、沟通和交付用的表。

如果 `案例素材清单_表格.md` 已经更新，需要同步到 Excel，运行：

```bash
python3 python/md_table_to_material_xlsx.py --dry-run
```

确认行数没问题后，再运行：

```bash
python3 python/md_table_to_material_xlsx.py
```

系统会：

- 生成一个带时间的 temp Excel
- 把数据追加到 `案例素材清单.xlsx`
- 把 temp 文件移动到 `md_trans_repo/`

## 什么图片可以进正式素材库

可以进入 `case_materials/` 的图片应该满足：

- 文件名有业务含义
- 图片清晰
- 知道属于哪个分类
- 知道能放在哪类 PPT 页面
- 来源和版权状态有记录
- 不需要再人工确认

不建议直接入库的情况：

- 文件名是 `image1.png`、`IMG_001.jpg`
- 图片模糊
- 截图文字看不清
- 不知道图片来源
- 不知道属于什么客户或项目
- 第三方素材版权没确认

## 文件命名规则

优先使用中文语义文件名。

示例：

```text
JOMEC_品牌标识.png
CAIP_概念_MPV_智能座舱内饰图.png
均胜_Joyspace+_智能座舱交互界面.png
智慧船舱实拍.png
```

不要使用：

```text
image1.png
IMG_8821.jpg
未命名.png
```

如果原始文件名没有中文，AI 识图时会建议新的中文文件名。

## 看到需人工确认怎么办

如果素材状态是：

```text
需人工确认
```

需要人工检查：

- 图片里的客户或品牌是否识别正确
- 是否允许用于方案或 PPT
- 是否需要更高清版本
- 是否需要重命名
- 是否应该进入正式素材库

## 常用命令

启动页面：

```bash
./start_dashboard.command
```

预览加载图片：

```bash
python3 python/prepare_feishu_raw.py --dry-run
```

正式加载图片：

```bash
python3 python/prepare_feishu_raw.py
```

压缩图片：

```bash
python3 python/compress.py
```

预览 Markdown 表格转 Excel：

```bash
python3 python/md_table_to_material_xlsx.py --dry-run
```

正式追加到 Excel：

```bash
python3 python/md_table_to_material_xlsx.py
```

## 一线使用原则

- 新图片先放 `feishu_trans_repo/`
- 不要直接改 `case_materials/`
- 不确定素材不要入库
- 追加 Excel 前先跑 `--dry-run`
- 文件名尽量中文、清楚、能看懂
- 第三方素材默认都需要确认授权

# Image Compressor — PPT 素材压缩工具

本地图片批量压缩，专为 PPT 素材优化：保持文字、图表、界面截图清晰，不模糊。

## 快速开始

```bash
# 1. 安装依赖（仅 Pillow）
pip3 install -r requirements.txt

# 2. 把待压缩图片放入 images_raw/

# 3. 回到项目根目录运行
python3 python/compress.py
```

## 输出

- `images_compressed/` — 压缩后的图片（原图不变）
- `compression_report.md` — 每张图的压缩报告

## 压缩策略

| 格式 | 质量 | 缩放 | 备注 |
|------|------|------|------|
| JPG/JPEG | 85 | 最长边 > 2560px 等比缩小 | subsampling 4:2:0 |
| WebP | 85 | 最长边 > 2560px 等比缩小 | method=6 |
| PNG | 优先无损 | 最长边 > 2560px 等比缩小 | > 500KB 时自动量化到 256 色（保留透明） |

- **JPG 85** 是 PPT 使用的最佳平衡点——视觉无差异，体积减少约 60%
- **2560px 上限** 覆盖 1920px 宽 PPT 背景 1.33× 超采样，Retina 屏够用不浪费
- **PNG 优先无损** 保证文字/图表/UI 像素级清晰

## 注意事项

- 不修改原图，输出到独立文件夹
- RGBA PNG 转 JPG 时透明部分填白底
- 不支持的格式自动跳过，不报错终止
- 每次运行会清空 `images_compressed/` 重新生成

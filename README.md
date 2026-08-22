# 🖊️ 表情包 PSD 批量署名替换工具

`design-asset-indexer`

[![CI](https://github.com/PicaChill/design-asset-indexer/actions/workflows/ci.yml/badge.svg)](https://github.com/PicaChill/design-asset-indexer/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-%3E%3D3.11-3776AB)
![License](https://img.shields.io/badge/License-MIT-green)

> **批量修改一个文件夹里 PSD 表情包的署名。**
>
> - ✅ **本地处理**：素材不会上传
> - ✅ **保护原文件**：默认只修改输出副本，不覆盖原 PSD
> - ✅ **可以先预演**：先看会改哪些文件，再正式执行
> - ⚠️ **需要**：Windows + 本机 Adobe Photoshop
> - ❌ **暂不支持**：栅格化署名、Smart Object 内文字、GIF 成品图署名

你可以自己照下面操作；如果你有能操作本机终端的 **Codex / ChatGPT / Claude**，也可以把使用指南里的提示词交给它，让 AI 帮你检查环境、安装和预演。

v0.2.0 只替换 PSD **可编辑文字图层**中与旧署名完全相同的文字。找不到唯一目标时会安全跳过，不做 OCR、模糊匹配或猜测。

## 🚀 从这里开始

### 🤖 方式 A：让 AI 助手帮你操作

如果你有能操作本机终端的 Codex / ChatGPT / Claude，推荐直接打开 [Windows 完整使用指南](docs/WINDOWS_PSD_SIGNATURE_GUIDE_CN.md#-让-ai-助手帮你操作)，复制里面的提示词。

> ⚠️ AI 也必须先做**预演**，未经你确认不要正式替换；不要把私人 PSD 上传给不受信任的在线服务。

### ⌨️ 方式 B：自己操作

1. 安装 Python 3.11+ 和 Adobe Photoshop。
2. 从 [v0.2.0 Release](https://github.com/PicaChill/design-asset-indexer/releases/tag/v0.2.0) 下载 wheel，并安装到独立虚拟环境。
3. 运行 `signature-inspect`，先确认 PSD 里的实际文字。
4. 运行 `signature-replace --dry-run`，只预演，不修改 PSD。
5. 确认 `planned_changes.csv` 后，去掉 `--dry-run` 正式执行。

👉 [查看 Windows 完整使用指南](docs/WINDOWS_PSD_SIGNATURE_GUIDE_CN.md)

## 🧪 最短示例

下面假设你已经按完整指南把 v0.2.0 安装在 `D:\design-asset-indexer-v020\venv`。先预演，不真正修改：

```powershell
& "D:\design-asset-indexer-v020\venv\Scripts\python.exe" -m design_asset_indexer signature-replace `
  "D:\表情包_原始" `
  --out "D:\表情包_已改署名" `
  --from "旧署名" `
  --to "新署名" `
  --dry-run
```

- `--from` = PSD 里当前的旧署名
- `--to` = 想换成的新署名

确认 `planned_changes.csv` 后，只去掉最后的 `--dry-run` 再执行。PSD 在子文件夹时，两步都加 `--recursive`。

> ⚠️ 默认每次最多处理 100 个 PSD。超过时 `summary.json` 的 `max_files_reached=true`；需要更多时显式添加 `--max-files 1000`。

## 🔒 会不会改坏原文件？

- ✅ 默认不覆盖原 PSD。
- ✅ 正式修改前先复制到独立输出目录，只修改输出副本。
- ✅ 预演不会生成修改后的 PSD，也不会调用保存。
- ✅ 多个相同候选时不猜，直接跳过。
- ✅ 已存在的输出 PSD 不覆盖、不删除。
- ✅ 修改或保存失败时，清理本轮新建的失败副本。
- ✅ 已通过真实 PSD 私有验收。
- ⚠️ 没有任何工具能承诺绝对安全，重要素材仍建议另外保留备份。

输入目录与输出目录必须分开，不能相同，也不能互相嵌套。报告可能包含相对文件名和文字内容，分享前请先检查。

## 📄 普通用户主要看这 3 个文件

| 文件 | 用途 |
|---|---|
| `signature_layers.csv` | 看 PSD 里有哪些文字、旧署名实际是什么 |
| `planned_changes.csv` | 预演后确认哪些会改、哪些会跳过 |
| `signature_replace_results.csv` | 正式执行后查看成功 / 跳过 / 失败 |

JSON、JSONL 和 `summary.json` 主要给程序或高级排错使用，第一次使用可以先忽略。

## ⚠️ 当前不支持

- ❌ 栅格化署名
- ❌ Smart Object / linked Smart Object 内文字
- ❌ GIF / PNG / JPG 成品图署名替换
- ❌ OCR、模糊匹配或自动猜测
- ❌ GUI、exe 或一键安装包
- ⚠️ 写入必须使用 Windows + Adobe Photoshop
- ⚠️ 只支持 PSD 可编辑文字图层

## 🧰 其他素材整理功能

除了署名替换，本项目还保留完整的本地素材整理能力：

- 📁 递归扫描素材
- 🔍 按文件特征识别格式
- 🧾 PSD / PSB 基础信息解析
- 🖼️ PSD 内嵌 JPEG 预览提取
- 📦 ZIP 只读目录索引
- ♻️ SHA-256 重复候选检测
- 📊 CSV / JSON / JSONL 结构化报告
- 🧩 Contact Sheet
- 🔎 dHash 相似度提示

这些扫描、预览、去重和索引功能不需要 Photoshop。

| 格式 | 当前支持 |
|---|---|
| PSD | ✅ 基础解析、JPEG 内嵌预览；Windows + Photoshop 下可检查/替换可编辑文字图层 |
| PSB | ✅ 文件识别与基础 header / resource 解析；不支持署名写入 |
| JPEG | ✅ 文件特征识别与图片尺寸读取 |
| PNG | ✅ 文件特征识别与图片尺寸读取 |
| GIF | ✅ 文件特征识别与图片尺寸读取；❌ 不替换署名或动画内容 |
| ZIP | ✅ 只读目录索引，不解压 |
| RAR | ❌ 暂不支持 |
| 其他文件 | ✅ 进入 inventory，并标记为 `OTHER` |

## 🧑‍💻 开发者 / 高级用法

源码开发才需要 Git、editable install、pytest 和 build：

```powershell
git clone https://github.com/PicaChill/design-asset-indexer.git
Set-Location "design-asset-indexer"
py -3.11 -m venv ".venv"
& ".\.venv\Scripts\python.exe" -m pip install -e ".[dev,photoshop]"
& ".\.venv\Scripts\python.exe" -m pytest
& ".\.venv\Scripts\python.exe" -m build
```

使用 `python -m design_asset_indexer <命令> --help` 查看全量参数。CSV 适合人工查看，JSON / JSONL 适合后续程序处理。

PSD / PSB parser 是最小实现，不渲染完整画面；内嵌预览只支持合法 JPEG thumbnail resource。ZIP 只读索引会拒绝 ZIP64 central-directory metadata、multi-disk ZIP 和异常大的目录数据。Photoshop 写入通过 Windows COM / pywin32 完成，但只访问命令明确选中的 PSD。

## English

Batch-replace exact attribution text in editable PSD text layers on Windows with Photoshop.

`design-asset-indexer` runs locally, writes only copied outputs, supports dry-run, and skips ambiguous matches. It also provides offline asset inventory, PSD/PSB metadata and preview extraction, read-only ZIP indexing, SHA-256 duplicate candidates, reports, contact sheets, and dHash hints.

Rasterized text, text inside Smart Objects, GIF/PNG/JPEG attribution replacement, and a GUI are not supported.

## License

本项目使用 MIT License，详见 [`LICENSE`](LICENSE)。Pillow 与 pywin32 是独立依赖，分别使用各自的许可证。

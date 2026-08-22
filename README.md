# design-asset-indexer：本地表情包 / PSD 素材整理与索引工具

[![CI](https://github.com/PicaChill/design-asset-indexer/actions/workflows/ci.yml/badge.svg)](https://github.com/PicaChill/design-asset-indexer/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-%3E%3D3.11-3776AB)
![License](https://img.shields.io/badge/License-MIT-green)

> 🧰 一个面向**表情包 / PSD 素材批处理前期整理**的本地离线工具。
>
> 最初是为了我自己的**表情包批量修改署名**工作流开发。稳定版 v0.1.0 已完成素材扫描、预览、去重和索引；开发中的 **v0.2.0（Unreleased）**新增 PSD 可编辑文字图层的保守替换流程。

> ⚠️ **PSD 署名替换需要 Windows + 本机 Adobe Photoshop，只修改输出副本。GIF 署名替换仍未实现。**

## 这个项目是做什么的？

`design-asset-indexer` 是一个命令行工具，用来整理本地的 PSD、PSB、GIF、PNG、JPEG 和 ZIP 等素材。它会递归扫描目录，识别文件格式，读取基础信息，并把结果写成 CSV、JSON 或 JSONL 报告。

它目前主要解决这些前期问题：

- 一批素材里到底有哪些文件？
- 哪些 PSD 带有可提取的内嵌预览？
- ZIP 里有哪些内容，能否只看目录而不解压？
- 哪些文件可能是完全相同的副本？
- 如何快速生成预览汇总图，方便人工检查？

扫描、预览、去重和索引等 v0.1 功能**不需要 Photoshop**，也不需要数据库或云端账号。只有 v0.2 的 PSD 文字图层检查与替换需要本机 Photoshop。

## 为什么做这个项目？

我手里有比较多的表情包 PSD、GIF 和图片素材，最终想做的是一套**表情包批量修改署名**工作流。

真正开始处理之前，先得知道素材有多少、格式是否正常、PSD 有没有预览、哪些文件重复，以及 ZIP 里装了什么。手动翻目录很慢，也容易漏掉文件，所以先做了这个本地索引工具。

v0.1.0 先解决素材整理和前处理。v0.2.0 开始加入第一条安全写回工作流：先检查可编辑文字图层，再 dry-run，最后只修改复制到独立输出目录的 PSD。

## 当前 v0.1.0 能做什么？

- 📁 **递归扫描素材**：遍历指定目录，输出稳定的相对路径清单。
- 🔍 **按文件特征识别格式**：识别 PSD、PSB、JPEG、PNG、GIF、ZIP 和其他文件，不只依赖扩展名。
- 🧾 **PSD / PSB 基础解析**：读取画布尺寸、通道数、位深、颜色模式等基础信息。
- 🖼️ **PSD 内嵌 JPEG 预览**：遇到合法的 JPEG thumbnail resource 时，可提取到指定输出目录。
- 📦 **ZIP 只读目录索引**：列出 ZIP 成员、大小、压缩后大小和 CRC，不解压、不执行其中内容。
- ♻️ **SHA-256 重复候选检测**：先按文件大小筛选，再用 SHA-256 找出字节完全相同的候选组。
- 📊 **结构化报告**：生成 CSV、JSON 和 JSONL，方便继续筛选或交给其他脚本处理。
- 🧩 **Contact Sheet**：把预览图片整理成一张联系表，便于快速浏览。
- 🔎 **dHash 相似度提示**：代码中提供 64-bit dHash 与 Hamming distance 辅助逻辑，用于相似候选提示。

## 🖊️ PSD 批量署名替换（v0.2.0 Unreleased）

v0.2.0 新增 Windows + Photoshop 模式，可批量修改 PSD 中明确匹配的可编辑文字图层署名。

- ✅ **原 PSD 默认不修改**：程序先复制，再只让 Photoshop 打开并保存输出副本。
- ✅ **支持 dry-run**：先查看 `WOULD_REPLACE` / 跳过 / 错误决策，不创建修改后的 PSD，也不调用保存。
- ✅ **只做完全匹配**：`textItem.contents` 必须与 `--from` 完全相同；可再用 `--layer-name` 限定图层名。
- ✅ **歧义时安全跳过**：零个匹配为 `SKIPPED_NO_MATCH`，多个匹配为 `SKIPPED_AMBIGUOUS`。
- ✅ **输出到独立目录**：保持相对目录结构；已存在的输出文件不会覆盖。
- ✅ **每个文件有结构化结果**：生成 CSV、JSONL 和汇总 JSON。
- ⚠️ **需要 Windows + Adobe Photoshop**，并安装可选的 `photoshop` 依赖。
- ⚠️ 当前只支持 PSD 中的**可编辑文字图层**。
- ❌ 暂不支持已经栅格化的署名。
- ❌ 暂不支持 Smart Object 内部署名。
- ❌ GIF 署名修改尚未实现。

## 当前还不能做什么？

- ❌ **不能替换 GIF 署名**。
- ❌ **不能修改栅格化、Smart Object 或 linked Smart Object 内的署名**。
- ❌ 不做 OCR、模糊匹配、正则匹配或自动猜测署名。
- ❌ **没有 GUI**，目前需要使用命令行。
- ❌ **不支持 RAR**。

> ⚠️ v0.2.0 只处理明确匹配的 PSD 可编辑文字图层，**不是通用署名识别工具**。

## 隐私与安全

- ✅ **完全本地运行**：程序没有网络客户端，不需要登录。
- ✅ **不会上传文件**：素材始终留在本机。
- ✅ **没有遥测**：不发送使用数据。
- ✅ **输入目录只读**：扫描不会删除、移动、重命名或改写输入文件。
- ✅ **输出位置明确**：报告和预览只写入 `--out` 指定的位置；输出目录位于输入目录内部时会被拒绝。
- ✅ **ZIP 不解压**：只读取目录信息，不执行归档内文件。
- ✅ **不跟随目录符号链接**：避免扫描意外越过所选目录边界。
- ✅ **源 PSD 不保存**：署名流程检查源文件时以不保存方式关闭，只允许修改输出副本。
- ✅ **输入/输出隔离**：相同目录、互相嵌套的目录都会被拒绝。
- ✅ **只访问明确选择的 PSD**：Photoshop 自动化不会扫描其他目录，也不会关闭用户原有文档。

⚠️ 报告会包含所选目录中的**相对文件名**。如果要把报告发给别人，请先检查内容。

> ⚠️ `signature-inspect` 报告会包含 PSD 文字图层的 `current_text`。**未经检查，不要公开分享这些报告。**

## 支持格式

| 格式 | 当前支持 |
|---|---|
| PSD | ✅ 基础解析与 JPEG 内嵌预览；v0.2 支持通过 Photoshop 检查/替换明确匹配的可编辑文字图层 |
| PSB | ✅ 文件识别与基础 header / resource 解析；不覆盖完整 PSB 功能 |
| JPEG | ✅ 文件特征识别与图片尺寸读取 |
| PNG | ✅ 文件特征识别与图片尺寸读取 |
| GIF | ✅ 文件特征识别与图片尺寸读取；不处理署名或动画内容 |
| ZIP | ✅ 只读目录索引；不解压 |
| RAR | ❌ v0.1.0 暂不支持 |
| 其他文件 | ✅ 会进入 inventory，并标记为 `OTHER` |

## 🚀 快速开始

需要 Python 3.11 或更高版本。

### 1. 获取代码并创建环境

```console
git clone https://github.com/PicaChill/design-asset-indexer.git
cd design-asset-indexer
python -m venv .venv

# Windows
.venv\Scripts\python -m pip install -e ".[dev]"

# Linux / macOS
.venv/bin/python -m pip install -e ".[dev]"
```

Windows 与 Linux/macOS 的安装命令二选一即可。

如果要在 Windows 使用 v0.2 PSD 署名功能，需要本机已安装 Adobe Photoshop，并安装可选依赖：

```console
.venv\Scripts\python -m pip install -e ".[dev,photoshop]"
```

### 2. 先用程序生成的测试素材试跑

```console
python tests/generate_fixtures.py
design-asset-index scan tests/fixtures/synthetic --out scan-output
```

测试素材只包含程序生成的几何图形、色块和测试文字。

### 3. 扫描自己的素材目录

```console
design-asset-index scan ./my-assets --out ./scan-output
```

### 4. 生成 Contact Sheet

如果扫描结果中提取到了 PSD 内嵌预览，可以执行：

```console
design-asset-index contact-sheet ./scan-output/previews --out ./scan-output/contact-sheet.jpg
```

### 5. 检查并替换 PSD 可编辑署名

先检查可能的目标文字图层：

```console
design-asset-index signature-inspect D:\input-psd --out D:\signature-inspect --recursive --layer-name "署名"
```

再执行 dry-run，不生成修改后的 PSD：

```console
design-asset-index signature-replace D:\input-psd --out D:\output-psd --from "旧署名" --to "新署名" --layer-name "署名" --recursive --dry-run
```

检查 `planned_changes.csv` 后，去掉 `--dry-run` 才会把源 PSD 复制到输出目录，并只修改副本：

```console
design-asset-index signature-replace D:\input-psd --out D:\output-psd --from "旧署名" --to "新署名" --layer-name "署名" --recursive
```

> ⚠️ 输出目录必须与输入目录完全分离。已有的输出 PSD 会标记为 `SKIPPED_EXISTS`，不会覆盖。

### 开发与测试

```console
python tests/generate_fixtures.py
python -m pytest
python -m build
```

Binary fixtures 由脚本动态生成，不会提交到 Git。

## 输出文件

| 文件 | 内容 |
|---|---|
| `inventory.csv` | 素材清单，适合用表格软件查看 |
| `inventory.jsonl` | 与 inventory 对应的逐行 JSON 记录 |
| `archives.jsonl` | ZIP 目录索引结果 |
| `duplicates.json` | SHA-256 完全相同的重复候选组 |
| `previews.jsonl` | PSD 来源文件与安全预览文件名的映射 |
| `summary.json` | 当前命令的数量、状态与非致命错误汇总 |
| `previews/` | 从 PSD 中提取的合法 JPEG 内嵌预览 |
| Contact Sheet | 运行 `contact-sheet` 命令后生成的预览汇总图 |
| `signature_layers.csv` / `.jsonl` | `signature-inspect` 找到的文字图层与匹配结果，可能包含 PSD 文字内容 |
| `planned_changes.csv` / `.jsonl` | dry-run 的逐文件计划与跳过原因 |
| `signature_replace_results.csv` / `.jsonl` | 正式替换的逐文件成功、跳过与失败结果 |

## ⚠️ 当前限制

- PSD / PSB parser 是最小实现，**不会渲染完整画面、解析图层内容或修改文件**。
- 内嵌预览目前只支持合法的 JPEG thumbnail resource。
- v0.1.0 会拒绝 ZIP64 central-directory metadata 和 multi-disk ZIP。
- 很大或损坏的 PSD resource section、异常 ZIP entry list 会被安全限制拒绝。
- dHash 只是低分辨率的相似度提示，**不能证明两个文件重复**。
- Contact Sheet 需要目录中已有可读取的预览图片。
- PSD 文字替换需要 Windows、Adobe Photoshop 和可选 `pywin32` 依赖。
- PSD 文字替换只支持可编辑 text layer，不处理栅格化内容或 Smart Object 内部文字。
- 完全相同的候选超过一个时会安全跳过，不会自动猜测。
- v0.2.0 仍是 Unreleased 开发版本，尚未创建 `v0.2.0` tag 或 Release。
- 当前只有 CLI，没有 GUI 或一键安装包。

## 🛠️ 后续计划

- ✅ PSD 可编辑文字图层的完全匹配、dry-run 与输出副本工作流（v0.2.0 Unreleased）。
- 🚧 更完整的署名识别与人工确认流程。
- 🚧 GIF 署名与动画处理。
- 🚧 GUI / 一键使用方式。

这些是后续方向，不代表已经承诺具体版本或发布时间。

## English

`design-asset-indexer` is a privacy-first, offline CLI for organizing local PSD, PSB, GIF, JPEG, PNG and ZIP asset collections. It started as preprocessing work for a personal batch-attribution workflow involving meme PSD/GIF assets.

Version 0.1.0 provides recursive inventory, signature-based format detection, basic PSD/PSB metadata parsing, embedded PSD JPEG preview extraction, read-only ZIP indexing, SHA-256 duplicate candidates, CSV/JSON/JSONL reports, contact sheets, and advisory dHash helpers.

Version 0.2.0 (Unreleased) adds optional Windows/Photoshop automation for inspecting editable PSD text layers and replacing one exact match in a copied output PSD. It supports dry-run, skips ambiguous matches, never overwrites existing outputs, and does not save source PSDs. Rasterized signatures, Smart Object editing, GIF replacement, and a GUI are not supported.

Files stay local; the tool has no uploads or telemetry. Inspection reports may contain PSD text contents and should be reviewed before sharing.

## License

本项目使用 MIT License，详见 [`LICENSE`](LICENSE)。

Pillow 是独立的运行时依赖，使用其自己的 `MIT-CMU` license expression。

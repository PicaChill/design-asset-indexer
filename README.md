# design-asset-indexer：本地表情包 / PSD 素材整理与索引工具

[![CI](https://github.com/PicaChill/design-asset-indexer/actions/workflows/ci.yml/badge.svg)](https://github.com/PicaChill/design-asset-indexer/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-%3E%3D3.11-3776AB)
![License](https://img.shields.io/badge/License-MIT-green)

> 🧰 一个面向**表情包 / PSD 素材批处理前期整理**的本地离线工具。
>
> 最初是为了我自己的**表情包批量修改署名**工作流开发。当前 v0.1.0 先把素材扫描、预览、去重和索引做好。

> ⚠️ **当前 v0.1.0 还不能直接批量修改 PSD / GIF 署名。** 署名识别与替换仍在后续计划中。

## 这个项目是做什么的？

`design-asset-indexer` 是一个命令行工具，用来整理本地的 PSD、PSB、GIF、PNG、JPEG 和 ZIP 等素材。它会递归扫描目录，识别文件格式，读取基础信息，并把结果写成 CSV、JSON 或 JSONL 报告。

它目前主要解决这些前期问题：

- 一批素材里到底有哪些文件？
- 哪些 PSD 带有可提取的内嵌预览？
- ZIP 里有哪些内容，能否只看目录而不解压？
- 哪些文件可能是完全相同的副本？
- 如何快速生成预览汇总图，方便人工检查？

整个过程**不需要 Photoshop**，也不需要数据库或云端账号。

## 为什么做这个项目？

我手里有比较多的表情包 PSD、GIF 和图片素材，最终想做的是一套**表情包批量修改署名**工作流。

真正开始处理之前，先得知道素材有多少、格式是否正常、PSD 有没有预览、哪些文件重复，以及 ZIP 里装了什么。手动翻目录很慢，也容易漏掉文件，所以先做了这个本地索引工具。

当前 v0.1.0 先解决素材整理和前处理。批量署名识别、替换与写回还没有实现，会放在后续版本继续做。

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

## 当前还不能做什么？

- ❌ **不能直接修改 PSD 署名**。
- ❌ **不能替换 GIF 署名**。
- ❌ **不能批量识别、编辑或写回署名**。
- ❌ **没有 GUI**，目前需要使用命令行。
- ❌ **不支持 RAR**。

> ⚠️ README 中提到的批量署名处理是项目来源和后续方向，**不是 v0.1.0 已经提供的功能**。

## 隐私与安全

- ✅ **完全本地运行**：程序没有网络客户端，不需要登录。
- ✅ **不会上传文件**：素材始终留在本机。
- ✅ **没有遥测**：不发送使用数据。
- ✅ **输入目录只读**：扫描不会删除、移动、重命名或改写输入文件。
- ✅ **输出位置明确**：报告和预览只写入 `--out` 指定的位置；输出目录位于输入目录内部时会被拒绝。
- ✅ **ZIP 不解压**：只读取目录信息，不执行归档内文件。
- ✅ **不跟随目录符号链接**：避免扫描意外越过所选目录边界。

⚠️ 报告会包含所选目录中的**相对文件名**。如果要把报告发给别人，请先检查内容。

## 支持格式

| 格式 | 当前支持 |
|---|---|
| PSD | ✅ 基础 header / image-resource 解析；可提取合法的内嵌 JPEG 预览 |
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
| `summary.json` | 文件数量、格式统计和非致命错误汇总 |
| `previews/` | 从 PSD 中提取的合法 JPEG 内嵌预览 |
| Contact Sheet | 运行 `contact-sheet` 命令后生成的预览汇总图 |

## ⚠️ 当前限制

- PSD / PSB parser 是最小实现，**不会渲染完整画面、解析图层内容或修改文件**。
- 内嵌预览目前只支持合法的 JPEG thumbnail resource。
- v0.1.0 会拒绝 ZIP64 central-directory metadata 和 multi-disk ZIP。
- 很大或损坏的 PSD resource section、异常 ZIP entry list 会被安全限制拒绝。
- dHash 只是低分辨率的相似度提示，**不能证明两个文件重复**。
- Contact Sheet 需要目录中已有可读取的预览图片。
- 当前只有 CLI，没有 GUI 或一键安装包。

## 🛠️ 后续计划

- 🚧 批量识别和替换署名。
- 🚧 PSD 批处理与安全写回。
- 🚧 GIF 署名与动画处理。
- 🚧 GUI / 一键使用方式。

这些是后续方向，不代表已经承诺具体版本或发布时间。

## English

`design-asset-indexer` is a privacy-first, offline CLI for organizing local PSD, PSB, GIF, JPEG, PNG and ZIP asset collections. It started as preprocessing work for a personal batch-attribution workflow involving meme PSD/GIF assets.

Version 0.1.0 provides recursive inventory, signature-based format detection, basic PSD/PSB metadata parsing, embedded PSD JPEG preview extraction, read-only ZIP indexing, SHA-256 duplicate candidates, CSV/JSON/JSONL reports, contact sheets, and advisory dHash helpers.

It does **not** edit PSD/GIF attribution text, perform batch attribution replacement, or provide a GUI yet. Files stay local; the tool has no uploads or telemetry, and treats the input tree as read-only.

## License

本项目使用 MIT License，详见 [`LICENSE`](LICENSE)。

Pillow 是独立的运行时依赖，使用其自己的 `MIT-CMU` license expression。

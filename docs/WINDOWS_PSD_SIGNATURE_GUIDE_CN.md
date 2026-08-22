# 🪟 Windows：PSD 表情包批量署名替换完整指南

本指南面向第一次使用命令行的 Windows 用户。目标是：**先检查、再预演、最后在你确认后只修改输出副本**。

当前正式版本是 **v0.2.0**。它只支持 PSD 中明确匹配的**可编辑文字图层**，写入时需要本机 Adobe Photoshop。

## 目录

- [✅ 开始前确认](#-开始前确认)
- [🤖 让 AI 助手帮你操作](#-让-ai-助手帮你操作)
- [📦 安装](#-安装)
- [📁 准备输入和输出文件夹](#-准备输入和输出文件夹)
- [🔒 原文件保护](#-原文件保护)
- [🔍 第一步：检查 PSD 里的文字](#-第一步检查-psd-里的文字)
- [🧪 第二步：先预演，不真正修改](#-第二步先预演不真正修改)
- [✅ 第三步：正式批量修改](#-第三步正式批量修改)
- [📄 怎么看结果](#-怎么看结果)
- [❓ 常见问题](#-常见问题)
- [🧰 高级参数](#-高级参数)
- [🐛 出问题怎么反馈](#-出问题怎么反馈)

## ✅ 开始前确认

请先确认：

- ✅ Windows 可以正常使用。
- ✅ 已安装 Python 3.11 或更新版本；当前项目 CI 覆盖 Python 3.11、3.12、3.13。
- ✅ Adobe Photoshop 已安装，并且可以手动启动和打开 PSD。
- ✅ 准备了与原素材分开的检查目录和输出目录。
- ✅ 重要素材另有备份。

> ⚠️ v0.2.0 没有 GUI、exe 或一键安装器，需要复制 PowerShell 命令。不会用时可以让能操作本机终端的 AI 助手协助。

## 🤖 让 AI 助手帮你操作

把下面整段复制给**能操作你本机终端和文件**的 AI 助手，再填写最后四项：

```text
我想在这台 Windows 电脑上使用下面这个开源项目，
批量修改一个文件夹里 PSD 表情包的署名：

https://github.com/PicaChill/design-asset-indexer

当前正式版本是 v0.2.0。

请先检查：
1. Windows 是否正常
2. Python 3.11 或更新版本是否已安装
3. Adobe Photoshop 是否已安装并能正常启动

然后帮助我完成安装和使用，但必须遵守：

1. 使用独立 Python 虚拟环境，不修改我的全局 Python 环境
2. 不覆盖任何原始 PSD
3. 输入目录和输出目录必须分开
4. 先运行 signature-inspect
5. 再运行 signature-replace --dry-run，只预演不真正修改
6. 把 planned_changes.csv 的结果用中文解释给我
7. 未经我明确确认，不得执行正式 signature-replace
8. 如果同一个 PSD 有多个相同文字，不要猜，先告诉我
9. 如果发现我的署名是栅格化或 Smart Object 内文字，告诉我当前版本不支持，不要自行尝试破坏性修改

我的输入文件夹：
<填写路径>

我的输出文件夹：
<填写路径>

旧署名：
<填写>

新署名：
<填写>
```

> ⚠️ 这段提示词适合**能操作你本机终端/文件的 AI 助手**。
>
> 普通网页聊天机器人如果无法访问你的电脑，只能指导你，不能直接执行。
>
> 不要为了省步骤把私人 PSD 上传到不受信任的在线服务。

## 📦 安装

下面使用 **Release wheel + 独立虚拟环境**。这条路线不需要 Git，不需要下载源码，不安装 pytest/build，也不会修改全局 Python 环境。

### 1. 下载 v0.2.0 wheel

打开 [v0.2.0 Release](https://github.com/PicaChill/design-asset-indexer/releases/tag/v0.2.0)，下载：

```text
design_asset_indexer-0.2.0-py3-none-any.whl
```

下面假设它保存在：

```text
D:\Downloads\design_asset_indexer-0.2.0-py3-none-any.whl
```

如果你的实际下载位置不同，请替换命令里的 wheel 路径。

### 2. 创建独立虚拟环境

打开 PowerShell，执行：

```powershell
New-Item -ItemType Directory -Path "D:\design-asset-indexer-v020" -Force
py -3.11 -m venv "D:\design-asset-indexer-v020\venv"
```

如果你安装的是 Python 3.12 或 3.13，把 `-3.11` 改成 `-3.12` 或 `-3.13`。

### 3. 安装 wheel 和 Photoshop 依赖

```powershell
& "D:\design-asset-indexer-v020\venv\Scripts\python.exe" -m pip install "D:\Downloads\design_asset_indexer-0.2.0-py3-none-any.whl"
& "D:\design-asset-indexer-v020\venv\Scripts\python.exe" -m pip install "pywin32>=306"
```

这里故意分成两条命令，避免依赖本地 wheel 的 extras 语法。后续所有命令都显式使用 venv 内的 Python，**不需要激活虚拟环境**。

### 4. 验证安装

```powershell
& "D:\design-asset-indexer-v020\venv\Scripts\python.exe" -m design_asset_indexer --help
& "D:\design-asset-indexer-v020\venv\Scripts\python.exe" -m design_asset_indexer signature-inspect --help
& "D:\design-asset-indexer-v020\venv\Scripts\python.exe" -m design_asset_indexer signature-replace --help
```

三条命令都显示帮助内容，就可以继续。

## 📁 准备输入和输出文件夹

推荐使用三个同级目录：

| 目录 | 用途 |
|---|---|
| `D:\表情包_原始` | 放原始 PSD，只作为输入 |
| `D:\表情包_检查` | 保存文字图层检查报告 |
| `D:\表情包_已改署名` | 保存预演报告和正式修改后的输出副本 |

可以先创建后两个目录：

```powershell
New-Item -ItemType Directory -Path "D:\表情包_检查" -Force
New-Item -ItemType Directory -Path "D:\表情包_已改署名" -Force
```

必须同时满足：

- **输入与输出不能相同**。
- **输出不能在输入里面**。
- **输入也不能在输出里面**。

不要使用 `D:\表情包\原始` 和 `D:\表情包\原始\output` 这种嵌套结构。

## 🔒 原文件保护

- ✅ `signature-inspect` 打开源 PSD 后不保存。
- ✅ `--dry-run` 只生成计划报告，不生成修改后的 PSD，也不调用保存。
- ✅ 正式执行先复制 PSD，再只修改输出副本。
- ✅ 多个完全相同候选时跳过，不猜目标。
- ✅ 已存在的输出 PSD 不覆盖、不删除。
- ✅ 修改或保存失败时清理本轮新建的失败副本。
- ✅ 已通过真实 PSD 私有验收。
- ⚠️ 重要素材仍建议另外留备份；不要把“保护机制”理解为绝对不会发生任何意外。

报告会包含相对文件名、旧文字和新文字。公开分享前请先脱敏。

## 🔍 第一步：检查 PSD 里的文字

先不加图层名过滤，查看输入目录第一层里的 PSD：

```powershell
& "D:\design-asset-indexer-v020\venv\Scripts\python.exe" -m design_asset_indexer signature-inspect `
  "D:\表情包_原始" `
  --out "D:\表情包_检查"
```

如果 PSD 还放在子文件夹中，加 `--recursive`：

```powershell
& "D:\design-asset-indexer-v020\venv\Scripts\python.exe" -m design_asset_indexer signature-inspect `
  "D:\表情包_原始" `
  --out "D:\表情包_检查" `
  --recursive
```

如果文字很多，可以加可选过滤条件：

```powershell
--contains-text "旧署名的一部分"
```

`--contains-text` 只用来帮助检查报告标记可能相关的文字，不会把正式替换变成模糊匹配。正式替换仍要求 `--from` 与完整文字完全相同。

打开 `D:\表情包_检查\signature_layers.csv`，主要看：

| 列 | 用途 |
|---|---|
| `relative_path` | PSD 在输入目录中的相对位置 |
| `layer_name` | Photoshop 图层名称 |
| `current_text` | 文字图层里的实际完整文字 |
| `matched` | 是否符合本次可选检查过滤条件 |

确定目标旧署名后，把 `current_text` 的完整内容用于下一步 `--from`。

## 🧪 第二步：先预演，不真正修改

> **`--dry-run` = 只告诉你“如果正式执行会发生什么”，不会生成修改后的 PSD，也不会调用保存。**

```powershell
& "D:\design-asset-indexer-v020\venv\Scripts\python.exe" -m design_asset_indexer signature-replace `
  "D:\表情包_原始" `
  --out "D:\表情包_已改署名" `
  --from "旧署名" `
  --to "新署名" `
  --dry-run
```

PSD 在子文件夹时加 `--recursive`。然后打开：

```text
D:\表情包_已改署名\planned_changes.csv
```

`decision` 的真实值和白话含义：

| decision | 白话 |
|---|---|
| `WOULD_REPLACE` | ✅ 正式执行时会修改 |
| `SKIP_NO_MATCH` | ⚠️ 没找到完全相同的旧署名 |
| `SKIP_AMBIGUOUS` | ⚠️ 找到多个候选，为安全起见跳过 |
| `SKIP_EXISTS` | ⚠️ 输出目录已有同名 PSD，不覆盖 |
| `ERROR` | ❌ 打开、Photoshop 或文件处理失败 |

只有你确认 `WOULD_REPLACE` 的文件符合预期，才进入下一步。

## ✅ 第三步：正式批量修改

确认 `planned_changes.csv` 后，使用相同参数，**只去掉 `--dry-run`**：

```powershell
& "D:\design-asset-indexer-v020\venv\Scripts\python.exe" -m design_asset_indexer signature-replace `
  "D:\表情包_原始" `
  --out "D:\表情包_已改署名" `
  --from "旧署名" `
  --to "新署名"
```

如果预演时用了 `--recursive`、`--layer-name`、`--include` 或 `--max-files`，正式执行时也要保持相同参数。

- 修改后的 PSD：在 `D:\表情包_已改署名`，并保持原来的相对子目录结构。
- 原始 PSD：仍在 `D:\表情包_原始`，程序不会保存覆盖它们。
- 正式结果：查看 `D:\表情包_已改署名\signature_replace_results.csv`。

正式 `status` 常见值：

| status | 含义 |
|---|---|
| `REPLACED` | ✅ 已替换唯一匹配并保存输出副本 |
| `SKIPPED_NO_MATCH` | ⚠️ 没有完全匹配 |
| `SKIPPED_AMBIGUOUS` | ⚠️ 有多个候选，安全跳过 |
| `SKIPPED_EXISTS` | ⚠️ 输出 PSD 已存在，未覆盖 |
| `FAILED_OPEN` / `FAILED_REPLACE` / `FAILED_SAVE` | ❌ 打开、替换或保存失败 |

## 📄 怎么看结果

普通用户主要看三个 CSV：

| 文件 | 何时产生 | 主要看什么 |
|---|---|---|
| `signature_layers.csv` | 检查阶段 | `current_text`、`layer_name`、`matched` |
| `planned_changes.csv` | dry-run | `decision`、`matched_layer_count`、`error_code` |
| `signature_replace_results.csv` | 正式执行 | `status`、`changed_layer_count`、`error_code` |

JSON / JSONL 和 `summary.json` 主要给程序或高级排错使用。`summary.json` 中：

- `max_files_reached=true`：候选超过本次安全上限，仍有文件未处理。
- `changed_layer_count`：本次实际修改的图层总数。
- `status_counts`：各结果状态的数量。

> ⚠️ CSV / JSON / JSONL 可能包含私人文件名和署名文字，不要未经检查直接公开上传。

## ❓ 常见问题

### 为什么只处理了 100 个？

`signature-inspect` 和 `signature-replace` 默认 `--max-files 100`。超过时 `summary.json` 会写入 `max_files_reached=true`。

明确需要更多时，在检查、预演和正式执行中都加相同上限，例如：

```powershell
--max-files 1000
```

### PSD 在子文件夹里怎么办？

在检查、预演和正式执行命令中都加：

```powershell
--recursive
```

### `SKIP_AMBIGUOUS` 怎么办？

1. 打开 `signature_layers.csv`。
2. 找到真正目标的 `layer_name`。
3. 重新预演时添加精确图层名：

```powershell
--layer-name "图层名"
```

仍然有多个匹配时不要猜，先在 Photoshop 中人工确认。

### 找不到旧署名怎么办？

检查：

- 是否多了空格或换行；
- 全角 / 半角字符是否一致；
- `current_text` 是否与 `--from` 完全相同；
- 检查阶段是否可用 `--contains-text "旧署名的一部分"` 帮助定位；
- 署名是否已经栅格化；
- 文字是否在 Smart Object 内。

后两种情况当前版本不支持，不要尝试破坏性绕过。

### `py` 或 `python` 找不到怎么办？

重新安装 Python 3.11、3.12 或 3.13，并在安装器中启用 Python Launcher。关闭并重新打开 PowerShell 后运行：

```powershell
py -0p
```

如果仍失败，把完整错误交给可信的本机 AI 助手或熟悉 Windows 的人排查，不要随意修改系统目录。

### 出现 `Photoshop automation unavailable` 怎么办？

确认：

- 当前系统是 Windows；
- Photoshop 能手动启动并打开 PSD；
- 使用的是本指南创建的 venv；
- venv 已安装 `pywin32`；
- 关闭并重新打开 PowerShell 后重试。

可用下面命令确认依赖：

```powershell
& "D:\design-asset-indexer-v020\venv\Scripts\python.exe" -m pip show pywin32
```

### 中文路径和中文文字可以用吗？

项目测试覆盖中文路径 / 文字，并完成过真实 PSD 私有验收；但不同 Photoshop 版本、字体和复杂 PSD 仍可能有差异。所有路径都用双引号，先 inspect、再 dry-run，不要跳过预演。

### 输出目录已经有同名 PSD 怎么办？

程序会返回 `SKIP_EXISTS`（预演）或 `SKIPPED_EXISTS`（正式执行），不会覆盖或删除原有输出。请换一个空的输出目录，或先由你人工确认并整理旧输出。

## 🧰 高级参数

| 参数 | 作用 |
|---|---|
| `--recursive` | 递归处理子目录 |
| `--contains-text "片段"` | 仅在 inspect 阶段标记包含该片段的文字图层 |
| `--layer-name "图层名"` | 正式匹配时再增加精确图层名条件 |
| `--include "*.psd"` | 按相对路径 glob 选择 PSD，默认 `*.psd` |
| `--max-files 1000` | 显式提高本次文件安全上限 |

查看当前版本的完整参数：

```powershell
& "D:\design-asset-indexer-v020\venv\Scripts\python.exe" -m design_asset_indexer signature-inspect --help
& "D:\design-asset-indexer-v020\venv\Scripts\python.exe" -m design_asset_indexer signature-replace --help
```

## 🐛 出问题怎么反馈

前往 [GitHub Issues](https://github.com/PicaChill/design-asset-indexer/issues) 新建 Issue。可以提供：

- Windows 版本
- Python 版本
- Photoshop 版本
- 项目版本（例如 v0.2.0）
- 执行的命令，但先隐去私人路径和署名
- `summary.json` 中不敏感的计数与状态字段
- `error_code` / `error_message`

请**不要公开**：

- 真实 PSD
- 私人文件名或绝对路径
- 真实署名文字
- `signature_layers.csv` 全文件
- `planned_changes.csv` 全文件

如需提供最小复现，优先使用自己新建的合成 PSD 和虚构文字。

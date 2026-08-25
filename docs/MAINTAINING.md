# Maintainer workflow

`design-asset-indexer` 是一个活跃维护的开源项目。本文件记录公开的维护责任与发布边界，方便贡献者和用户理解项目如何处理 issue、PR、安全与版本发布。

## Issue triage

维护者会将新问题优先归入以下类别：

- correctness / data-safety；
- Photoshop / Windows compatibility；
- GUI / usability；
- packaging / release；
- security / privacy；
- feature request / unsupported format。

能够影响源 PSD、输出路径、计划一致性或隐私边界的问题优先级最高。

## Pull request review

PR 评审重点：

1. 是否保持原 PSD 不被覆盖；
2. dry-run / plan 与 execute 是否仍严格绑定；
3. 是否存在路径逃逸、隐私泄露或不必要网络访问；
4. Photoshop COM 是否仍在明确线程生命周期内；
5. 行为变化是否有回归测试；
6. Windows portable 变化是否影响依赖、许可证或最终 bundle。

项目默认使用小范围 PR，并在合并前要求 CI 通过。

## Release management

正式版本遵循：

1. 版本与 changelog 同步；
2. 全量测试与 GUI 测试通过；
3. Windows portable 从最终 release commit 构建；
4. 对 portable 做独立启动、Photoshop、路径和 DPI 验收；
5. 生成并核对 SHA-256；
6. tag 指向与 provenance 中的 source commit 一致；
7. GitHub Release 只上传经过验收的最终 artifacts。

v0.3.0 已提供 Windows x64 portable ZIP、wheel、sdist 与 `SHA256SUMS.txt`。

## Security and privacy

安全问题请先阅读 [`SECURITY.md`](../SECURITY.md)。

项目不需要上传用户 PSD；公开 issue / PR / 日志中不应包含私人 PSD、真实署名、绝对私人路径、凭据或其他敏感信息。

## Supported maintenance scope

当前重点维护：

- editable PSD text-layer inspection / replacement；
- Premium Simple Windows GUI；
- Windows + Photoshop COM compatibility；
- source-preserving output-copy workflow；
- offline indexing / preview / duplicate-candidate reports；
- Windows portable packaging 与第三方许可证记录。

公开路线图见 [`ROADMAP.md`](../ROADMAP.md)。

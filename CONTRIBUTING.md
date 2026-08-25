# Contributing

感谢你关注 `design-asset-indexer`。

这个项目优先保证：**不覆盖原 PSD、行为可预演、失败时安全停止、隐私数据不进入公开仓库**。提交 issue 或 PR 时，请尽量围绕这些边界提供最小、可复现的信息。

## 报告 Bug

请优先使用 GitHub Issue，并提供：

- Windows / Python / Photoshop 版本（如适用）；
- 项目版本或 commit SHA；
- 可复现步骤；
- 实际结果与预期结果；
- 脱敏后的错误码、日志或截图。

请不要上传私人 PSD、真实署名、账号信息、绝对私人路径或其他敏感素材。若问题只能用私人素材复现，请先用匿名/合成样本描述结构。

## 提交 PR

1. 从最新 `main` 创建分支。
2. 保持改动范围小而明确。
3. 对行为变化补充测试。
4. 运行：

```powershell
python -m pytest
python -m build
```

涉及 GUI 时，再运行 GUI 测试；涉及 Windows portable 时，遵循 `packaging/windows/README.md`。

## 安全边界

以下改动需要特别谨慎：

- 源 PSD 写入语义；
- dry-run / plan 与正式执行参数绑定；
- 输出目录包含关系与路径逃逸；
- Photoshop COM 生命周期；
- 打包后的第三方组件与许可证；
- 报告中可能泄露的路径、文件名或文字内容。

如果一个改动会削弱“只修改输出副本”或“确认过的计划才执行”的约束，请在 PR 中明确说明原因与替代保护措施。

## 代码风格

保持现有 Python 风格与类型注解；优先清晰、可审计的实现，不为了抽象而抽象。

## 维护者工作流

项目的 issue triage、release、security 与 Windows portable 维护约定见 [`docs/MAINTAINING.md`](docs/MAINTAINING.md)。未来方向见 [`ROADMAP.md`](ROADMAP.md)。

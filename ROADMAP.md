# Roadmap

本路线图用于说明 `design-asset-indexer` 的维护方向，不承诺固定发布日期。

## Near term

### v0.3.x — stability and maintainer ergonomics

- 明确规范化/拒绝 GUI 中的相对输入与输出路径，避免行为依赖进程 working directory；
- 继续扩大 Windows / Photoshop 版本兼容性验证；
- 改进 portable 构建与 release 自动化的可审计性；
- 根据真实 issue 优化错误提示与诊断信息，同时避免泄露私人路径或文字内容；
- 保持 Premium Simple 为默认公共 GUI，不牺牲 frozen-plan 和 source-preserving 安全边界。

## Medium term

- 更好的批量处理可观测性与可恢复性；
- 更清晰的结构化报告和 maintainer-facing diagnostics；
- 对 PSD/PSB 只读解析能力做渐进增强；
- 在不上传用户素材的前提下扩展自动化测试夹具与兼容性矩阵。

## Explicit non-goals for now

- OCR / 模糊猜测署名；
- 自动编辑 Smart Object 内部内容；
- 覆盖源 PSD；
- 未经确认自动执行计划；
- 把私人素材上传到云端；
- 为了“更智能”而削弱 fail-closed 行为。

## How priorities are chosen

优先级主要由以下信号决定：

1. 数据安全与隐私风险；
2. 用户能否稳定完成真实工作流；
3. 可复现的兼容性问题；
4. issue / PR 中反复出现的维护负担；
5. 对开源贡献者是否容易验证和评审。

欢迎通过 issue 提供可复现问题和具体使用场景。

# 更新说明

[English](CHANGELOG.md)

## 2026-07-14

### 更可靠的论文归档

- 新增可选的 PDF 自动归档：识别标题、规范化文件名、分入唯一分类，并保留同名副本。
- 工作区现在有可编辑的 `references/organization_rules.json`；新工作区会获得通用的初始分类。
- 新增 `requires_any` 与 `requires_all` 规则门槛，使专题分类可要求明确的领域信号后才生效。
- 文件移动后，搜索索引、source registry、BibTeX `Source` 注释和本地笔记链接会同步更新。
- 拒绝不安全的分类路径；无法确定的论文保留在兜底分类。

### 更稳健的本地 PDF 处理

- 将常见 ACL/会议页眉识别为非标题，并支持多行标题拼接。
- 复制来的完整标题会优先精确匹配；同时抑制无害的损坏 PDF 警告。
- 笔记截图可使用 Ghostscript、PyMuPDF 或 Poppler `pdftoppm` 渲染。

### 文档与验证

- 将使用说明改写为“阅读器复制标题 -> Codex 交互”的日常流程。
- 补充归档、source 路径迁移、不安全规则、标题识别和截图回退的测试覆盖。

# Codex 论文阅读工作流 Skill

[English](README.md) | [更新说明](CHANGELOG.zh-CN.md)

这是一个配合 PDF 阅读器使用的 Codex skill。你继续在 Zotero、Office、Preview 或浏览器中阅读 PDF；Codex 负责从复制的标题定位本地文件、陪你解读论文、管理相关 source，并把讨论沉淀成简洁的 HTML 笔记。

本仓库使用 Codex 开发并维护。

## 你只需要做什么

1. 安装一次 skill。
2. 选择一个本地文件夹作为论文工作区。
3. 把下载好的 PDF 放进去，不需要改名。
4. 从阅读器复制论文标题，直接和 Codex 讨论。

你不需要手动建目录、重命名编号 PDF、建立索引或维护 source registry。

## Quickstart

安装：

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/hwang847/codex-paper-reader.git ~/.codex/skills/literature-workflow
```

重启 Codex App，或开启新的 Codex CLI 会话。打开你想作为论文库的文件夹，或者在终端 `cd` 到这个文件夹，然后对 Codex 说：

```text
使用 $literature-workflow，帮我配置这个论文阅读工作区。
```

Codex 会创建工作区、检查本地 PDF 能力，并根据你的偏好写出精简的本地 `AGENTS.md`。如果希望新文献自动归档，在配置时直接告诉它。

## 带我读一篇论文

工作区配置后，日常流程只有三步：

1. 把新 PDF 放在工作区根目录。`2508.05002v1.pdf`、`2025.findings-naacl.245.pdf`、`download.pdf` 都可以。
2. 用你平常的阅读器打开它，复制论文标题。
3. 对 Codex 说：

```text
使用 $literature-workflow，带我读这篇文献：
APEX-SQL: Talking to the data via Agentic Exploration for Text-to-SQL
```

Codex 会按需刷新索引，找到对应的本地 PDF，先从摘要开始，再解释论文主张和可实现的 method pipeline。之后自然追问即可：

```text
按实现视角带我走一遍 pipeline。
每个 agent 保存什么状态？反馈如何影响下一步？
把这篇放进我正在写的综述脉络里。
为这篇生成简洁的 HTML 笔记。
```

HTML 笔记会结合论文和你们的讨论生成。后续提问改变了对论文的理解时，Codex 应更新同一份笔记；本地支持渲染时，也可以放入原生 PDF 截图。

## 自动重命名与归档

自动归档是可选的：配置工作区时启用，或者直接让 Codex 整理新 PDF。

启用后，工作流会：

- 从 PDF 文本中识别真实标题，尽量忽略会议页眉等通用元数据；
- 将下载文件规范化为论文标题对应的文件名；
- 依据可编辑的本地规则放入唯一的 `papers/<category>/` 目录；
- 发现同名文件时加后缀保留，不会覆盖；
- 在路径变化后同步更新搜索索引、source registry、BibTeX 的 `Source` 注释和本地笔记链接。

初始分类是通用的。你只需告诉 Codex 想怎样分组，它会调整 `references/organization_rules.json` 和本地 `AGENTS.md`。无法可靠判断的论文会留在兜底分类；工作流不会删除 PDF。

## Codex 维护的内容

```text
your-workspace/
├── papers/                 # 已归档 PDF
├── notes/                  # HTML 笔记
│   └── assets/             # 原生 PDF 截图
├── references/             # 索引、source registry、归档规则
└── AGENTS.md               # 你的稳定阅读偏好
```

一个阅读对象可以拥有多个 source：本地 PDF、arXiv、DOI、项目页、代码仓库、slides 或技术文档。它们会被记录为同一个 entity，因此复制来的标题无需和下载文件名一致。

## 把它变成你的工作流

直接告诉 Codex：

```text
阅读和笔记使用中文。
重点关注实现细节和 pipeline 复现。
默认跳过实验，除非我问。
我正在写综述，所以更关注 related work 和论文定位。
每篇论文也关联项目页和 GitHub repo。
```

Codex 会把稳定偏好精简地维护在该工作区的 `AGENTS.md`。公开 skill 提供稳定的工具和流程；你的工作区定义具体的研究语境。

## 维护者测试

```bash
python3 tests/smoke_test.py
python3 tests/privacy_scan.py
```

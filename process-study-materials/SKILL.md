---
name: process-study-materials
description: Process study materials (papers/articles/git repos) into the standardized scc_record pipeline: translate to Chinese, clone repos, and build offline lecture HTMLs with rich visuals. Use when the user mentions new materials, papers, articles, git repos, weekly-meeting presentations, or organizing study materials.
---

# 材料处理流水线

当你收到"新材料"/"论文"/"文章"/"git repo"或类似意图的信号时,自动走以下流程。

## 快速概览

所有产物集中到素材根目录 `$RECORD_ROOT`(默认 `D:\scc_record\`;Linux/macOS 下用对应挂载路径,如 `/mnt/d/scc_record`):

```
$RECORD_ROOT/
├── 01-papers/       ← 论文 PDF
├── 02-articles/     ← 文章(EN/ZH 双语,NN_Name_Desc_EN|ZH.md)
├── 03-notes/        ← 学习笔记
├── 04-web/          ← 离线讲解网页(NN_Name_Desc.html,100% 自包含)
└── 05-repos/        ← 克隆的仓库代码
    ├── 01-paper-impl/         ← 论文实现
    ├── 02-second-brain/       ← Second Brain 生态
    └── 03-memory-engineering/ ← 记忆工程
```

所有产物都按普通文件落盘:用 Write/Edit 工具直接写入目标路径,不走单独的 CCKB 反哺子流程。

## 执行顺序

1. **落盘原始材料 + clone 仓库**(快,先做;clone 放后台,不等它)
2. **翻译**(重活,子代理分块,见步骤一)
3. **构建讲解网页**(最后做——它依赖译文和对 repo 代码的理解)
4. **更新 `$RECORD_ROOT/README.md` 关系表 + 过验证清单**

## 步骤一:识别材料类型并准备

**输入**可能是以下一种或多种的组合:

| 材料类型 | 准备工作 |
|---------|---------|
| 论文 PDF | 保存到 `01-papers/`;翻译全文为中文(见下),译文保存到 `02-articles/` |
| 文章(URL/文本) | 英文 → 先翻译成中文;中英文版本均保存到 `02-articles/` |
| git 仓库(URL) | `git clone` 到 `05-repos/` 对应子目录(见"仓库分类") |

**翻译长文(论文/长文章)**:
- 按章节/小节切分,每块派一个子代理翻译,**译一块落一块**(直接写入目标文件),主上下文只保留进度状态——不要把整篇长文塞进主上下文再逐段输出
- 全部译完后校验完整性:对照原文目录确认章节数一致、末尾段落存在(长文翻译最常见的问题是漏段)

**仓库分类**:按主题判断落入 `01-paper-impl` / `02-second-brain` / `03-memory-engineering`;都不匹配时新建 `NN-新类别/` 子目录(NN 取现有最大序号 +1),并在 `$RECORD_ROOT/README.md` 更新目录说明。clone 失败(网络/私有仓库)直接报告,不要卡住重试。

**命名规范**:统一 `NN_主题_英文描述[_EN|ZH].pdf|md|html`,NN 序号取目标目录现有最大序号 +1(先 `ls` 确认,不要凭记忆)。完整规则与示例见 [references/naming.md](references/naming.md)。

## 步骤二:构建离线讲解网页

放在 `04-web/`。如果多个材料(文章 + 多个 repo)关联,建一个综合网页。动手前先读一个 `04-web/` 现有 HTML 对齐风格。

**核心提示词**(直接使用):

> 构建一个离线网页 纯html 里面有结构图 graph 等丰富的用于辅助展示的讲解信息 用中文 来讲解这个文章的主题知识和结构思路 就用来把这个长文进行讲解细节 讲清楚所有的细节 网页参看reactbits的组件 要高级美观

**网页要求**:
- **100% 离线自包含**:所有 CSS、JS、SVG 内联,零外部请求(不引用 CDN、字体库、外链图片)。图表一律手绘内联 SVG——不要把 ECharts/D3 整个库 inline 进来(体积失控),也不要引 CDN
- **ReactBits 风格组件**:参考 reactbits.dev 的组件设计(Glassmorphism 卡片、AnimatedContent、渐变背景、Spotlight 效果等),追求高级美观
- **结构图/Graph**:架构图、流程图等丰富的可视化,图要承载信息而非纯装饰
- **长文导航**:内容多屏时加锚点目录(TOC),可折叠分节
- **体现仓库代码理解**:材料涉及 repo 时,需体现对仓库代码结构的分析
- **中文讲解**:详细、逐点讲清楚
- **写文件**:单文件较大时分节写入(先 Write 骨架再 append),避免单次输出截断
- **完成后浏览器预览验证**:打开 HTML 确认零控制台错误、渲染正常、无外部请求(Network 面板);本机无浏览器时把路径交给用户打开确认

## 已知参考

- 已处理的材料历史在 `$RECORD_ROOT/README.md` 的关系映射表中
- 之前构建的网页风格可参考 `04-web/` 现有 HTML 文件

## 验证清单

- [ ] NN 序号已与目标目录现有文件核对(无冲突、无跳号)
- [ ] 文章/论文已翻译为中文版本,且章节完整(对照原文目录)
- [ ] 仓库已克隆完成(含 `.git`)
- [ ] HTML 网页:零外部资源、浏览器预览无错误
- [ ] 所有产物已作为普通文件落盘到目标路径
- [ ] 如新增仓库子类别,已更新 `$RECORD_ROOT/README.md` 的目录说明
- [ ] 已在 `$RECORD_ROOT/README.md` 关系表中补充本次条目

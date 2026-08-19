# 代码清理 / 项目优化类 Skill 调研

> 调研日期：2026-08-19
> 主题：社区中用于"删减不必要代码、优化项目"的 Agent Skill 现状

## 总览

社区中相关 skill 大致分三类：

1. **死代码清理** — 专注识别并安全删除无用代码
2. **整体仓库清理** — 代码、依赖、文档、测试一起瘦身
3. **代码简化 / 去过度设计** — 不只删，还重构精简（尤其针对 AI 生成代码的冗余）

---

## 一、死代码清理类

| Skill | 来源 | 特点 |
|---|---|---|
| remove-deadcode | [code-yeongyu/oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent/blob/dev/.agents/skills/remove-deadcode/SKILL.md) | orchestrator 扫描 → LSP 引用验证 → 并行子代理批量删除，原子化 commit；**"LSP 验证优先于 ripgrep 猜测"**，删除安全性最好 |
| Dead Code Sweep | [mcpmarket](https://mcpmarket.com/tools/skills/dead-code-sweep) | 从入口点做可达性分析，找孤儿文件、未使用 export、冗余逻辑、死分支；先出高置信度报告再删 |
| Knip Dead Code | [lobehub](https://lobehub.com/skills/comeonoliver-skillshub-knip-deadcode) | JS/TS 专用，基于 Knip 工具；43 条按优先级排序的规则（入口配置、monorepo、依赖分析、CI 集成、auto-fix） |
| Dead Code Eliminator | [mcpmarket](https://mcpmarket.com/tools/skills/dead-code-eliminator-2) | Swift/Xcode 专用；清理 `#if false` 块、stub 文件、废弃变体 |

## 二、整体仓库清理类

| Skill | 来源 | 特点 |
|---|---|---|
| cleanup-sprint | [skills-hub](https://skills-hub.ai/skills/cleanup-sprint) | 深度清理全家桶：死代码、lint/format 告警、孤儿文件、过期 TODO、安全隐患、import 整理 |
| repo-cleanup | [mcpmarket](https://mcpmarket.com/tools/skills/repository-cleanup) | 强调安全流程：删前基线检查 → 用法验证 → 删后跑测试；范围含死代码、未用依赖、过时文档、脆弱测试 |
| code-and-test-cleanup | [mcpmarket](https://mcpmarket.com/tools/skills/code-and-test-cleanup) | 同时清理源码和测试套件的 bloat（琐碎测试、陈旧注释）；支持 Go/TS/Python |
| codebase-refactoring-cleanup | [mcpmarket](https://mcpmarket.com/zh/tools/skills/codebase-refactoring-cleanup) | 基于 clean code 和 SOLID 原则重构，降复杂度、去重复 |

## 三、代码简化 / 去过度设计类

| Skill | 来源 | 特点 |
|---|---|---|
| code-simplification | [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills/blob/main/skills/code-simplification/SKILL.md)（仓库 54.5k star） | 最知名。五原则：行为完全不变、遵循项目惯例、清晰优先、不过度简化、限定改动范围；专治 AI 生成代码的冗余抽象、注释掉的死代码、误导性命名 |
| Simplification Cascades | [mcpmarket](https://mcpmarket.com/tools/skills/simplification-cascades-1) | 战略型：找"一个改动能消除多个组件"的核心洞察，砍架构层 bloat |
| Code Simplification Expert | [mcpmarket](https://mcpmarket.com/tools/skills/code-simplification-expert) | YAGNI 原则：删投机性功能、内联一次性函数、拍平深层嵌套 |
| Batch Code Cleanup | [mcpmarket](https://mcpmarket.com/zh/tools/skills/batch-code-cleanup) | 严格验证协议（ripgrep 搜索 + import 检查）后批量删未用依赖和死代码 |

---

## 关键设计模式（值得借鉴）

### 1. 删除前的安全验证（最重要）

- **LSP 引用验证优先于文本搜索**：`remove-deadcode` 要求删除任何符号前必须用 LSP `FindReferences` 确认零引用，ripgrep 只做初筛。
- **保护入口点**：`src/index.ts`、`main.py`、`__main__.py` 等入口文件永不删除。
- **可达性分析**：从项目入口出发 trace，不可达的才算候选死代码。

### 2. 流程基线

`repo-cleanup` 的三段式流程：

1. 删前：跑通测试/构建，建立基线
2. 删中：原子化 commit，每批删除可独立回滚
3. 删后：重跑基线验证，绿了才算完

### 3. 原则框架

`addyosmani/code-simplification` 的核心思想：

- **Chesterton's Fence**：先搞懂这段代码为什么存在，再决定删不删
- 目标是降低复杂度，不是减少行数
- 不为简化而引入新的抽象

---

## 分语言工具约定

| 语言 | 死代码/未用依赖检测工具 |
|---|---|
| JS/TS | Knip、ts-prune、depcheck |
| Python | vulture、ruff（F401 等规则）、pip-check-reqs |
| Go | staticcheck（U1000）、go vet、deadcode（官方工具） |
| Swift | Periphery、Xcode 静态分析 |

---

## 结论与建议

如果要在本仓库沉淀一个自己的清理 skill，最值得参考的两个蓝本：

1. **remove-deadcode** — 安全验证流程（LSP 引用验证 + 保护入口点 + 原子 commit），删除类操作的核心是"不删错"；
2. **addyosmani/code-simplification** — 原则框架（Chesterton's Fence + 五条简化原则），防止过度删除和过度重构。

建议组合：用第二类 skill 的流程骨架（基线 → 删除 → 验证），填第一类的验证手段和第三类的原则约束。

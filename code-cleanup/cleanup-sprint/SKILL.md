---
name: cleanup-sprint
description: Deep whole-repo cleanup sprint — dead code, lint/format warnings, orphaned files, stale TODOs, security hazards, unused dependencies, and import organization. Use when the user asks for codebase cleanup, decluttering, technical debt cleanup, spring cleaning, or code hygiene.
---

# 整体仓库清理冲刺

> 来源: [skills-hub — cleanup-sprint](https://skills-hub.ai/skills/cleanup-sprint)

一次把仓库的代码、依赖、文档、测试一起瘦身。**先出报告再动手**,全程基线保护。

## 安全流程(repo-cleanup 三段式)

1. **删前基线**:跑通测试/构建,记录基线;不绿先修基线再谈清理
2. **删中**:每类清理独立原子 commit,任何一批可单独回滚
3. **删后**:重跑基线,绿了才算完;红了回滚该批

## 清理清单(按风险从低到高)

| 类别 | 做法 |
|---|---|
| lint / format 告警 | 跑项目既有 linter/formatter 的 `--fix`,零告警收尾 |
| import 整理 | 删未用 import、统一排序(遵循项目工具:isort / organize-imports) |
| 过期 TODO/FIXME | 已失效的删除;仍有效的补 issue 链接或日期,不留无主体 TODO |
| 孤儿文件 | git 历史 + 引用搜索确认无引用后删除;入口/配置文件永不删 |
| 未用依赖 | depcheck / pip-check-reqs 等检测后从清单移除,并跑安装+测试验证 |
| 死代码 | 按 [[remove-deadcode]] 的验证标准执行(引用确认为零才删) |
| 安全隐患 | 硬编码密钥、`eval`/`exec` 滥用、过时高危依赖 → 只标记报告,修复需用户确认 |
| 脆弱测试 | 报告琐碎/失效测试,**删除测试前必须用户确认** |

## 输出

- 每类清理一个 commit;最终输出汇总表:类别 / 处理项数 / 跳过项及原因
- 基线测试前后对比必须全绿

## 红线

- 不动行为:纯清理,不顺手重构、不顺手改逻辑(重构走 [[code-simplification]])
- 无引用的"看起来没用"的文件,仍要确认不是动态加载/约定式入口再删

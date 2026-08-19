---
name: remove-deadcode
description: Safely remove dead code (unused symbols, orphaned files, dead exports) via scan → LSP reference verification → batched parallel deletion with atomic commits. Use when the user asks to remove dead code, unused functions/exports/files, or delete unreachable code.
---

# 死代码清理(orchestrator 模式)

> 来源: [code-yeongyu/oh-my-openagent — remove-deadcode](https://github.com/code-yeongyu/oh-my-openagent/blob/dev/.agents/skills/remove-deadcode/SKILL.md)

主代理只做编排,不动手删代码。核心原则:**LSP 验证是法律,ripgrep 只做初筛**。

## 五阶段流程

### 1. 扫描(Scan)
- 编译器/静态分析初筛(按语言选工具,见下)
- 并行 explore 子代理找孤儿文件与未使用 export
- 产出候选清单(符号/文件 + 所在路径)

### 2. 验证(Verify)
- 每个候选必须经 LSP `FindReferences`(不含声明本身)确认**零引用**才算死代码
- 误报守卫(永不删除):
  - 入口文件(`main.py` / `__main__.py` / `src/index.ts` 等)
  - 测试文件、配置文件
  - barrel re-export、`@public` / `@api` 标注符号、框架工厂函数、`package.json` exports 声明的入口
- 未使用参数不删,改为 `_` 前缀
- 候选超过 50 个时先停下来跟用户确认

### 3. 分批(Batch)
- 按文件路径分组:同一文件的项必须在同一批(防并行编辑冲突)
- 整文件删除单独成批
- 目标 5–15 批

### 4. 执行(Execute,并行子代理)
- 每批派一个子代理:先**重新验证引用**(其他代理可能已改动),再编辑、类型检查、提交
- 每批一个原子 commit(`refactor:` 前缀),只 `git add` 自己的文件,**永不 `git add -A`**
- 类型检查失败 → revert 该批并报告,不要尝试顺手修

### 5. 终验(Final Verification)
- 跑全量 typecheck / test / build,全绿才算完
- 输出汇总表:已删除 / 跳过(及原因)/ 验证结果

## 分语言初筛工具

| 语言 | 工具 |
|---|---|
| TS | `tsc --noEmit --noUnusedLocals --noUnusedParameters` |
| Python | `vulture`、`ruff`(F401 等) |
| Go | `staticcheck`(U1000)、官方 `deadcode` |

## 红线

- 主代理(orchestrator)自己不改任何代码
- 无 LSP 时降级为保守策略:ripgrep 双查定义与引用 + 人工确认,且默认跳过导出符号
- 构建不可恢复地坏掉 → 中止并回滚

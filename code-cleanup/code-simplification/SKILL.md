---
name: code-simplification
description: Simplify code for clarity while preserving exact behavior — fix redundant abstractions, dead/commented-out code, misleading names, deep nesting, over-engineering (especially AI-generated bloat). Use when the user asks to simplify, clean up, de-over-engineer, or refactor code for readability without changing behavior.
---

# 代码简化(去过度设计)

> 来源: [addyosmani/agent-skills — code-simplification](https://github.com/addyosmani/agent-skills/blob/main/skills/code-simplification/SKILL.md)

核心判据:**新团队成员能比现在更快看懂这段代码吗?** 目标是降低理解成本,不是减少行数。

## 五条原则

1. **行为完全不变**:输入、输出、副作用、错误行为、边界情况全部保持原样。拿不准就不改。
2. **遵循项目惯例**:简化是与现有代码库保持一致,不是强加个人偏好——先看 CLAUDE.md 和邻近代码。
3. **清晰优先于精巧**:需要心算解析的紧凑代码不如显式的朴素代码(嵌套三元 → if/else;密集 reduce → 命名中间步骤)。
4. **不过度简化**:不内联给了概念名字的 helper;不合并无关函数;不删除为扩展性/可测试性存在的抽象。
5. **限定改动范围**:默认只简化本次改动过的代码,不搞顺手重构,除非用户明确要求扩大。

## 目标代码味道

- **结构**:3+ 层嵌套、50+ 行长函数、嵌套三元、布尔 flag 参数、重复条件分支
- **命名**:`data`/`result`/`temp` 等泛名、`usr`/`cfg` 缩写、误导性命名;解释"是什么"的注释删掉,解释"为什么"的保留
- **冗余**:5+ 行重复逻辑、死代码、注释掉的死代码、不必要的抽象、过度设计的模式、冗余类型断言
- **AI 生成代码常见**:为单一调用点造的通用抽象层、防御不必要边界的校验、"以后可能有用"的投机性功能(YAGNI)

## 流程

1. **先懂再动**(Chesterton's Fence):这段代码为什么存在?谁调用它?边界情况?为什么写成这样?必要时 `git blame` 找原始上下文
2. **扫描机会点**:对照上面的具体信号,不靠模糊感觉
3. **增量应用**:一次一个简化,每步后跑测试;简化与功能/修 bug 分开提交;触及 500+ 行时改用自动化(codemod/AST)而非手工
4. **验证结果**:对比前后——真更好懂吗?diff 干净吗?同事会 approve 吗?否则 revert

## 红线(出现即停)

- 简化需要改测试 → 你改了行为,停
- 简化后更长或更难懂 → 方向错了
- 为"干净"删除错误处理
- 不懂这段代码就动手
- 把多个简化塞进一个大 commit
- 重构超出当前任务范围的代码

## 验证清单

- [ ] 全部测试通过且未修改测试
- [ ] 构建、linter 通过
- [ ] 无错误处理被削弱
- [ ] 无残留死代码
- [ ] diff 增量可审查,符合项目惯例

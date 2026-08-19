# scc-SKILLS

个人 skill 集:AutoML Agent 比赛技能 + 学习材料处理流水线 + 代码清理/优化,附比赛存档。

## Skills(git 跟踪)

### AutoML 比赛类(双模式:本地直接跑脚本,或在 ADK / kaggle-kaggle 沙箱中通过 `run_skill_script` / `load_skill_resource` 调用,详见各自 `SKILL.md`)

| Skill | 用途 |
|---|---|
| `eda-feature-scan/` | 表格数据 EDA 两阶段流水线:特征扫描(Polars)+ 编码/填充配置生成 |
| `feature-engineer/` | 泄漏安全的自动特征工程(插补、行统计、datetime 部件、类别编码) |
| `review-experiment/` | JSONL 实验日志:结构化 review 提交 + 历史检索,按数据集指纹自动隔离 task |

### 学习材料处理类(工作流型,无脚本)

| Skill | 用途 |
|---|---|
| `process-study-materials/` | 学习材料处理流水线:论文/文章翻译、仓库克隆、离线讲解网页构建 |

### 代码清理 / 优化类(工作流型,无脚本,源自社区,来源见各 SKILL.md)

| Skill | 用途 |
|---|---|
| `remove-deadcode/` | 死代码清理:扫描 → LSP 引用验证 → 并行子代理分批删除,原子化 commit |
| `cleanup-sprint/` | 整体仓库清理:代码+依赖+文档+测试一起瘦身,基线保护三段式 |
| `code-simplification/` | 代码简化/去过度设计:行为不变前提下重构精简,专治 AI 生成代码冗余 |

## 比赛存档(本地,不入库)

`competition/`(已被 .gitignore 排除)收录 Kaggle-in-Kaggle 比赛的全部资料,入口为 **`competition/COMPETITION.md`**(提交记录、配置谱系、实验总结、工作流与线上推荐配置 v1.1):

```
competition/
├── COMPETITION.md   # 总文档
├── agents/          # 各版本 agent 配置(v1/v4.1/v5/v5.1/v1.1 + 子代理)
├── prompts/         # 各版本 prompt
├── references/      # 上下文管理方法论、环境坑清单、执行规则
└── reports/         # 本地评测汇总报告(html)
```

## 其他

- `references/code_cleanup_skills_research.md`:代码清理类 skill 调研笔记

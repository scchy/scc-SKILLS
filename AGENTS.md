# AGENTS.md — 本仓库开发规则

本仓库是个人 Agent Skill 集 + 比赛存档。改动任何 skill 前,先读完对应 `SKILL.md`。

## 仓库结构

- `<skill-name>/` — 一个目录一个 skill,内含 `SKILL.md`(必需)、`references/`(参考文档)、`scripts/`(可执行脚本)
- `scripts/` — 仓库级工具(如 `validate_skills.py`),不是 skill
- `competition/` — 比赛存档,**gitignore 本地保留,永不入库**
- `.github/workflows/ci.yml` — 结构校验 + 脚本编译(py3.8/3.12 矩阵)

## Skill 编写规则

1. **frontmatter 三硬约束**(CI 强制):`name` / `description` 非空;`name` 与目录名一致(ADK 加载依赖)。
2. **description 是唯一的触发依据**:写清"做什么 + 何时用",别把路径等实现细节塞进去。
3. **目录约定**:参考文档一律放 `references/`,脚本放 `scripts/`——ADK 只认 `references/` / `assets/` / `scripts/`。SKILL.md 内的相对链接必须真实存在(CI 链接校验)。
4. **双模式**(带脚本的 skill):SKILL.md 需同时给出「本地直接跑」与「ADK 沙箱 `run_skill_script` / `load_skill_resource`」两种调用方式;沙箱段落必须强调:skill 文件不在沙箱文件系统上、脚本在临时目录执行、数据 I/O 传 `/work` 下绝对路径。工作流型 skill(无脚本)不需要双模式章节。
5. **保持精简**:SKILL.md 是 prompt,不是文档——能一句话说清的别写一段;prompt 文本的边际收益接近噪声,只写有行为影响的内容。

## 脚本规则

1. **Python 3.8 兼容**:类型标注依赖 `from __future__ import annotations`,不用 3.9+ 语法(CI 矩阵守这条线)。
2. **零第三方依赖假设**:仓库级脚本(如 `validate_skills.py`)必须纯标准库;skill 脚本只用目标沙箱已预装的库。
3. **输出协议**(agent 可解析):stdout 只打紧凑 JSON 结果,日志/警告走 stderr;失败非零退出并打 `{"status": "error", ...}`。
4. **防御性可选依赖**:非关键产物(如 Excel 导出)缺库时 warning 跳过,不许整体崩溃。

## 提交流程

1. 提交前本地必过:`python scripts/validate_skills.py` 和 `python -m compileall -q */scripts/ scripts/`。
2. commit message:emoji 前缀 + 中文简述(参照 git log 风格:✨/🐛/📝/♻️/🔒)。
3. 比赛相关内容(prompt、agent 配置、实验记录)一律放 `competition/`,不得提交入库。

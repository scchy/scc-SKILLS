#!/usr/bin/env python3
"""validate_skills.py — 校验本仓库所有 skill 的结构与内部链接。

- **结构**:含 SKILL.md 的目录即为一个 skill;frontmatter 的 `name` / `description`
  必须非空(description 是 Agent 判断"何时触发技能"的唯一依据),且 `name`
  必须与目录名一致(ADK 加载的硬性要求)。
- **链接**:扫描所有 .md 的 Markdown 内部链接,相对路径按「文件所在目录」+
  「仓库根」双基准解析,消灭 404 与幻觉链接。外部 http(s):// 链接跳过,不联网。

退出码:任何 FAIL → 1;仅 WARN → 0。纯标准库实现,无第三方依赖。

用法:
    python scripts/validate_skills.py
"""

import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 遍历时跳过的目录
_SKIP_DIRS = (".git", "__pycache__", ".venv", "node_modules")
# 非本地文件的链接前缀
_SKIP_LINK_PREFIXES = ("http://", "https://", "mailto:", "ftp://", "tel:")
_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")  # markdown 链接 [text](target)
_INDENTED = re.compile(r"^\s+")  # 缩进续行(frontmatter folded 块)


def walk_md(repo_root):
    """遍历仓库根下所有 .md 文件。"""
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".md"):
                yield os.path.join(dirpath, fn)


def find_skill_dirs(repo_root):
    """目录内含 SKILL.md 即视为一个 skill 目录。"""
    skills = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if "SKILL.md" in filenames:
            skills.append(os.path.normpath(dirpath))
    return sorted(skills)


def parse_frontmatter(text):
    """极简 frontmatter 解析(含 BOM 剥离 + folded 缩进续行),返回键值 dict。

    - `key: value` → fm[key] = value
    - `key: >-` 等 folded 标记后,缩进续行追加到该 key(如多行 description)
    """
    text = text.lstrip("\ufeff")
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    meta = []
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        meta.append(lines[i])
        i += 1
    fm = {}
    key = None
    for line in meta:
        m = re.match(r"^([A-Za-z_][\w.-]*)\s*:\s*(.*)$", line)
        if m and not _INDENTED.match(line):
            key = m.group(1)
            fm[key] = m.group(2).strip()
            continue
        if key and _INDENTED.match(line) and line.strip():
            # folded 块续行:追加到当前 key
            fm[key] = ((fm.get(key) or "") + " " + line.strip()).strip()
    return fm


def check_skill(skill_dir):
    """结构校验:SKILL.md 非空、frontmatter name/description 非空、name == 目录名。

    返回 (fails, warns)。
    """
    fails = []
    warns = []
    rel = os.path.relpath(skill_dir, REPO_ROOT)
    skillmd = os.path.join(skill_dir, "SKILL.md")
    with open(skillmd, encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
        return [f"[{rel}] SKILL.md 为空"], warns
    fm = parse_frontmatter(text)
    for field in ("name", "description"):
        val = str(fm.get(field) or "").strip(" >-|'\"").strip()
        if not val:
            fails.append(f"[{rel}] frontmatter 缺非空 {field}")
    name = str(fm.get("name") or "").strip()
    if name and name != os.path.basename(skill_dir):
        fails.append(f"[{rel}] frontmatter name={name!r} 与目录名不一致")
    return fails, warns


def resolve_link(base_dir, raw):
    """把相对链接解析为候选绝对路径(文件所在目录 + 仓库根双基准)。

    返回 None 表示无需校验(外部链接/纯锚点/空)。
    """
    target = raw.strip()
    if not target or target.startswith(_SKIP_LINK_PREFIXES):
        return None
    target = target.split("#", 1)[0].split("?", 1)[0]  # 去锚点/查询串
    if not target:
        return None
    if os.path.isabs(target):
        return [target]
    return [os.path.join(base_dir, target), os.path.join(REPO_ROOT, target)]


def check_links(path):
    """校验一个 .md 文件的所有内部链接。返回 fails。"""
    fails = []
    rel = os.path.relpath(path, REPO_ROOT)
    base_dir = os.path.dirname(path)
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    if lines:
        lines[0] = lines[0].lstrip("\ufeff")
    for lineno, line in enumerate(lines, 1):
        for lm in _LINK_RE.finditer(line):
            raw = lm.group(1)
            candidates = resolve_link(base_dir, raw)
            if candidates and not any(
                os.path.exists(os.path.normpath(c)) for c in candidates
            ):
                fails.append(f"[{rel}:{lineno}] 链接失效 {raw}")
    return fails


def main():
    # Windows 控制台默认代码页非 UTF-8,强制 UTF-8 输出避免中文乱码
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    fails = []
    warns = []

    # 1) 结构校验:每个 skill 目录
    skill_dirs = find_skill_dirs(REPO_ROOT)
    if not skill_dirs:
        fails.append("未找到任何 skill(含 SKILL.md 的目录)")
    for sd in skill_dirs:
        sfails, swarns = check_skill(sd)
        fails.extend(sfails)
        warns.extend(swarns)

    # 2) 链接校验:所有 .md 内部链接
    md_files = list(walk_md(REPO_ROOT))
    for path in md_files:
        fails.extend(check_links(path))

    # 3) 汇总
    print(f"校验 {len(skill_dirs)} 个 skill / {len(md_files)} 个 md …")
    for sd in skill_dirs:
        print(f"  PASS  {os.path.relpath(sd, REPO_ROOT)}")
    for w in warns:
        print("  WARN " + w)
    for f in fails:
        print("  FAIL " + f)

    print(f"\n结果: FAIL={len(fails)} WARN={len(warns)} PASS={len(skill_dirs)}")
    if fails:
        return 1
    print("结构校验通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

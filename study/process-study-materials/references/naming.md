# 命名规范与关系映射表

## 命名规范

统一格式:

```
NN_主题_英文描述[_EN|ZH].pdf|md|html
```

- `NN`:两位序号,**取目标目录现有最大序号 +1**(先 `ls` 目标目录确认,不要凭记忆)
- `主题`:简短英文主题词,驼峰或下划线连接
- `英文描述`:内容的一句话英文概括
- 语言后缀:仅文章需要,`_EN` / `_ZH` 成对出现;PDF 与 HTML 不加

示例:

```
01-papers/06_MemoryData_代理原生记忆系统评测_2606.24775v1.pdf
02-articles/06_MemoryData_AgentNativeMemoryEval_EN.md
02-articles/06_MemoryData_AgentNativeMemoryEval_ZH.md
04-web/06_MemoryData_AgentNativeMemoryEval.html
```

关联材料(论文 + 译文 + 网页 + repo)共享同一个 `NN` 与主题词,便于互相索引。

## 关系映射表

`$RECORD_ROOT/README.md` 中维护一张关系映射表,每处理一批材料补一行:

| NN | 主题 | 论文 | 文章(EN/ZH) | 网页 | 仓库 | 备注 |
|----|------|------|--------------|------|------|------|
| 06 | MemoryData | 01-papers/06_....pdf | 02-articles/06_..._EN.md / _ZH.md | 04-web/06_....html | 05-repos/01-paper-impl/xxx | 一句话说明 |

新增仓库子类别时,同步更新 README 中的目录结构说明。

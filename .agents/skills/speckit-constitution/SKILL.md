---
name: "speckit-constitution"
description: "具有项目原则、治理和版本依据的宪章"
compatibility: "适用于具有 .specify/ 目录的 Spec Kit 项目"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/constitution.md"
---

# 具有项目原则、治理和版本依据的宪章

## User Input

```text
$ARGUMENTS
```

当前用户目标和已有授权是产物范围的依据。

## 上下文入口

```powershell
.specify/scripts/powershell/resolve-template.ps1 constitution-template -Json
```

上下文结果包含适用的 FEATURE_DIR、AVAILABLE_DOCS、模板内容和实际分支。路径采用绝对定位，文档引用采用相对路径。项目宪章提供适用原则，完整输入对应可交付产物。

## 产物

.specify/memory/constitution.md 采用 constitution-template 的当前解析结果，包含完整原则、适用运行规则、治理、版本和日期。

顶部同步影响报告以 HTML 注释记录版本变化、受影响原则、章节和依赖资料。主版本对应原则重新定义，次版本对应原则扩展，补丁版本对应语义澄清。原有首次批准日期保留，最后修订日期对应实际修改。

## 内容范围

写入范围为宪章文件。依赖模板与命令采用运行时宪章输入，独立业务请求归各自任务范围。原则描述具体适用条件和可观察结果，例外具有范围、理由、退出条件及负责人依据。

交付报告包含版本、变更依据、同步影响与约定式提交建议。

## 扩展结果契约

扩展定义来源为 `.specify/extensions.yml`，作用点为 `hooks.before_constitution` 与 `hooks.after_constitution`。有效 YAML 的已启用条目具有执行资格，enabled 默认值为 true。带 condition 的条目由 HookExecutor 求值，空条件条目适用当前会话执行器。

命令标识中的点对应连字符，例如 speckit.git.commit 对应 speckit-git-commit。`optional: false` 的完成凭证包含 `EXECUTE_COMMAND: {command}` 及真实命令结果；`optional: true` 的报告包含命令、描述和用户提示，执行资格依据用户选择。扩展结果与主产物共同组成完成报告。

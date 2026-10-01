---
name: "speckit-taskstoissues"
description: "与任务编号一一对应的 GitHub Issue"
compatibility: "适用于具有 .specify/ 目录的 Spec Kit 项目"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/taskstoissues.md"
---

# 与任务编号一一对应的 GitHub Issue

## User Input

```text
$ARGUMENTS
```

当前用户目标和已有授权是产物范围的依据。

## 上下文入口

```powershell
.specify/scripts/powershell/check-prerequisites.ps1 -Json -RequireTasks -IncludeTasks
```

上下文结果包含适用的 FEATURE_DIR、AVAILABLE_DOCS、模板内容和实际分支。路径采用绝对定位，文档引用采用相对路径。项目宪章提供适用原则，完整输入对应可交付产物。

## 产物

Issue 的目标仓库与 remote.origin.url 解析的 GitHub owner/repository 一致。输入为 FEATURE_DIR/tasks.md，每项标题为 `T001: <正向交付结果>`，正文包含需求来源、文件路径、前置任务及验收标准。

## 唯一性与授权

任务 ID 匹配 `\bT\d{3,}\b`，支持三位及更长编号。查重范围覆盖开放与已关闭 Issue；list_issues 的 state 参数采用默认全状态，perPage 为 100，after 对应 endCursor。查询范围以任务 ID 全部匹配或分页结束为完成条件。

同一任务 ID 的既有 Issue 对应已有结果，新建范围为具有创建授权且具有唯一任务 ID 的项目。标题保留一次任务编号，checkbox、[P]、[US#] 是任务元数据。Issue 依赖与 tasks 的前置关系一致。

交付报告包含目标仓库、任务 ID、既有链接、新建链接与计数。该技能的外部写入范围为用户明确调用的任务转 Issue 操作。

## 扩展结果契约

扩展定义来源为 `.specify/extensions.yml`，作用点为 `hooks.before_taskstoissues` 与 `hooks.after_taskstoissues`。有效 YAML 的已启用条目具有执行资格，enabled 默认值为 true。带 condition 的条目由 HookExecutor 求值，空条件条目适用当前会话执行器。

命令标识中的点对应连字符，例如 speckit.git.commit 对应 speckit-git-commit。`optional: false` 的完成凭证包含 `EXECUTE_COMMAND: {command}` 及真实命令结果；`optional: true` 的报告包含命令、描述和用户提示，执行资格依据用户选择。扩展结果与主产物共同组成完成报告。

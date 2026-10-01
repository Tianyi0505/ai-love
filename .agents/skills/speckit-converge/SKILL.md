---
name: "speckit-converge"
description: "当前实现与功能目标对应的交付任务"
compatibility: "适用于具有 .specify/ 目录的 Spec Kit 项目"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/converge.md"
---

# 当前实现与功能目标对应的交付任务

## User Input

```text
$ARGUMENTS
```

当前用户目标和已有授权是产物范围的依据。

## 上下文入口

```powershell
.specify/scripts/powershell/check-prerequisites.ps1 -Json -RequireSpec -RequireTasks -IncludeTasks
```

上下文结果包含适用的 FEATURE_DIR、AVAILABLE_DOCS、模板内容和实际分支。路径采用绝对定位，文档引用采用相对路径。项目宪章提供适用原则，完整输入对应可交付产物。

## 产物

实现核对报告包含 Finding ID、Source、Evidence、Severity、Gap Type 和目标结果。来源为 FR、SC、用户故事、计划决策及适用宪章条款，代码范围由设计及任务的路径确定。

分类代码为 missing、partial、contradicts、unrequested。优先级为 CRITICAL、HIGH、MEDIUM、LOW，宪章必需条款和 P1 基础行为对应最高优先级。

## 任务写入契约

适用条件为 tasks 已生成且当前 implement 已运行。写入范围为 tasks.md 末尾追加的 `## Phase N: Convergence`，既有内容、编号、排序和状态完整保留。

N 等于已有最大阶段编号加 1，新任务 ID 为 `T{M+1:03d}` 起的连续编号，允许四位及更长编号。每项使用 `[ ]`，具有来源、文件路径及正向目标结果。任务优先级对应报告证据。

`tasks_appended` 结果包含阶段、追加数和 implement 入口；`converged` 结果表示规格、计划与任务的当前目标均有实现证据，此时 tasks.md 字节保持原值。

## 扩展结果契约

扩展定义来源为 `.specify/extensions.yml`，作用点为 `hooks.before_converge` 与 `hooks.after_converge`。有效 YAML 的已启用条目具有执行资格，enabled 默认值为 true。带 condition 的条目由 HookExecutor 求值，空条件条目适用当前会话执行器。

命令标识中的点对应连字符，例如 speckit.git.commit 对应 speckit-git-commit。`optional: false` 的完成凭证包含 `EXECUTE_COMMAND: {command}` 及真实命令结果；`optional: true` 的报告包含命令、描述和用户提示，执行资格依据用户选择。扩展结果与主产物共同组成完成报告。

---
name: "speckit-implement"
description: "任务定义范围内的实现与验收结果"
compatibility: "适用于具有 .specify/ 目录的 Spec Kit 项目"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/implement.md"
---

# 任务定义范围内的实现与验收结果

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

任务定义的代码、配置和文档具有实际交付结果；tasks.md 的 `[x]` 对应实现及适用验收证据，`[ ]` 对应目标结果。任务顺序以依赖为依据，独立文件任务具有可并行范围。

输入包含 spec.md、plan.md、tasks.md、适用 research.md、data-model.md、contracts/ 和宪章。实施范围由用户授权及任务确定，现有工作区内容具有明确归属。

## 质量门槛

checklists/ 的权限为只读状态核对。每份清单的报告包含 Total、Checked、Open 和 Status。自定义 `[x]` 是评审者的需求质量确认；内置 requirements.md 由 specify/clarify 维护。

实施资格为所有清单标准均满足，或用户已明确授权接受当前清单状态。需要该例外时，确认资料包含具体清单、开放项目与对应规则依据。此前相应授权持续有效。

## 完成标准

每个交付结果具有可用代码、必要配置、适用检查和真实状态记录。验证结果明确环境、边界替身、已测范围及目标。最终报告包含完成任务数、主要变化、验收证据与下一项可交付结果。

## 扩展结果契约

扩展定义来源为 `.specify/extensions.yml`，作用点为 `hooks.before_implement` 与 `hooks.after_implement`。有效 YAML 的已启用条目具有执行资格，enabled 默认值为 true。带 condition 的条目由 HookExecutor 求值，空条件条目适用当前会话执行器。

命令标识中的点对应连字符，例如 speckit.git.commit 对应 speckit-git-commit。`optional: false` 的完成凭证包含 `EXECUTE_COMMAND: {command}` 及真实命令结果；`optional: true` 的报告包含命令、描述和用户提示，执行资格依据用户选择。扩展结果与主产物共同组成完成报告。

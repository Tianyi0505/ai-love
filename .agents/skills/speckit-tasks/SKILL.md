---
name: "speckit-tasks"
description: "按依赖和用户故事组织的交付结果清单"
compatibility: "适用于具有 .specify/ 目录的 Spec Kit 项目"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/tasks.md"
---

# 按依赖和用户故事组织的交付结果清单

## User Input

```text
$ARGUMENTS
```

当前用户目标和已有授权是产物范围的依据。

## 上下文入口

```powershell
.specify/scripts/powershell/setup-tasks.ps1 -Json
```

上下文结果包含适用的 FEATURE_DIR、AVAILABLE_DOCS、模板内容和实际分支。路径采用绝对定位，文档引用采用相对路径。项目宪章提供适用原则，完整输入对应可交付产物。

## 产物

FEATURE_DIR/tasks.md 使用 TASKS_TEMPLATE_CONTENT 的当前结构，以 spec、plan 和适用设计资料为依据。任务按用户故事与优先级组织，每个故事具有独立可观察结果与验收条件。

项目格式为 `- [ ] T001 [P] [US1] <文件路径> 提供 <结果>`。T 编号连续；故事标签适用于故事任务；[P] 对应前置结果满足后文件互相独立的范围。每项结果具体、可验收，依赖和需求映射明确。

## 范围与质量

测试任务适用于功能规格或用户明确要求的验证范围。准备、公共基础、用户故事与交付各有结果边界。任务中的路径对应实际设计结构，目标与完成证据分别由 `[ ]`、`[x]` 表达。

交付报告包含绝对路径、任务数、各故事数量、依赖、独立范围、最小交付切片和格式核验结果。

## 扩展结果契约

扩展定义来源为 `.specify/extensions.yml`，作用点为 `hooks.before_tasks` 与 `hooks.after_tasks`。有效 YAML 的已启用条目具有执行资格，enabled 默认值为 true。带 condition 的条目由 HookExecutor 求值，空条件条目适用当前会话执行器。

命令标识中的点对应连字符，例如 speckit.git.commit 对应 speckit-git-commit。`optional: false` 的完成凭证包含 `EXECUTE_COMMAND: {command}` 及真实命令结果；`optional: true` 的报告包含命令、描述和用户提示，执行资格依据用户选择。扩展结果与主产物共同组成完成报告。

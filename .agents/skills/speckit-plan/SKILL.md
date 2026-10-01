---
name: "speckit-plan"
description: "功能实施所需的设计产物"
compatibility: "适用于具有 .specify/ 目录的 Spec Kit 项目"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/plan.md"
---

# 功能实施所需的设计产物

## User Input

```text
$ARGUMENTS
```

当前用户目标和已有授权是产物范围的依据。

## 上下文入口

```powershell
.specify/scripts/powershell/setup-plan.ps1 -Json
```

上下文结果包含适用的 FEATURE_DIR、AVAILABLE_DOCS、模板内容和实际分支。路径采用绝对定位，文档引用采用相对路径。项目宪章提供适用原则，完整输入对应可交付产物。

## 产物

| 文档 | 结果 |
| --- | --- |
| plan.md | Summary、Technical Context、Constitution Check、Project Structure 和设计收益 |
| research.md | Decision、Rationale 与适用依据 |
| data-model.md | 实体、字段、关联、唯一性及状态语义 |
| contracts/ | 适用外部接口的当前输入、输出、授权和结果 |
| quickstart.md | 环境条件、运行入口和端到端验收标准 |

当前规格与宪章是设计依据。技术决策具有明确理由，数据和权限归属与用户目标一致，宪章检查覆盖适用原则。外部接口契约的生成条件为实际公开接口需求。

## 交付范围

设计完成状态以可实施的技术选择和完整产物为依据。quickstart 提供运行及验收入口，完整实现归 tasks 与 implement。文件操作采用绝对路径，文档引用采用项目相对路径。

交付报告包含实际 Git 分支、计划绝对路径、生成文档及设计检查结果。

## 扩展结果契约

扩展定义来源为 `.specify/extensions.yml`，作用点为 `hooks.before_plan` 与 `hooks.after_plan`。有效 YAML 的已启用条目具有执行资格，enabled 默认值为 true。带 condition 的条目由 HookExecutor 求值，空条件条目适用当前会话执行器。

命令标识中的点对应连字符，例如 speckit.git.commit 对应 speckit-git-commit。`optional: false` 的完成凭证包含 `EXECUTE_COMMAND: {command}` 及真实命令结果；`optional: true` 的报告包含命令、描述和用户提示，执行资格依据用户选择。扩展结果与主产物共同组成完成报告。

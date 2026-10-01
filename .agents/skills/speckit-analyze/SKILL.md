---
name: "speckit-analyze"
description: "规格、计划和任务的一致性分析结果"
compatibility: "适用于具有 .specify/ 目录的 Spec Kit 项目"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/analyze.md"
---

# 规格、计划和任务的一致性分析结果

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

会话报告 `Specification Analysis Report` 包含以下结果：

| ID | Category | Severity | Location(s) | Summary | Recommendation |
| --- | --- | --- | --- | --- | --- |
| [稳定编号] | [需求类别] | [优先级] | [文件与行号] | [证据结论] | [目标结果] |

覆盖表包含 Requirement Key、Has Task、Task IDs 和 Notes。指标包含需求数、任务数、覆盖率、措辞明确度、重复项数量和 CRITICAL 数量。每个结论对应明确文档位置，报告最多呈现 50 项并提供汇总数量。

## 分析边界

spec.md、plan.md、tasks.md 与宪章是只读输入，报告写入范围为会话。需求与任务的映射、术语、实体、授权、验收标准及依赖具有一致性证据。

CRITICAL 对应宪章必需条款、核心产物及 P1 基础覆盖；HIGH 对应核心语义和可验收性；MEDIUM 对应次要覆盖及术语；LOW 对应表达质量。宪章修订属于独立明确授权范围，改稿范围由用户明确请求确定。

## 扩展结果契约

扩展定义来源为 `.specify/extensions.yml`，作用点为 `hooks.before_analyze` 与 `hooks.after_analyze`。有效 YAML 的已启用条目具有执行资格，enabled 默认值为 true。带 condition 的条目由 HookExecutor 求值，空条件条目适用当前会话执行器。

命令标识中的点对应连字符，例如 speckit.git.commit 对应 speckit-git-commit。`optional: false` 的完成凭证包含 `EXECUTE_COMMAND: {command}` 及真实命令结果；`optional: true` 的报告包含命令、描述和用户提示，执行资格依据用户选择。扩展结果与主产物共同组成完成报告。

---
name: "speckit-clarify"
description: "具有用户答案及一致验收语义的功能规格"
compatibility: "适用于具有 .specify/ 目录的 Spec Kit 项目"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/clarify.md"
---

# 具有用户答案及一致验收语义的功能规格

## User Input

```text
$ARGUMENTS
```

当前用户目标和已有授权是产物范围的依据。

## 上下文入口

```powershell
.specify/scripts/powershell/check-prerequisites.ps1 -Json -PathsOnly
```

上下文结果包含适用的 FEATURE_DIR、AVAILABLE_DOCS、模板内容和实际分支。路径采用绝对定位，文档引用采用相对路径。项目宪章提供适用原则，完整输入对应可交付产物。

## 产物

更新后的 spec.md 具有 `## Clarifications` 和 `### Session YYYY-MM-DD`，每条记录格式为 `- Q: <问题> → A: <确认答案>`。答案同时体现于相应需求、实体、边界或成功指标。

术语、数据归属、适用场景、授权、指标和依赖各有明确语义。每次会话最多 5 个高影响问题，每次呈现一个完整问题；选项为 2 至 5 项，简短回答范围为 5 个词以内。问题正文可独立理解，后接一句说明答案对交付的影响。已有答案及可靠上下文是判断依据。

## 质量结果

内置 checklists/requirements.md 的 checkbox 状态反映当前规格质量，状态变更范围为标记字符。原有标题、文字、次序和格式保留。自定义清单归评审者。

交付报告包含已回答数量、规格绝对路径、涉及章节、质量清单前后计数及分类覆盖。答案适用的改稿范围为当前规格。

## 扩展结果契约

扩展定义来源为 `.specify/extensions.yml`，作用点为 `hooks.before_clarify` 与 `hooks.after_clarify`。有效 YAML 的已启用条目具有执行资格，enabled 默认值为 true。带 condition 的条目由 HookExecutor 求值，空条件条目适用当前会话执行器。

命令标识中的点对应连字符，例如 speckit.git.commit 对应 speckit-git-commit。`optional: false` 的完成凭证包含 `EXECUTE_COMMAND: {command}` 及真实命令结果；`optional: true` 的报告包含命令、描述和用户提示，执行资格依据用户选择。扩展结果与主产物共同组成完成报告。

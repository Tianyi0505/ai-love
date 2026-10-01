---
name: "speckit-checklist"
description: "基于功能需求的自定义质量清单"
compatibility: "适用于具有 .specify/ 目录的 Spec Kit 项目"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/checklist.md"
---

# 基于功能需求的自定义质量清单

## User Input

```text
$ARGUMENTS
```

当前用户目标和已有授权是产物范围的依据。

## 上下文入口

```powershell
.specify/scripts/powershell/check-prerequisites.ps1 -Json -Template checklist-template
```

上下文结果包含适用的 FEATURE_DIR、AVAILABLE_DOCS、模板内容和实际分支。路径采用绝对定位，文档引用采用相对路径。项目宪章提供适用原则，完整输入对应可交付产物。

## 产物

FEATURE_DIR/checklists/<主题>.md 采用 checklist-template 结构，包含标题、目的、日期、规格引用、评审归属、分类项目和备注。每项格式为 `- [ ] CHK001 <需求质量标准> [来源]`，新项目使用连续 CHK 编号。

质量标准覆盖完整性、清晰度、一致性、可测量性、范围、依赖、边界及权限。项目表达需求文字的质量，例如“卡片数量与布局具有明确规格”，并对应具体来源。

## 归属与范围

自定义清单的勾选权归评审者，`[x]` 表示需求质量已获确认。生成结果以追加方式保留已有文字、编号与状态；评审协助以评审者明确请求为依据。内置 requirements.md 的维护权归 specify 与 clarify。

澄清范围为会实质改变清单内容的信息，问题最多 3 个。交付报告包含绝对路径、项目总数、主题、来源，以及新建或追加状态。

## 扩展结果契约

扩展定义来源为 `.specify/extensions.yml`，作用点为 `hooks.before_checklist` 与 `hooks.after_checklist`。有效 YAML 的已启用条目具有执行资格，enabled 默认值为 true。带 condition 的条目由 HookExecutor 求值，空条件条目适用当前会话执行器。

命令标识中的点对应连字符，例如 speckit.git.commit 对应 speckit-git-commit。`optional: false` 的完成凭证包含 `EXECUTE_COMMAND: {command}` 及真实命令结果；`optional: true` 的报告包含命令、描述和用户提示，执行资格依据用户选择。扩展结果与主产物共同组成完成报告。

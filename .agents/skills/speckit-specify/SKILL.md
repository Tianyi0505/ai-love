---
name: "speckit-specify"
description: "来自自然语言目标的可验收功能规格"
compatibility: "适用于具有 .specify/ 目录的 Spec Kit 项目"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/specify.md"
---

# 来自自然语言目标的可验收功能规格

## User Input

```text
$ARGUMENTS
```

当前用户目标和已有授权是产物范围的依据。

## 上下文入口

```powershell
.specify/scripts/powershell/resolve-template.ps1 spec-template -Json
```

上下文结果包含适用的 FEATURE_DIR、AVAILABLE_DOCS、模板内容和实际分支。路径采用绝对定位，文档引用采用相对路径。项目宪章提供适用原则，完整输入对应可交付产物。

## 产物

当前用户描述对应 SPECIFY_FEATURE_DIRECTORY/spec.md 和 checklists/requirements.md。规格包含独立用户故事、优先级、Given/When/Then、FR、实体、SC 及假设，正文以正向适用条件和可观察结果表达。

## 目录与元数据

SPECIFY_FEATURE_DIRECTORY 优先采用用户显式路径；默认目录为 specs/<prefix>-<short-name>。short-name 表达 2 至 4 个核心词。prefix 依据 .specify/init-options.json 的 feature_numbering，timestamp 对应 YYYYMMDD-HHMMSS，sequential 对应现有最大编号加 1；branch_numbering 是既有配置的后备字段。

.specify/feature.json 保存实际解析目录。spec-template 的解析结果是规格结构来源，分支创建属于已启用 before_specify 钩子的作用范围；用户显式 GIT_BRANCH_NAME 保持原值。

## 质量标准

规格面向业务利益相关者，功能具有明确条件，成功指标具有环境、样本和阈值。技术细节归 plan，评审清单具有独立文件。

高影响决策的 NEEDS CLARIFICATION 标记最多 3 个，问题具有明确选项。内置 requirements.md 反映规格实际质量，质量核对迭代最多 3 次。完成报告包含目录、规格路径、质量结果及适用下一项产物。

## 扩展结果契约

扩展定义来源为 `.specify/extensions.yml`，作用点为 `hooks.before_specify` 与 `hooks.after_specify`。有效 YAML 的已启用条目具有执行资格，enabled 默认值为 true。带 condition 的条目由 HookExecutor 求值，空条件条目适用当前会话执行器。

命令标识中的点对应连字符，例如 speckit.git.commit 对应 speckit-git-commit。`optional: false` 的完成凭证包含 `EXECUTE_COMMAND: {command}` 及真实命令结果；`optional: true` 的报告包含命令、描述和用户提示，执行资格依据用户选择。扩展结果与主产物共同组成完成报告。

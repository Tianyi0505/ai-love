---
name: "speckit-analyze"
description: "Analyze alignment between a specification, plan, and tasks."
compatibility: "Use in a Spec Kit project with a .specify directory."
metadata:
  author: "github-spec-kit"
  source: "templates/commands/analyze.md"
---

# Specification Analysis

## User Input

\`\`\`text
$ARGUMENTS
\`\`\`

Use the current user goal and granted authority as the work boundary.

## Context

\`\`\`powershell
.specify/scripts/powershell/check-prerequisites.ps1 -Json -RequireSpec -RequireTasks -IncludeTasks
\`\`\`

Use FEATURE_DIR, AVAILABLE_DOCS, template data, and the active branch. Use absolute paths for file operations. Use project-relative paths in documents. Use the constitution as the governing source.

## Result

Create a session-only Specification Analysis Report. Include this table:

| ID | Category | Severity | Location(s) | Summary | Recommendation |
| --- | --- | --- | --- | --- | --- |
| [stable ID] | [requirement category] | [priority] | [file and line] | [evidence] | [target result] |

Include a coverage table with Requirement Key, Has Task, Task IDs, and Notes. Report requirement count, task count, coverage, clarity, duplicate count, and CRITICAL count. Link every finding to a document location. Present up to 50 findings and a total.

## Scope

Read spec.md, plan.md, tasks.md, and the constitution. Map requirements to tasks. Check terms, entities, authority, acceptance criteria, and dependencies.

Use CRITICAL for a required constitution rule, core output, or P1 foundation. Use HIGH for core meaning and acceptance. Use MEDIUM for secondary coverage and terminology. Use LOW for writing quality.

## Extension Contract

Read extensions from \`.specify/extensions.yml\`. Run enabled hooks at \`hooks.before_analyze\` and \`hooks.after_analyze\`. Evaluate condition with HookExecutor. Use every hook with an empty condition.

Map a dotted command ID to a hyphenated command name. Report the executed command and its actual result for a required action. Report the command, description, and user choice for an optional action.

---
name: "speckit-implement"
description: "Deliver implementation and acceptance results for defined tasks."
compatibility: "Use in a Spec Kit project with a .specify directory."
metadata:
  author: "github-spec-kit"
  source: "templates/commands/implement.md"
---

# Task Implementation

## User Input

\`\`\`text
$ARGUMENTS
\`\`\`

Use the current user goal and granted authority as the work boundary.

## Context

\`\`\`powershell
.specify/scripts/powershell/check-prerequisites.ps1 -Json -RequireTasks -IncludeTasks
\`\`\`

Use FEATURE_DIR, AVAILABLE_DOCS, template data, and the active branch. Use the constitution as the governing source.

## Result

Deliver the code, configuration, and documentation named by tasks.md. Use \`[x]\` for a task with implementation and applicable acceptance evidence. Use \`[ ]\` for a target result. Order tasks by dependency. Work on independent files in parallel.

Use spec.md, plan.md, tasks.md, applicable research.md, data-model.md, contracts, and the constitution as input. Respect user authority and existing workspace ownership.

## Quality Result

Read checklist state. Report Total, Checked, Open, and Status for each checklist. A reviewer owns custom checklist markers. Specify and clarify own requirements.md markers.

Every delivered result includes usable code, required configuration, applicable checks, and actual status. State the test environment, boundary doubles, tested scope, and target.

Report the completed task count, main changes, acceptance evidence, and the next deliverable.

## Extension Contract

Read extensions from \`.specify/extensions.yml\`. Run enabled hooks at \`hooks.before_implement\` and \`hooks.after_implement\`. Evaluate condition with HookExecutor. Use every hook with an empty condition.

Map a dotted command ID to a hyphenated command name. Report the executed command and its actual result for a required action. Report the command, description, and user choice for an optional action.

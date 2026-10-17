---
name: "speckit-converge"
description: "Map the current implementation to feature goals."
compatibility: "Use in a Spec Kit project with a .specify directory."
metadata:
  author: "github-spec-kit"
  source: "templates/commands/converge.md"
---

# Implementation Convergence

## User Input

\`\`\`text
$ARGUMENTS
\`\`\`

Use the current user goal and granted authority as the work boundary.

## Context

\`\`\`powershell
.specify/scripts/powershell/check-prerequisites.ps1 -Json -RequireSpec -RequireTasks -IncludeTasks
\`\`\`

Use FEATURE_DIR, AVAILABLE_DOCS, template data, and the active branch. Use the constitution as the governing source.

## Result

Create a convergence report. Include Finding ID, Source, Evidence, Severity, Gap Type, and Target Result. Use FRs, SCs, user stories, plan decisions, applicable constitution rules, and source paths as evidence.

Use gap types \`missing\`, \`partial\`, \`contradicts\`, and \`unrequested\`. Use CRITICAL, HIGH, MEDIUM, and LOW severity. Use CRITICAL for a required constitution rule or a P1 foundation.

## Task Update

Use tasks.md after implementation work has started. Append \`## Phase N: Convergence\`. Preserve existing task text, identifiers, order, and status.

Set N to the existing maximum phase plus one. Start at the next T identifier. Give each task \`[ ]\`, a source, a file path, and a positive target result. Match task priority to report evidence.

Report \`tasks_appended\` with the phase, task count, and implementation entry. Report \`converged\` when every current goal has implementation evidence.

## Extension Contract

Read extensions from \`.specify/extensions.yml\`. Run enabled hooks at \`hooks.before_converge\` and \`hooks.after_converge\`. Evaluate condition with HookExecutor. Use every hook with an empty condition.

Map a dotted command ID to a hyphenated command name. Report the executed command and its actual result for a required action. Report the command, description, and user choice for an optional action.

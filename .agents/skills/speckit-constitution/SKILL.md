---
name: "speckit-constitution"
description: "Maintain the project constitution."
compatibility: "Use in a Spec Kit project with a .specify directory."
metadata:
  author: "github-spec-kit"
  source: "templates/commands/constitution.md"
---

# Project Constitution

## User Input

\`\`\`text
$ARGUMENTS
\`\`\`

Use the current user goal and granted authority as the work boundary.

## Context

\`\`\`powershell
.specify/scripts/powershell/resolve-template.ps1 constitution-template -Json
\`\`\`

Use the resolved template, project documents, and active branch.

## Result

Update \`.specify/memory/constitution.md\` from constitution-template. Keep the project principles, operating rules, governance rules, version, and current date.

Use an HTML comment at the top for the impact report. State the version change, affected principles, affected sections, and dependent material. Use a major version for a principle change, a minor version for a new principle, and a patch version for a meaning clarification. Keep the original ratification date. Set the amendment date to the current update.

## Scope

Write the constitution only. Describe each principle with an applicable condition and an observable result. Describe each exception with scope, reason, exit condition, and accountable owner.

Report the version, change basis, impact report, and a conventional-commit suggestion.

## Extension Contract

Read extensions from \`.specify/extensions.yml\`. Run enabled hooks at \`hooks.before_constitution\` and \`hooks.after_constitution\`. Evaluate condition with HookExecutor. Use every hook with an empty condition.

Map a dotted command ID to a hyphenated command name. Report the executed command and its actual result for a required action. Report the command, description, and user choice for an optional action.

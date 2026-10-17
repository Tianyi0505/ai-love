---
name: "speckit-plan"
description: "Create design artifacts for feature implementation."
compatibility: "Use in a Spec Kit project with a .specify directory."
metadata:
  author: "github-spec-kit"
  source: "templates/commands/plan.md"
---

# Feature Plan

## User Input

\`\`\`text
$ARGUMENTS
\`\`\`

Use the current user goal and granted authority as the work boundary.

## Context

\`\`\`powershell
.specify/scripts/powershell/setup-plan.ps1 -Json
\`\`\`

Use FEATURE_DIR, AVAILABLE_DOCS, template data, and the active branch. Use the constitution as the governing source.

## Result

Create these design artifacts:

| File | Result |
| --- | --- |
| plan.md | Summary, technical context, constitution check, source layout, and design value. |
| research.md | Decision, reason, and applicable evidence. |
| data-model.md | Entity, field, relation, uniqueness, and state meaning. |
| contracts/ | Current external input, output, authority, and result. |
| quickstart.md | Environment, start entry, and end-to-end acceptance result. |

Use the current specification and constitution as sources. Give each technical choice a reason. Match data and authority ownership to the user goal. Create an interface contract when the feature exposes an interface.

## Delivery Scope

Use actionable technical choices and complete artifacts as the design result. Use quickstart for the runtime and acceptance entry. Use absolute paths for file operations. Use project-relative paths in documents.

Report the active Git branch, absolute plan path, created documents, and design-check result.

## Extension Contract

Read extensions from \`.specify/extensions.yml\`. Run enabled hooks at \`hooks.before_plan\` and \`hooks.after_plan\`. Evaluate condition with HookExecutor. Use every hook with an empty condition.

Map a dotted command ID to a hyphenated command name. Report the executed command and its actual result for a required action. Report the command, description, and user choice for an optional action.

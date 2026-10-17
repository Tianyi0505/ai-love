---
name: "speckit-clarify"
description: "Clarify a feature specification and its acceptance meaning."
compatibility: "Use in a Spec Kit project with a .specify directory."
metadata:
  author: "github-spec-kit"
  source: "templates/commands/clarify.md"
---

# Specification Clarification

## User Input

\`\`\`text
$ARGUMENTS
\`\`\`

Use the current user goal and granted authority as the work boundary.

## Context

\`\`\`powershell
.specify/scripts/powershell/check-prerequisites.ps1 -Json -PathsOnly
\`\`\`

Use FEATURE_DIR, AVAILABLE_DOCS, template data, and the active branch. Use absolute paths for file operations. Use project-relative paths in documents.

## Result

Update spec.md with \`## Clarifications\` and \`### Session YYYY-MM-DD\`. Record each answer as \`- Q: <question> → A: <confirmed answer>\`. Apply the answer to the matching requirement, entity, boundary, or success criterion.

Give each term, data owner, scene, authority, metric, and dependency one clear meaning. Ask up to five high-impact questions in one session. Present one complete question at a time. Provide two to five options. Keep a short answer within five words. State the delivery effect after each question.

## Quality Result

Update the marker state in \`checklists/requirements.md\` to match the current specification quality. Preserve headings, text, order, and format. The reviewer owns custom checklists.

Report answer count, the absolute specification path, changed sections, checklist counts, and category coverage.

## Extension Contract

Read extensions from \`.specify/extensions.yml\`. Run enabled hooks at \`hooks.before_clarify\` and \`hooks.after_clarify\`. Evaluate condition with HookExecutor. Use every hook with an empty condition.

Map a dotted command ID to a hyphenated command name. Report the executed command and its actual result for a required action. Report the command, description, and user choice for an optional action.

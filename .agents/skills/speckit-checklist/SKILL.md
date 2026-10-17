---
name: "speckit-checklist"
description: "Create a requirement-quality checklist."
compatibility: "Use in a Spec Kit project with a .specify directory."
metadata:
  author: "github-spec-kit"
  source: "templates/commands/checklist.md"
---

# Requirement Checklist

## User Input

\`\`\`text
$ARGUMENTS
\`\`\`

Use the current user goal and granted authority as the work boundary.

## Context

\`\`\`powershell
.specify/scripts/powershell/check-prerequisites.ps1 -Json -Template checklist-template
\`\`\`

Use FEATURE_DIR, AVAILABLE_DOCS, template data, and the active branch. Use absolute paths for file operations. Use project-relative paths in documents.

## Result

Create \`FEATURE_DIR/checklists/<topic>.md\` from checklist-template. Include a title, purpose, date, specification reference, review owner, categories, and notes.

Use \`- [ ] CHK001 <quality criterion> [source]\` for each item. Use consecutive CHK identifiers. Cover completeness, clarity, consistency, measurability, scope, dependencies, boundaries, and authority. Link each item to a source requirement.

## Ownership

The reviewer owns each custom checklist marker. \`[x]\` records a confirmed requirement-quality result. Preserve existing text, identifiers, and marker state. Specify and clarify own the generated requirements.md checklist.

Ask up to three questions when information changes a checklist result. Report the absolute path, item count, topic, sources, and created or appended result.

## Extension Contract

Read extensions from \`.specify/extensions.yml\`. Run enabled hooks at \`hooks.before_checklist\` and \`hooks.after_checklist\`. Evaluate condition with HookExecutor. Use every hook with an empty condition.

Map a dotted command ID to a hyphenated command name. Report the executed command and its actual result for a required action. Report the command, description, and user choice for an optional action.

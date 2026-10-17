---
name: "speckit-taskstoissues"
description: "Create GitHub issues that match delivery tasks."
compatibility: "Use in a Spec Kit project with a .specify directory."
metadata:
  author: "github-spec-kit"
  source: "templates/commands/taskstoissues.md"
---

# Tasks to GitHub Issues

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

Read the target repository from \`remote.origin.url\`. Read \`FEATURE_DIR/tasks.md\`. Create an issue title as \`T001: <positive delivery result>\`. Include requirement sources, file paths, prerequisites, and acceptance criteria in the issue body.

Use \`\\bT\\d{3,}\\b\` to identify task IDs. Search open and closed issues for every ID. Use \`state=all\`, \`perPage=100\`, and the returned \`endCursor\` for paging. Associate an existing issue with its task ID. Create an issue for each authorized task with a unique ID.

Report the target repository, task IDs, existing links, created links, and counts. Use external write authority only for a user-requested tasks-to-issues operation.

## Extension Contract

Read extensions from \`.specify/extensions.yml\`. Run enabled hooks at \`hooks.before_taskstoissues\` and \`hooks.after_taskstoissues\`. Evaluate condition with HookExecutor. Use every hook with an empty condition.

Map a dotted command ID to a hyphenated command name. Report the executed command and its actual result for a required action. Report the command, description, and user choice for an optional action.

---
name: "speckit-tasks"
description: "Create delivery tasks from dependencies and user stories."
compatibility: "Use in a Spec Kit project with a .specify directory."
metadata:
  author: "github-spec-kit"
  source: "templates/commands/tasks.md"
---

# Delivery Tasks

## User Input

\`\`\`text
$ARGUMENTS
\`\`\`

Use the current user goal and granted authority as the work boundary.

## Context

\`\`\`powershell
.specify/scripts/powershell/setup-tasks.ps1 -Json
\`\`\`

Use FEATURE_DIR, AVAILABLE_DOCS, template data, and the active branch. Use the constitution as the governing source.

## Result

Create \`FEATURE_DIR/tasks.md\` from TASKS_TEMPLATE_CONTENT. Use spec.md, plan.md, and applicable design artifacts. Group tasks by user story and priority. Give each story an independent observable result and acceptance condition.

Use \`- [ ] T001 [P] [US1] <file path> Deliver <result>\`. Use consecutive T identifiers. Use a story label for story tasks. Use \`[P]\` for independent files after prerequisite results exist. Give each task a specific acceptance result and an explicit dependency.

## Quality Result

Use test tasks for feature requirements and user-requested validation. Group setup, shared foundation, user stories, and delivery work by result. Match every path to the design structure. Use \`[ ]\` for a target and \`[x]\` for delivered evidence.

Report the absolute path, task count, story counts, dependencies, independent work, minimum delivery slice, and format-check result.

## Extension Contract

Read extensions from \`.specify/extensions.yml\`. Run enabled hooks at \`hooks.before_tasks\` and \`hooks.after_tasks\`. Evaluate condition with HookExecutor. Use every hook with an empty condition.

Map a dotted command ID to a hyphenated command name. Report the executed command and its actual result for a required action. Report the command, description, and user choice for an optional action.

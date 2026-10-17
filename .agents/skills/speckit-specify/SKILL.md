---
name: "speckit-specify"
description: "Create an accepted feature specification from a user goal."
compatibility: "Use in a Spec Kit project with a .specify directory."
metadata:
  author: "github-spec-kit"
  source: "templates/commands/specify.md"
---

# Feature Specification

## User Input

\`\`\`text
$ARGUMENTS
\`\`\`

Use the current user goal and granted authority as the work boundary.

## Context

\`\`\`powershell
.specify/scripts/powershell/resolve-template.ps1 spec-template -Json
\`\`\`

Use FEATURE_DIR, AVAILABLE_DOCS, template data, and the active branch. Use the constitution as the governing source.

## Result

Create \`SPECIFY_FEATURE_DIRECTORY/spec.md\` and \`checklists/requirements.md\`. Include independent user stories, priority, Given/When/Then scenarios, functional requirements, entities, success criteria, and assumptions. Use applicable conditions and observable results.

## Directory and Metadata

Use an explicit user path when provided. Otherwise use \`specs/<prefix>-<short-name>\`. Use two to four core words for short-name. Read feature numbering from \`.specify/init-options.json\`. Use the current timestamp for timestamp numbering. Use the next number for sequential numbering.

Write the resolved directory to \`.specify/feature.json\`. Use the resolved spec template as the specification structure. Preserve an explicit \`GIT_BRANCH_NAME\`.

## Quality Result

Write for business stakeholders. Give each function a clear condition. Give each success criterion an environment, sample, and threshold. Keep design detail in plan. Keep review items in a separate checklist.

Use up to three NEEDS CLARIFICATION markers for high-impact decisions. Give each marker clear options. Update requirements.md to match the specification quality. Report the directory, specification path, quality result, and next artifact.

## Extension Contract

Read extensions from \`.specify/extensions.yml\`. Run enabled hooks at \`hooks.before_specify\` and \`hooks.after_specify\`. Evaluate condition with HookExecutor. Use every hook with an empty condition.

Map a dotted command ID to a hyphenated command name. Report the executed command and its actual result for a required action. Report the command, description, and user choice for an optional action.

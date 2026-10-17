---
description: "Template for delivery tasks organized by user story."
---

# Tasks: [FEATURE NAME]

**Input**: Design documents in \`/specs/[###-feature-name]/\`.
**Prerequisites**: plan.md, spec.md, and applicable research.md, data-model.md, and contracts/.
**Tests**: Acceptance tasks match feature requirements and the user validation scope.
**Organization**: Each user story has an independent result, path, and acceptance evidence.

## Format: \`[ID] [P?] [Story] Description\`

Use \`- [ ] T001 [P] [US1] <file path> Deliver <accepted result>\`. Use consecutive identifiers. Use a story label for a story task. Use \`[P]\` when prerequisite results enable independent file work. Use \`[ ]\` for a target result. Use \`[x]\` for delivered evidence.

## Phase 1: Setup

- [ ] T001 [project path] Deliver the package structure and dependencies from the design.
- [ ] T002 [environment path] Deliver an independent validation environment and configuration.

## Phase 2: Foundation

- [ ] T003 [contract path] Deliver shared input and output contracts.
- [ ] T004 [storage path] Deliver stable identity, data ownership, and state results.

## Phase 3: User Story 1 - [Title] (Priority: P1)

**Goal**: [Observable user result.]
**Independent Test**: [Entry, environment, sample, and pass condition.]

- [ ] T005 [US1] [implementation path] Deliver [result].
- [ ] T006 [US1] [acceptance path] Deliver real-entry evidence for [result].

## Phase 4: User Story 2 - [Title] (Priority: P2)

**Goal**: [Observable user result.]
**Independent Test**: [Independent acceptance result.]

- [ ] T007 [US2] [implementation path] Deliver [result].
- [ ] T008 [US2] [acceptance path] Deliver entry evidence for [result].

## Phase 5: Delivery

- [ ] T009 [documentation path] Describe the delivered capability, environment, and data state.
- [ ] T010 [acceptance path] Report feature metrics, resource results, and recovery evidence.

## Dependencies

| Result set | Prerequisite result | Independent scope |
| --- | --- | --- |
| [user story] | [task identifier] | [file and state boundary] |

## Requirement Coverage

| Requirement | Delivery Task | Acceptance Evidence |
| --- | --- | --- |
| FR-001 / SC-001 | [task identifier] | [path and result] |

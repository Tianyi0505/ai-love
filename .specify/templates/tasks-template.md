---
description: "按用户故事组织的交付结果清单模板"
---

# Tasks: [FEATURE NAME]

**Input**: `/specs/[###-feature-name]/` 的设计文档。
**Prerequisites**: plan.md、spec.md，以及适用的 research.md、data-model.md 和 contracts/。
**Tests**: 验收项目对应用户要求及功能规格的明确验证范围。
**Organization**: 每个用户故事具有独立结果、路径和验收证据。

## Format: `[ID] [P?] [Story] Description`

任务格式为 `- [ ] T001 [P] [US1] <具体文件路径> 提供 <可验收结果>`。编号连续，故事标签对应规格，`[P]` 表示依赖满足后文件互相独立的任务。`[ ]` 表示目标结果，`[x]` 表示已有完成证据。

## Phase 1: Setup

- [ ] T001 [项目路径] 具备设计规定的包结构和依赖。
- [ ] T002 [环境路径] 提供独立验证环境和配置。

## Phase 2: Foundational

- [ ] T003 [契约路径] 定义各用户故事共同使用的输入输出。
- [ ] T004 [持久层路径] 提供稳定身份、数据归属和状态结果。

## Phase 3: User Story 1 - [Title] (Priority: P1)

**Goal**: [用户可观察结果。]
**Independent Test**: [入口、环境、样本与通过标准。]

- [ ] T005 [US1] [实现路径] 提供 [结果]。
- [ ] T006 [US1] [验收路径] 具有 [结果] 的真实入口证据。

## Phase 4: User Story 2 - [Title] (Priority: P2)

**Goal**: [用户可观察结果。]
**Independent Test**: [独立验收结果。]

- [ ] T007 [US2] [实现路径] 提供 [结果]。
- [ ] T008 [US2] [验收路径] 具有 [结果] 的入口证据。

## Phase 5: Delivery

- [ ] T009 [文档路径] 准确表达实际交付能力、环境和数据。
- [ ] T010 [验收路径] 汇总功能指标、资源结果及恢复证据。

## Dependencies

| 结果集合 | 前置结果 | 独立范围 |
| --- | --- | --- |
| [用户故事] | [任务编号] | [文件与状态范围] |

## Requirement Coverage

| 需求 | 交付任务 | 验收证据 |
| --- | --- | --- |
| FR-001 / SC-001 | [任务编号] | [路径与结果] |

# [CHECKLIST TYPE] Checklist: [FEATURE NAME]

**Purpose**: [需求质量范围]
**Created**: [DATE]
**Feature**: [规格链接]
**Review Ownership**: 自定义清单的评审者拥有勾选状态。
**Marker Semantics**: `[x]` 表示评审确认需求质量标准已满足；实现状态由 tasks.md 和验收证据表达。

## [Category 1]

- [ ] CHK001 [需求具有明确适用条件和可观察结果。]
- [ ] CHK002 [验收指标包含环境、样本和阈值。]
- [ ] CHK003 [数据归属、权限及状态范围表达一致。]

## [Category 2]

- [ ] CHK004 [边界场景具有确定结果。]
- [ ] CHK005 [依赖及假设具有资料依据。]
- [ ] CHK006 [每项需求具有来源引用。]

## Notes

新生成项目使用 `[ ]`，已有项目与评审状态保留。CHK 编号连续。`speckit-implement` 对清单的权限为状态读取；`checklists/requirements.md` 的规格质量状态由 `speckit-specify` 和 `speckit-clarify` 维护。

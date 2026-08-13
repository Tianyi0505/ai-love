from __future__ import annotations


PERSON_SECTIONS = (
    "基本信息",
    "当前关注",
    "稳定偏好",
    "交流偏好",
    "重要经历",
    "关系认知",
    "未完成事项",
    "不确定信息",
)
SELF_SECTIONS = (
    "核心身份",
    "当前关注",
    "稳定偏好",
    "交流方式",
    "重要经历",
    "行为原则",
    "未完成事项",
    "不确定信息",
)


def normalize_markdown(owner_type: str, markdown: str) -> str:
    sections = PERSON_SECTIONS if owner_type == "person" else SELF_SECTIONS
    title = "联系人长期认知" if owner_type == "person" else "自我长期认知"
    content: dict[str, list[str]] = {section: [] for section in sections}
    current = "不确定信息"
    text = markdown.replace("```markdown", "").replace("```md", "").replace("```", "")
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            heading = line[3:].strip()
            current = heading if heading in content else "不确定信息"
            continue
        if line.startswith("# "):
            continue
        if line.strip():
            content[current].append(line)
    output = [f"# {title}"]
    for section in sections:
        lines = content[section]
        if not lines:
            continue
        output.extend(("", f"## {section}", "", *lines))
    return "\n".join(output).strip()

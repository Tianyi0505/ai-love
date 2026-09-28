from __future__ import annotations

from typing import TYPE_CHECKING

from markdown_it import MarkdownIt

from memory.memory_generation_output import (
    MemoryConsolidationOutput,
    MemoryExtractionOutput,
    MemoryOwnerType,
)
from shared.global_settings import MemoryDocumentSchemas, MemoryOutputLimits

if TYPE_CHECKING:
    from memory.episode_memory_repository import EpisodeMessage


class MemoryOutputPolicy:
    def __init__(self, limits: MemoryOutputLimits) -> None:
        self._limits = limits

    def validate_extraction(
        self,
        output: MemoryExtractionOutput,
    ) -> MemoryExtractionOutput:
        limits = self._limits
        if not (limits.episode_summary_min_chars <= len(output.episode_summary) <= limits.episode_summary_max_chars):
            raise ValueError("片段摘要长度不符合配置")
        if len(output.memories) > limits.memories_max_count:
            raise ValueError("片段记忆数量不符合配置")
        for memory in output.memories:
            if not (limits.memory_content_min_chars <= len(memory.content) <= limits.memory_content_max_chars):
                raise ValueError("记忆内容长度不符合配置")
            if not limits.importance_min <= memory.importance <= limits.importance_max:
                raise ValueError("记忆重要性不符合配置")
            if not limits.confidence_min <= memory.confidence <= limits.confidence_max:
                raise ValueError("记忆置信度不符合配置")
        return output

    def ground_extraction(
        self, output: MemoryExtractionOutput, messages: list[EpisodeMessage]
    ) -> MemoryExtractionOutput:
        roles = {message.message_id: message.role for message in messages}
        memories = []
        for memory in output.memories:
            if any(message_id not in roles for message_id in memory.source_message_ids):
                raise ValueError("记忆引用了本片段之外的消息")
            evidence_roles = {roles[message_id] for message_id in memory.source_message_ids}
            if memory.owner_type == "self" and not {"user", "assistant"}.issubset(evidence_roles):
                continue
            memories.append(memory)
        return output.model_copy(update={"memories": memories})

    def validate_consolidation(
        self,
        output: MemoryConsolidationOutput,
    ) -> MemoryConsolidationOutput:
        if not (self._limits.markdown_min_chars <= len(output.markdown) <= self._limits.markdown_max_chars):
            raise ValueError("长期记忆文档长度不符合配置")
        return output


class MemoryDocumentPolicy:
    def __init__(self, schemas: MemoryDocumentSchemas) -> None:
        self._schemas = schemas
        self._markdown = MarkdownIt()

    def empty_document(self, owner_type: MemoryOwnerType) -> str:
        return getattr(self._schemas, owner_type).empty_document

    def anchor_identity(self, markdown: str, persona: str) -> str:
        schema = self._schemas.self
        section = schema.identity_section
        if section is None:
            raise ValueError("自我认知文档必须配置固定身份章节")
        self.validate("self", markdown)
        tokens = self._markdown.parse(markdown)
        headings = [token for token in tokens if token.type == "heading_open"]
        lines = markdown.splitlines()
        removed: set[int] = set()
        for index, token in enumerate(tokens):
            if token.type == "heading_open" and token.tag == "h2" and tokens[index + 1].content == section:
                start = token.map[0]
                stop = next((heading.map[0] for heading in headings if heading.map[0] > start), len(lines))
                removed.update(range(start, stop))
        title_end = headings[0].map[1]
        body = "\n".join(line for index, line in enumerate(lines) if index >= title_end and index not in removed).strip()
        result = f"# {schema.title}\n\n## {section}\n{persona.strip()}"
        return self.validate("self", result + ("\n\n" + body if body else ""))

    def validate(self, owner_type: MemoryOwnerType, markdown: str) -> str:
        schema = getattr(self._schemas, owner_type)
        tokens = self._markdown.parse(markdown)
        headings = [
            (token.tag, tokens[index + 1].content) for index, token in enumerate(tokens) if token.type == "heading_open"
        ]
        if not headings or headings[0] != ("h1", schema.title):
            raise ValueError("长期记忆文档一级标题不符合配置")
        if any(tag not in {"h1", "h2"} for tag, _ in headings):
            raise ValueError("长期记忆文档只允许一级和二级标题")
        if any(title not in schema.sections for tag, title in headings[1:] if tag == "h2"):
            raise ValueError("长期记忆文档包含未配置的二级标题")
        if any(tag == "h1" for tag, _ in headings[1:]):
            raise ValueError("长期记忆文档只能包含一个一级标题")
        return markdown.strip()

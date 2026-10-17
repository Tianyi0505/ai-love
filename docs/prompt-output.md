# Prompt and Structured Output

## Persona prompt

An AI definition combines a shared default with an AI-specific override. The definition contains identity, personality, relationship policy, social behavior, model selection, tool grants, and prompt templates.

The system prompt presents the identity, expression style, approved facts, scene rules, context labels, and output protocol. The user prompt presents current input, conversation history, retrieved context, and source data.

## Memory prompt

The memory pipeline records activity, groups quiet activity into episodes, extracts source-backed atoms, and consolidates long-term Markdown documents.

| Owner | Document purpose |
| --- | --- |
| person | Stable facts, interests, preferences, significant events, relationship context, and active commitments for one contact. |
| self | Persona-aligned preferences, digital experiences, behavior principles, and active commitments for one AI. |

Each memory atom contains an owner type, memory type, content, importance, confidence, and supporting message identifiers.

## Structured output tools

| Tool | Result |
| --- | --- |
| submit_response_plan | Speech segments, emotion, and sticker actions. |
| submit_participation_decision | A group participation decision and reason. |
| submit_repeat_decision | A repeat decision and reason. |
| submit_image_description | Image type, visible content, tags, emotion, and sticker quality. |
| submit_sticker_decision | Image type, sticker suitability, and reason. |
| submit_memory_extraction | Episode summary and source-backed memory atoms. |
| submit_memory_document | A consolidated long-term Markdown document. |

The tool schema validates every field before the runtime stores or delivers the result.

from __future__ import annotations

from shared.contracts.entity import EntityCandidate, EntityContext, EntityReference
from shared.contracts.rpc.grounding import ResolvePeopleResponse
from shared.contracts.tools import ToolExecutionContext
from shared.conversation_context_repository import ConversationContextRepository
from shared.global_settings import GroundingSettings
from shared.group_member_repository import GroupMemberRepository
from shared.person_resolver import PersonResolver


class EntityGrounder:
    def __init__(
        self,
        resolver: PersonResolver,
        group_members: GroupMemberRepository,
        conversations: ConversationContextRepository,
        settings: GroundingSettings,
    ) -> None:
        self._resolver = resolver
        self._group_members = group_members
        self._conversations = conversations
        self._settings = settings

    async def ground(
        self,
        context: ToolExecutionContext,
        message,
        recent_participants_limit: int,
        recent_lookback_sec: float,
    ) -> EntityContext:
        sender = (
            {
                "person_id": context.sender_person_id,
                "display_name": message.sender.name or message.sender.user_id,
            }
            if context.sender_person_id
            else {}
        )
        references: list[EntityReference] = []
        seen = {context.sender_person_id}

        for target in message.meta.get("at_user_ids", []):
            if message.to_ai and str(target) == message.at_user_id:
                continue
            result = await self._resolver.resolve(context, str(target), self._settings.at_candidate_limit)
            references.append(self._reference(f"@{target}", "explicit_at", result))
            for candidate in result.candidates[: self._settings.primary_candidate_limit]:
                seen.add(candidate.person_id)

        if message.quote_ref and message.quote_ref.sender.user_id:
            result = await self._resolver.resolve(
                context,
                message.quote_ref.sender.user_id,
                self._settings.quote_candidate_limit,
            )
            references.append(self._reference("引用消息发送者", "reply_to", result))

        matched_roles: list[str] = []
        for role_name in sorted(self._settings.role_names, key=len, reverse=True):
            if role_name not in message.text or any(role_name in existing for existing in matched_roles):
                continue
            result = await self._resolver.resolve(context, role_name, self._settings.role_candidate_limit)
            references.append(self._reference(role_name, "group_role", result))
            matched_roles.append(role_name)

        matched_names = await self._group_members.names_in_message(context, message.text)
        selected_names: list[str] = []
        for name in sorted(matched_names, key=len, reverse=True):
            if any(name in existing for existing in selected_names):
                continue
            selected_names.append(name)
            person_ids = matched_names[name]
            if len(person_ids) == self._settings.primary_candidate_limit and person_ids[0] not in seen:
                references.append(
                    EntityReference(
                        text=name,
                        status="resolved",
                        person_id=person_ids[0],
                        display_name=name,
                        candidates=(),
                        evidence=({"type": "group_card_match", "name": name},),
                    )
                )
                seen.add(person_ids[0])
            elif len(person_ids) > self._settings.primary_candidate_limit:
                references.append(
                    EntityReference(
                        text=name,
                        status="candidate",
                        person_id="",
                        display_name="",
                        candidates=tuple(
                            EntityCandidate(
                                person_id=person_id,
                                display_name=name,
                                confidence=self._settings.ambiguous_name_confidence,
                                evidence=(),
                            )
                            for person_id in person_ids
                        ),
                        evidence=(),
                    )
                )

        participants = await self._conversations.recent_participants(
            context,
            recent_participants_limit,
            recent_lookback_sec,
        )
        if context.sender_person_id and all(item["person_id"] != context.sender_person_id for item in participants):
            participants = (
                {
                    "person_id": context.sender_person_id,
                    "display_name": message.sender.name,
                    "group_card": "",
                    "roles": [],
                    "last_message_id": "",
                    "last_seen_at": "now",
                },
            ) + participants
        return EntityContext(
            current_sender=sender,
            references=tuple(references),
            recent_participants=participants,
        )

    def _reference(
        self,
        text: str,
        resolution_type: str,
        result: ResolvePeopleResponse,
    ) -> EntityReference:
        candidates = tuple(result.candidates)
        if (
            len(candidates) == self._settings.primary_candidate_limit
            and candidates[0].confidence >= self._settings.resolved_confidence_threshold
        ):
            return EntityReference(
                text=text,
                status="resolved",
                person_id=candidates[0].person_id,
                display_name=candidates[0].display_name,
                candidates=(),
                evidence=({"type": resolution_type},),
            )
        if candidates:
            return EntityReference(
                text=text,
                status="candidate",
                person_id="",
                display_name="",
                candidates=candidates,
                evidence=(),
            )
        return EntityReference(
            text=text,
            status="unresolved",
            person_id="",
            display_name="",
            candidates=(),
            evidence=(),
        )

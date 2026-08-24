from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class QuickEntry(BaseModel):
    key: str
    name: str
    description: str
    url: str


class QuickEntriesResponse(BaseModel):
    entries: list[QuickEntry]


class PersonalityResponse(BaseModel):
    ai_id: str
    name: str
    identity: str
    traits: list[str]
    speaking_style: str
    catchphrases: list[str]
    taboos: list[str]
    version: int
    fingerprint: str


class MemoryDocumentResponse(BaseModel):
    markdown: str
    version: int
    updated_at: datetime


class SelfMemoryResponse(BaseModel):
    ai_id: str
    memory: MemoryDocumentResponse | None


class PersonSummary(BaseModel):
    person_id: str
    display_name: str
    qq: str
    version: int
    updated_at: datetime


class PeopleResponse(BaseModel):
    ai_id: str
    people: list[PersonSummary]


class PersonMemoryResponse(BaseModel):
    ai_id: str
    person: PersonSummary
    memory: MemoryDocumentResponse

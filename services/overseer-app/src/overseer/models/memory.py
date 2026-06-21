from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkingMemoryEntry(BaseModel):
    key: str
    value: Any
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class EpisodicMemory(BaseModel):
    id: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    event_type: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    tickers: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    importance: float = 0.5
    embedding: list[float] | None = None
    trade_id: int | None = None
    outcome: str | None = None
    outcome_details: dict[str, Any] | None = None
    lesson_extracted: bool = False
    linked_principle_id: int | None = None


class LearnedPrinciple(BaseModel):
    id: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    category: str
    principle: str
    confidence: float = 0.5
    evidence_count: int = 1
    source: str = "experience"
    source_episodes: list[int] = Field(default_factory=list)
    contradictions: list[int] = Field(default_factory=list)
    active: bool = True
    version: int = 1
    previous_version_text: str | None = None


class KnowledgeChunk(BaseModel):
    id: int | None = None
    source_file: str
    chunk_index: int
    content: str
    embedding: list[float] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MemorySearchResult(BaseModel):
    content: str
    source: str
    similarity_score: float
    metadata: dict[str, Any] = Field(default_factory=dict)

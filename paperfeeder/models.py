"""
Paper, author, and digest data models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class PaperSource(Enum):
    ARXIV = "arxiv"
    HUGGINGFACE = "huggingface"
    MANUAL = "manual"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    OPENREVIEW = "openreview"


@dataclass
class Author:
    name: str
    affiliation: Optional[str] = None
    email: Optional[str] = None


@dataclass
class Paper:
    title: str
    abstract: str
    url: str
    source: PaperSource

    arxiv_id: Optional[str] = None
    authors: List[Author] = field(default_factory=list)
    published_date: Optional[datetime] = None
    updated_date: Optional[datetime] = None
    categories: List[str] = field(default_factory=list)
    pdf_url: Optional[str] = None

    relevance_score: float = 0.0
    matched_keywords: List[str] = field(default_factory=list)
    filter_reason: Optional[str] = None

    notes: Optional[str] = None
    added_by: Optional[str] = None
    full_text: Optional[str] = None
    research_notes: Optional[str] = None
    semantic_paper_id: Optional[str] = None

    def __hash__(self):
        return hash(self.arxiv_id or self.url)

    def __eq__(self, other):
        if not isinstance(other, Paper):
            return False
        return (self.arxiv_id or self.url) == (other.arxiv_id or other.url)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "abstract": self.abstract,
            "url": self.url,
            "source": self.source.value,
            "arxiv_id": self.arxiv_id,
            "authors": [{"name": a.name, "affiliation": a.affiliation} for a in self.authors],
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "categories": self.categories,
            "pdf_url": self.pdf_url,
            "relevance_score": self.relevance_score,
            "matched_keywords": self.matched_keywords,
            "filter_reason": self.filter_reason,
            "notes": self.notes,
            "research_notes": self.research_notes,
            "semantic_paper_id": self.semantic_paper_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Paper":
        authors = [Author(**a) for a in data.get("authors", [])]
        published_date = None
        if data.get("published_date"):
            published_date = datetime.fromisoformat(data["published_date"])

        return cls(
            title=data["title"],
            abstract=data["abstract"],
            url=data["url"],
            source=PaperSource(data.get("source", "manual")),
            arxiv_id=data.get("arxiv_id"),
            authors=authors,
            published_date=published_date,
            categories=data.get("categories", []),
            pdf_url=data.get("pdf_url"),
            relevance_score=data.get("relevance_score", 0.0),
            matched_keywords=data.get("matched_keywords", []),
            filter_reason=data.get("filter_reason"),
            notes=data.get("notes"),
            research_notes=data.get("research_notes"),
            semantic_paper_id=data.get("semantic_paper_id"),
        )


@dataclass
class DailyReport:
    date: datetime
    papers: List[Paper]
    summary: str
    insights: List[str]
    html_content: str


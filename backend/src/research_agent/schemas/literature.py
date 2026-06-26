from typing import Dict, List

from pydantic import BaseModel, Field


class ArxivPaper(BaseModel):
    arxiv_id: str
    title: str
    authors: List[str] = Field(default_factory=list)
    abstract: str
    published: str
    categories: List[str] = Field(default_factory=list)
    entry_url: str
    pdf_url: str


class RecommendedPaper(BaseModel):
    paper: ArxivPaper
    reason: str
    purpose_labels: List[str] = Field(default_factory=list)


class LiteratureQuery(BaseModel):
    english_query: str


class RecommendationItem(BaseModel):
    arxiv_id: str
    reason: str
    purpose_labels: List[str] = Field(default_factory=list)


class LiteratureDiscoveryResult(BaseModel):
    query: str
    candidates: List[ArxivPaper]
    recommendations: List[RecommendedPaper]
    candidate_summaries: Dict[str, str] = Field(default_factory=dict)

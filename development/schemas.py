from typing import Dict, List, Optional, Any, Literal

from pydantic import BaseModel, Field


class CompanyIntelligenceSchema(BaseModel):
    primary_industry: Optional[str] = None
    sub_industries: List[str] = Field(default_factory=list)
    business_domains: List[str] = Field(default_factory=list)
    products_services: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    business_keywords: List[str] = Field(default_factory=list)
    competitors: List[str] = Field(default_factory=list)
    target_markets: List[str] = Field(default_factory=list)
    relevant_geographies: List[str] = Field(default_factory=list)
    regulatory_domains: List[str] = Field(default_factory=list)


class DevelopmentInsightSchema(BaseModel):
    what_happened: str
    implication: str
    confidence: float = Field(ge=0.0, le=1.0)
    opportunity_type: Literal["tender", "RFP", "RFQ", "EOI", "contract", "procurement", "partnership", "expansion", "investment", "infrastructure", "market_opportunity", "regulatory_opportunity", "none"] = "none"
    opportunity_relevance: Literal["high", "medium", "low", "none"] = "none"
    business_opportunity_score: float = Field(default=0.0, ge=0.0, le=1.0)


class DevelopmentInsightBatchSchema(BaseModel):
    insights: List[DevelopmentInsightSchema]


class GeminiDevelopmentInsightSchema(BaseModel):
    what_happened: str
    implication: str
    opportunity_type: str
    opportunity_relevance: str
    business_opportunity_score: float
    confidence: float


class GeminiDevelopmentInsightBatchSchema(BaseModel):
    insights: List[GeminiDevelopmentInsightSchema]


class CompanyContext(BaseModel):
    id: str
    name: str
    city: Optional[str] = None
    state: Optional[str] = None
    business_category: Optional[str] = None


class DevelopmentItem(BaseModel):
    title: str
    summary: Optional[str] = None
    what_happened: Optional[str] = None
    implication: Optional[str] = None
    source_name: str
    source_url: Optional[str] = None
    published_at: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    category: Optional[str] = "other"
    development_type: str = "domain"
    opportunity_type: str = "none"
    opportunity_relevance: str = "none"
    business_opportunity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    location: Optional[Dict[str, Optional[str]]] = None
    source: Optional[Dict[str, Optional[str]]] = None
    event_type: str = "other"
    relevance: Optional[str] = None
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)


class DevelopmentResponse(BaseModel):
    company: CompanyContext
    company_context: Optional[Dict[str, Any]] = None
    retrieved_at: str
    sources: List[str]
    items: List[DevelopmentItem]

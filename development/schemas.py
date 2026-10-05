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
    candidate_id: str
    relevance: Literal["high", "medium", "low", "none"] = "none"
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    what_happened: str
    impact: Literal["positive", "negative", "neutral", "mixed"] = "neutral"
    opportunity_type: Literal["direct_opportunity", "indirect_opportunity", "market_signal", "competitive_signal", "regulatory_impact", "risk", "none"] = "none"
    opportunity_relevance: Literal["high", "medium", "low", "none"] = "none"
    business_opportunity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    implication: str
    recommended_action: str = ""
    development_type: str = "other"
    confidence: float = Field(ge=0.0, le=1.0)


class DevelopmentInsightBatchSchema(BaseModel):
    insights: List[DevelopmentInsightSchema]


class GeminiDevelopmentInsightSchema(BaseModel):
    candidate_id: str
    relevance: str
    relevance_score: float
    what_happened: str
    impact: str
    opportunity_type: str
    opportunity_relevance: str
    business_opportunity_score: float
    implication: str
    recommended_action: str
    development_type: str
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
    recommended_action: Optional[str] = None
    impact: Optional[str] = None
    confidence: float = 0.0
    source_name: str
    source_url: Optional[str] = None
    original_source: Optional[str] = None
    original_url: Optional[str] = None
    discovery_source: Optional[str] = None
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
    tender_id: Optional[str] = None
    closing_date: Optional[str] = None
    issuing_organization: Optional[str] = None
    sources: Optional[List[Dict[str, Optional[str]]]] = None


class DevelopmentResponse(BaseModel):
    company: CompanyContext
    company_context: Optional[Dict[str, Any]] = None
    retrieved_at: str
    sources: List[str]
    pipeline_metrics: Optional[Dict[str, int]] = None
    items: List[DevelopmentItem]

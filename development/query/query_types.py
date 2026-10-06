from enum import Enum
from typing import TypedDict


class DevelopmentQueryType(str, Enum):
    COMPANY = "company"
    DOMAIN = "domain"
    PRODUCT_SERVICE = "product_service"
    TECHNOLOGY = "technology"
    COMPETITOR = "competitor"
    LOCAL = "local"
    NEARBY = "nearby"
    STATE = "state"
    GOVERNMENT = "government"
    TENDER = "tender"
    RFP = "RFP"
    RFQ = "RFQ"
    EOI = "EOI"
    PROCUREMENT = "procurement"
    OPPORTUNITY = "opportunity"
    INFRASTRUCTURE = "infrastructure"
    INVESTMENT = "investment"
    REGULATORY = "regulatory"
    POLICY = "policy"
    NATIONAL = "national"
    GLOBAL = "global"
    INDUSTRY = "industry"


class DevelopmentQuery(TypedDict):
    query: str
    type: DevelopmentQueryType
    priority: float

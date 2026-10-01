from enum import Enum
from typing import TypedDict


class DevelopmentQueryType(str, Enum):
    COMPANY = "company"
    DOMAIN = "domain"
    TECHNOLOGY = "technology"
    COMPETITOR = "competitor"
    LOCAL = "local"
    NEARBY = "nearby"
    STATE = "state"
    GOVERNMENT = "government"
    TENDER = "tender"
    OPPORTUNITY = "opportunity"
    INFRASTRUCTURE = "infrastructure"
    INVESTMENT = "investment"
    REGULATORY = "regulatory"
    NATIONAL = "national"
    GLOBAL = "global"


class DevelopmentQuery(TypedDict):
    query: str
    type: DevelopmentQueryType
    priority: float

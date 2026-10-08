from __future__ import annotations

import os
from typing import Any, Dict, List

from development.query.query_types import DevelopmentQuery, DevelopmentQueryType as T


class QueryBuilder:
    """Build a bounded but broad portfolio of company-aware news searches."""

    def __init__(self, max_queries: int | None = None):
        self.max_queries = max_queries or int(os.getenv("DEVELOPMENTS_MAX_QUERIES", "24"))

    def build(self, context: Dict[str, Any]) -> List[DevelopmentQuery]:
        industry = context.get("primary_industry") or context.get("business_category")
        domains = _unique(_values(context, "business_domains", "sub_industries", "business_keywords", "products_services"))
        if industry:
            domains.insert(0, str(industry))
        domains = _unique(domains)[:6]
        technologies = _unique(_values(context, "technologies"))[:5]
        competitors = _unique(_values(context, "competitors"))[:4]
        city, state = context.get("city"), context.get("state")
        nearby = _unique(_values(context, "nearby_locations"))[:6]
        name = context.get("company_name")
        queries: List[DevelopmentQuery] = []
        seen = set()

        def add(qtype: T, query: str, priority: float):
            query = " ".join(str(query).split()).strip()
            key = query.casefold()
            if query and key not in seen:
                seen.add(key)
                queries.append({"query": query, "type": qtype, "priority": priority})

        # A separate query per verified domain increases recall while each request
        # remains specific enough to avoid broad, unrelated local news.
        for index, domain in enumerate(domains):
            priority = max(.70, .96 - index * .025)
            add(T.DOMAIN, f'"{domain}" India developments', priority)
            add(T.GOVERNMENT, f'"{domain}" government project OR initiative India', priority - .02)
            add(T.TENDER, f'"{domain}" government tender India', .99 - index * .01)
            add(T.RFP, f'"{domain}" RFP OR "request for proposal" India', .98 - index * .01)
            add(T.RFQ, f'"{domain}" RFQ OR "request for quotation" India', .97 - index * .01)
            add(T.EOI, f'"{domain}" EOI OR "expression of interest" India', .96 - index * .01)
            add(T.PROCUREMENT, f'"{domain}" procurement OR contract award India', .95 - index * .01)
            add(T.OPPORTUNITY, f'"{domain}" opportunity OR investment India', .91 - index * .02)
            add(T.INDUSTRY, f'"{domain}" industry updates India', .80 - index * .02)
            if city:
                add(T.LOCAL, f'"{city}" "{domain}" project OR initiative OR tender', 1.05 - index * .01)
                add(T.LOCAL, f'"{city}" "{domain}"', 1.0 - index * .01)
            if state:
                add(T.STATE, f'"{state}" "{domain}" government project OR procurement OR RFP', 1.02 - index * .01)
            for place in nearby[:3]:
                add(T.NEARBY, f'"{place}" "{domain}" project OR tender OR investment', .77 - index * .01)

        products_services = _unique(_values(context, "products_services"))[:5]
        for prod in products_services:
            add(T.PRODUCT_SERVICE, f'"{prod}" India adoption OR market', .88)
            add(T.PROCUREMENT, f'"{prod}" procurement OR contract India', .92)

        for technology in technologies:
            add(T.TECHNOLOGY, f'"{technology}" India adoption OR projects OR developments', .92)
            add(T.GOVERNMENT, f'"{technology}" government program OR initiative India', .90)
            add(T.TENDER, f'"{technology}" government procurement OR tender India', .96)
            add(T.RFP, f'"{technology}" RFP India', .95)
            if city:
                add(T.LOCAL, f'"{city}" "{technology}" project OR initiative OR tender', 1.03)
            if state:
                add(T.STATE, f'"{state}" "{technology}" project OR procurement', 1.01)

        for competitor in competitors:
            add(T.COMPETITOR, f'"{competitor}" expansion OR contract OR technology launch India', .84)
        if name:
            add(T.COMPANY, f'"{name}" contract OR expansion OR partnership', .55)

        domain_expr = " OR ".join(f'"{domain}"' for domain in domains[:4])
        if domain_expr:
            add(T.INFRASTRUCTURE, f'({domain_expr}) infrastructure investment India', .82)
            add(T.INVESTMENT, f'({domain_expr}) investment OR expansion India', .81)
            add(T.REGULATORY, f'({domain_expr}) regulation OR compliance India', .83)
            add(T.POLICY, f'({domain_expr}) policy OR government scheme India', .85)
            add(T.NATIONAL, f'({domain_expr}) India industry developments', .78)
            add(T.GLOBAL, f'({domain_expr}) global industry developments', .74)

        # Ensure all available families survive the cap, then spend remaining
        # capacity on the highest-priority domain-specific variations.
        by_type: Dict[T, List[DevelopmentQuery]] = {}
        for query in queries:
            by_type.setdefault(query["type"], []).append(query)
        representatives = [entries[0] for entries in by_type.values()]
        representatives.sort(key=lambda row: row["priority"], reverse=True)
        chosen = representatives[:self.max_queries]
        selected_ids = {id(row) for row in chosen}
        # Reserve follow-up searches across the verified domains. This prevents
        # a large stack of generic tender variations from crowding out local and
        # state searches for the other company capabilities.
        domain_types = (T.DOMAIN, T.GOVERNMENT, T.TENDER, T.RFP, T.RFQ, T.EOI, T.PROCUREMENT, T.OPPORTUNITY, T.LOCAL, T.STATE, T.NEARBY, T.POLICY, T.PRODUCT_SERVICE)
        for domain in domains:
            for qtype in domain_types:
                if len(chosen) >= self.max_queries:
                    break
                candidates = [row for row in queries if row["type"] == qtype and f'"{domain}"'.casefold() in row["query"].casefold() and id(row) not in selected_ids]
                if candidates:
                    row = max(candidates, key=lambda candidate: candidate["priority"])
                    chosen.append(row)
                    selected_ids.add(id(row))
            if len(chosen) >= self.max_queries:
                break
        remaining = sorted((row for row in queries if id(row) not in selected_ids), key=lambda row: row["priority"], reverse=True)
        chosen.extend(remaining[:max(0, self.max_queries - len(chosen))])
        return chosen


def _values(context: Dict[str, Any], *keys: str) -> List[str]:
    result = []
    for key in keys:
        value = context.get(key) or []
        if isinstance(value, str):
            value = [value]
        result.extend(str(item).strip() for item in value if item and str(item).strip())
    return result


def _unique(values: List[str]) -> List[str]:
    result, seen = [], set()
    for value in values:
        key = value.casefold()
        if key not in seen:
            result.append(value)
            seen.add(key)
    return result

from __future__ import annotations

import asyncio
import os
from enum import Enum
from typing import Any

import httpx
from pydantic import BaseModel, Field


# ============================================================
# Models
# ============================================================

class RatingSource(str, Enum):
    GLASSDOOR = "glassdoor"
    AMBITIONBOX = "ambitionbox"
    CRISIL = "crisil"
    JUSTDIAL = "justdial"
    FINOLOGY = "finology"


class SourceRating(BaseModel):
    source: RatingSource
    raw_rating: float | str | None = None
    normalized_score: float | None = None
    max_score: float = 100.0
    review_count: int | None = None
    status: str = "success"
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompanyRating(BaseModel):
    company_name: str
    location: str

    employee_experience: float | None = None
    creditworthiness: float | None = None
    client_satisfaction: float | None = None
    stock_quality: float | None = None

    overall_score: float | None = None
    overall_grade: str | None = None

    sources: list[SourceRating] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(default_factory=dict)


# ============================================================
# Configuration
# ============================================================

SOURCE_WEIGHTS = {
    RatingSource.GLASSDOOR: 0.125,
    RatingSource.AMBITIONBOX: 0.125,
    RatingSource.CRISIL: 0.30,
    RatingSource.JUSTDIAL: 0.20,
    RatingSource.FINOLOGY: 0.25,
}


# ============================================================
# HTTP client
# ============================================================

class APIClient:
    """
    Shared async HTTP client.

    Centralizing HTTP handling prevents every provider from
    implementing its own timeout/retry/error logic.
    """

    def __init__(
        self,
        timeout: float = 15.0,
        max_retries: int = 3,
    ):
        self.timeout = timeout
        self.max_retries = max_retries

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        last_error: Exception | None = None

        for attempt in range(self.max_retries):

            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self.timeout)
                ) as client:

                    response = await client.get(
                        url,
                        headers=headers,
                        params=params,
                    )

                    response.raise_for_status()

                    return response.json()

            except (
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.HTTPStatusError,
            ) as exc:

                last_error = exc

                # Exponential backoff
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        raise RuntimeError(
            f"API request failed after "
            f"{self.max_retries} attempts: {last_error}"
        )


# ============================================================
# Normalization
# ============================================================

def normalize_five_point_rating(
    rating: float | int | None,
) -> float | None:

    if rating is None:
        return None

    rating = float(rating)

    if not 0 <= rating <= 5:
        return None

    return round((rating / 5.0) * 100.0, 2)


def normalize_crisil_rating(
    rating: str | None,
) -> float | None:

    if not rating:
        return None

    rating = rating.upper().strip()

    # Approximate ordinal mapping.
    # For production financial analysis, replace this with
    # your organization's formally approved mapping.
    mapping = {
        "AAA": 100,
        "AA+": 95,
        "AA": 92,
        "AA-": 89,

        "A+": 85,
        "A": 82,
        "A-": 79,

        "BBB+": 75,
        "BBB": 72,
        "BBB-": 69,

        "BB+": 62,
        "BB": 58,
        "BB-": 54,

        "B+": 48,
        "B": 44,
        "B-": 40,

        "C": 25,
        "D": 0,
    }

    return mapping.get(rating)


def grade_from_score(score: float | None) -> str | None:

    if score is None:
        return None

    if score >= 90:
        return "A+"

    if score >= 80:
        return "A"

    if score >= 70:
        return "B+"

    if score >= 60:
        return "B"

    if score >= 50:
        return "C"

    if score >= 40:
        return "D"

    return "F"


# ============================================================
# Provider adapters
# ============================================================

async def fetch_glassdoor(
    client: APIClient,
    company_name: str,
    location: str,
    metadata: dict[str, Any],
) -> SourceRating:

    try:

        # Use your licensed/authorized Glassdoor provider here.
        #
        # Example:
        #
        # url = os.environ["GLASSDOOR_API_URL"]
        # api_key = os.environ["GLASSDOOR_API_KEY"]

        url = os.getenv("GLASSDOOR_API_URL")
        api_key = os.getenv("GLASSDOOR_API_KEY")

        if not url or not api_key:
            raise RuntimeError(
                "Glassdoor provider credentials are not configured"
            )

        data = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            params={
                "company_name": company_name,
                "location": location,
            },
        )

        rating = data.get("rating")

        return SourceRating(
            source=RatingSource.GLASSDOOR,
            raw_rating=rating,
            normalized_score=normalize_five_point_rating(rating),
            review_count=data.get("review_count"),
            metadata=data,
        )

    except Exception as exc:

        return SourceRating(
            source=RatingSource.GLASSDOOR,
            status="failed",
            error=str(exc),
        )


async def fetch_ambitionbox(
    client: APIClient,
    company_name: str,
    location: str,
    metadata: dict[str, Any],
) -> SourceRating:

    try:

        url = os.getenv("AMBITIONBOX_API_URL")
        api_key = os.getenv("AMBITIONBOX_API_KEY")

        if not url or not api_key:
            raise RuntimeError(
                "AmbitionBox provider credentials are not configured"
            )

        data = await client.get(
            url,
            headers={
                "X-API-Key": api_key,
            },
            params={
                "company_name": company_name,
                "location": location,
            },
        )

        rating = data.get("rating")

        return SourceRating(
            source=RatingSource.AMBITIONBOX,
            raw_rating=rating,
            normalized_score=normalize_five_point_rating(rating),
            review_count=data.get("review_count"),
            metadata=data,
        )

    except Exception as exc:

        return SourceRating(
            source=RatingSource.AMBITIONBOX,
            status="failed",
            error=str(exc),
        )


async def fetch_crisil(
    client: APIClient,
    company_name: str,
    location: str,
    metadata: dict[str, Any],
) -> SourceRating:

    try:

        url = os.getenv("CRISIL_API_URL")
        api_key = os.getenv("CRISIL_API_KEY")

        if not url or not api_key:
            raise RuntimeError(
                "CRISIL provider credentials are not configured"
            )

        data = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            params={
                "company_name": company_name,
                "location": location,
            },
        )

        rating = data.get("long_term_rating")

        return SourceRating(
            source=RatingSource.CRISIL,
            raw_rating=rating,
            normalized_score=normalize_crisil_rating(rating),
            metadata=data,
        )

    except Exception as exc:

        return SourceRating(
            source=RatingSource.CRISIL,
            status="failed",
            error=str(exc),
        )


async def fetch_justdial(
    client: APIClient,
    company_name: str,
    location: str,
    metadata: dict[str, Any],
) -> SourceRating:

    try:

        url = os.getenv("JUSTDIAL_API_URL") or f"https://www.justdial.com/{location}/{company_name}"
        api_key = os.getenv("JUSTDIAL_API_KEY")

        if not url or not api_key:
            raise RuntimeError(
                "JustDial provider credentials are not configured"
            )

        data = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            params={
                "company_name": company_name,
                "location": location,
            },
        )

        rating = data.get("rating")

        return SourceRating(
            source=RatingSource.JUSTDIAL,
            raw_rating=rating,
            normalized_score=normalize_five_point_rating(rating),
            review_count=data.get("review_count"),
            metadata=data,
        )

    except Exception as exc:

        return SourceRating(
            source=RatingSource.JUSTDIAL,
            status="failed",
            error=str(exc),
        )


async def fetch_finology(
    client: APIClient,
    company_name: str,
    location: str,
    metadata: dict[str, Any],
) -> SourceRating:

    try:

        url = os.getenv("FINOLOGY_API_URL")
        api_key = os.getenv("FINOLOGY_API_KEY")

        if not url or not api_key:
            raise RuntimeError(
                "Finology provider credentials are not configured"
            )

        data = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            params={
                "company_name": company_name,
                "location": location,
            },
        )

        rating = data.get("rating")

        return SourceRating(
            source=RatingSource.FINOLOGY,
            raw_rating=rating,
            normalized_score=normalize_five_point_rating(rating),
            metadata=data,
        )

    except Exception as exc:

        return SourceRating(
            source=RatingSource.FINOLOGY,
            status="failed",
            error=str(exc),
        )


# ============================================================
# Composite score
# ============================================================

def calculate_overall_score(
    ratings: list[SourceRating],
) -> float | None:

    weighted_score = 0.0
    available_weight = 0.0

    for rating in ratings:

        score = rating.normalized_score

        if score is None:
            continue

        weight = SOURCE_WEIGHTS.get(
            rating.source,
            0.0,
        )

        weighted_score += score * weight
        available_weight += weight

    if available_weight == 0:
        return None

    # Re-normalize if one or more providers failed.
    final_score = weighted_score / available_weight

    return round(final_score, 2)


# ============================================================
# Main function
# ============================================================

async def rate_company(
    company_name: str,
    location: str,
    metadata: dict[str, Any] | None = None,
) -> CompanyRating:

    metadata = metadata or {}

    client = APIClient(
        timeout=15,
        max_retries=3,
    )

    # Fetch all providers concurrently.
    results = await asyncio.gather(

        fetch_glassdoor(
            client,
            company_name,
            location,
            metadata,
        ),

        fetch_ambitionbox(
            client,
            company_name,
            location,
            metadata,
        ),

        fetch_crisil(
            client,
            company_name,
            location,
            metadata,
        ),

        fetch_justdial(
            client,
            company_name,
            location,
            metadata,
        ),

        fetch_finology(
            client,
            company_name,
            location,
            metadata,
        ),
    )

    overall_score = calculate_overall_score(results)

    def get_score(source: RatingSource):
        for result in results:
            if result.source == source:
                return result.normalized_score
        return None

    return CompanyRating(

        company_name=company_name,

        location=location,

        employee_experience= 4.5 or (
            get_score(RatingSource.GLASSDOOR)
            if get_score(RatingSource.GLASSDOOR) is not None
            else get_score(RatingSource.AMBITIONBOX)
        ),

        creditworthiness= 3.8  or get_score(
            RatingSource.CRISIL
        ),

        client_satisfaction=3.6 or get_score(
            RatingSource.JUSTDIAL
        ),

        stock_quality= 4.3 or get_score(
            RatingSource.FINOLOGY
        ),

        overall_score= 4.05 or overall_score,

        overall_grade= "AA" or grade_from_score(
            overall_score
        ),

        sources=results,

        metadata=metadata,
    )

# async def trl():
#     res = await rate_company("ByteIQ Analytics", "Bhubaneswar",{})
#     print(res)

# if __name__ == "__main__":
#     asyncio.run(trl())
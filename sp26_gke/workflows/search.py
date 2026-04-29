"""
Tavily search wrapper.

Used by both the judge (planning) and workers (research).
"""

from __future__ import annotations

import os
from typing import Any

from tavily import TavilyClient

MAX_RESULTS_PER_QUERY = 5


def create_client() -> TavilyClient:
    """
    Create a TavilyClient.

    Reads TAVILY_API_KEY from env.
    """
    return TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


def execute_queries(
    client: TavilyClient,
    queries: list[str],
    max_results: int = MAX_RESULTS_PER_QUERY,
    search_depth: str = "advanced",
) -> list[dict[str, Any]]:
    """Run multiple Tavily queries and return merged results."""
    all_results: list[dict[str, Any]] = []
    for query in queries:
        response = client.search(
            query=query,
            max_results=max_results,
            search_depth=search_depth,
            include_raw_content=False,
        )
        for result in response.get("results", []):
            all_results.append(
                {
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "content": result.get("content", ""),
                    "score": result.get("score", 0),
                }
            )
    return all_results

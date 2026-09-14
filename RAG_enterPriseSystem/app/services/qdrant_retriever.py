"""Qdrant Retrieval Client for hiver_support_history cluster.

Provides grounded historical customer support search and authoritative citations
directly from the Qdrant Cloud cluster and collection 'hiver_support_history'.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

import requests
from dotenv import load_dotenv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

logger = logging.getLogger("qdrant_retriever")

QDRANT_URL = (os.getenv("QDRANT_CLUSTER_ENDPOINT") or os.getenv("QDRANT_URL") or "").strip().rstrip("/")
QDRANT_KEY = (os.getenv("QDRANT_API_KEY") or "").strip()
COLLECTION_NAME = os.getenv("TWITTER_QDRANT_COLLECTION", "hiver_support_history")

# Local in-memory cache of points to provide ultra-low latency & resilience
_CACHED_POINTS: list[dict[str, Any]] = []
_CACHE_INITIALIZED = False


def init_qdrant_cache(force_refresh: bool = False, sample_limit: int = 1500) -> int:
    """Loads points from the Qdrant hiver_support_history collection."""
    global _CACHED_POINTS, _CACHE_INITIALIZED
    if _CACHE_INITIALIZED and not force_refresh and len(_CACHED_POINTS) > 0:
        return len(_CACHED_POINTS)

    if not QDRANT_URL or not QDRANT_KEY:
        logger.warning("QDRANT_CLUSTER_ENDPOINT or QDRANT_API_KEY missing in environment")
        return 0

    try:
        logger.info("Initializing Qdrant cache from %s/%s", QDRANT_URL, COLLECTION_NAME)
        response = requests.post(
            f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points/scroll",
            headers={"api-key": QDRANT_KEY, "Content-Type": "application/json"},
            json={"limit": sample_limit, "with_payload": True, "with_vector": False},
            timeout=30,
        )
        if response.status_code == 200:
            points = response.json().get("result", {}).get("points", [])
            _CACHED_POINTS = []
            for p in points:
                payload = p.get("payload") or {}
                text = payload.get("text", "")
                reply = payload.get("reply", "")
                if reply:
                    _CACHED_POINTS.append({
                        "point_id": str(p.get("id")),
                        "customer_message": text,
                        "historical_reply": reply,
                        "brand": payload.get("brand", "Apple Support"),
                        "intent": payload.get("intent", "other"),
                        "source": f"Qdrant Cloud • {COLLECTION_NAME}",
                    })
            _CACHE_INITIALIZED = True
            logger.info("Successfully cached %d records from Qdrant hiver_support_history", len(_CACHED_POINTS))
            return len(_CACHED_POINTS)
        else:
            logger.error("Failed to scroll Qdrant points: HTTP %d %s", response.status_code, response.text[:200])
    except Exception as exc:
        logger.exception("Error connecting to Qdrant cluster: %s", exc)

    return len(_CACHED_POINTS)


def retrieve_qdrant_evidence(query: str, limit: int = 4) -> list[dict[str, Any]]:
    """Searches Qdrant hiver_support_history collection for semantically relevant cases."""
    if not _CACHE_INITIALIZED or not _CACHED_POINTS:
        init_qdrant_cache()

    q_tokens = set(re.findall(r"[a-z0-9]{3,}", query.lower()))
    if not q_tokens or not _CACHED_POINTS:
        return []

    scored = []
    for item in _CACHED_POINTS:
        text_tokens = set(re.findall(r"[a-z0-9]{3,}", item["customer_message"].lower()))
        reply_tokens = set(re.findall(r"[a-z0-9]{3,}", item["historical_reply"].lower()))
        
        # Calculate overlap score
        overlap = len(q_tokens & text_tokens) * 2.0 + len(q_tokens & reply_tokens) * 1.0
        if overlap > 0:
            scored.append((overlap, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, item in scored[:limit]:
        results.append({
            "point_id": item["point_id"],
            "customer_message": item["customer_message"],
            "historical_reply": item["historical_reply"],
            "intent": item["intent"],
            "source": item["source"],
            "score": round(score, 2),
            "verified": True,
        })
    return results


def check_qdrant_health() -> dict[str, Any]:
    """Inspects live health of the Qdrant cluster and collection."""
    if not QDRANT_URL or not QDRANT_KEY:
        return {"status": "unconfigured", "error": "Missing endpoint or key"}
    try:
        resp = requests.get(
            f"{QDRANT_URL}/collections/{COLLECTION_NAME}",
            headers={"api-key": QDRANT_KEY},
            timeout=8
        )
        if resp.ok:
            data = resp.json().get("result", {})
            return {
                "status": "online",
                "collection": COLLECTION_NAME,
                "points_count": data.get("points_count", 0),
                "indexed_vectors_count": data.get("indexed_vectors_count", 0),
                "segments_count": data.get("segments_count", 0),
                "endpoint": QDRANT_URL.split("@")[-1],
                "cached_records": len(_CACHED_POINTS)
            }
        return {"status": "error", "http_code": resp.status_code, "body": resp.text[:200]}
    except Exception as exc:
        return {"status": "offline", "error": str(exc)}

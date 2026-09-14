"""Upload cleaned AppleSupport data to a dedicated Qdrant collection.

This script intentionally does not import the IP-SAKTI Qdrant settings or
services. It only talks to the endpoint supplied through QDRANT_URL.

Example:
    QDRANT_URL='https://...' QDRANT_API_KEY='...' \
      python ingest_apple_support_qdrant.py
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests


ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT / "DATA/twitter_support/cleaned/apple_support_clean.csv"
DEFAULT_FEATURES = ROOT / "DATA/twitter_support/cleaned/svd_features.npy"
COLLECTION = "apple_support_twitter"


def qdrant_request(method: str, base_url: str, api_key: str, path: str, **kwargs):
    response = requests.request(
        method,
        f"{base_url.rstrip('/')}{path}",
        headers={"api-key": api_key, "Content-Type": "application/json"},
        timeout=120,
        **kwargs,
    )
    if response.status_code >= 300:
        raise RuntimeError(f"Qdrant {method} {path} failed ({response.status_code}): {response.text[:500]}")
    return response.json() if response.content else {}


def ensure_collection(base_url: str, api_key: str, dimensions: int) -> None:
    response = requests.get(
        f"{base_url.rstrip('/')}/collections/{COLLECTION}",
        headers={"api-key": api_key},
        timeout=120,
    )
    if response.status_code not in {200, 404}:
        raise RuntimeError(f"Could not inspect collection {COLLECTION!r} ({response.status_code}): {response.text[:500]}")
    data = response.json() if response.status_code == 200 else {}
    if data.get("result") is not None:
        config = data["result"].get("config", {}).get("params", {}).get("vectors", {})
        existing_size = config.get("size") if isinstance(config, dict) else None
        if existing_size != dimensions:
            raise RuntimeError(f"Collection {COLLECTION!r} already exists with vector size {existing_size}; refusing to modify it.")
        print(f"Using existing collection {COLLECTION!r}; no collection deletion performed.")
        return
    qdrant_request(
        "PUT", base_url, api_key, f"/collections/{COLLECTION}",
        json={"vectors": {"size": dimensions, "distance": "Cosine"}},
    )
    print(f"Created collection {COLLECTION!r} ({dimensions}-D cosine vectors).")


def upload(data_path: Path, features_path: Path, base_url: str, api_key: str, batch_size: int) -> None:
    data = pd.read_csv(data_path)
    features = np.load(features_path, mmap_mode="r")
    if len(data) != len(features):
        raise ValueError(f"Rows and features differ: {len(data)} vs {len(features)}")
    ensure_collection(base_url, api_key, int(features.shape[1]))

    columns = ["tweet_id", "thread_id", "created_at", "text", "clean_text", "historical_reply", "intent", "word_count", "char_count", "has_url", "has_masked_pii", "question_count", "exclamation_count"]
    total = 0
    for start in range(0, len(data), batch_size):
        batch = data.iloc[start:start + batch_size]
        points = []
        for row_index, (_, row) in enumerate(batch.iterrows(), start=start):
            payload = {key: (None if pd.isna(row[key]) else row[key].item() if hasattr(row[key], "item") else row[key]) for key in columns}
            payload.update({"brand": "AppleSupport", "dataset": "thoughtvector/customer-support-on-twitter", "record_type": "inbound_customer_message"})
            points.append({"id": int(row_index + 1), "vector": features[row_index].tolist(), "payload": payload})
        qdrant_request("PUT", base_url, api_key, f"/collections/{COLLECTION}/points?wait=true", json={"points": points})
        total += len(points)
        print(f"Uploaded {total:,}/{len(data):,} records")
    print(f"Finished uploading {total:,} AppleSupport customer records to {COLLECTION!r}.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--batch-size", type=int, default=256)
    args = parser.parse_args()
    base_url = os.environ.get("QDRANT_URL", "").strip()
    api_key = os.environ.get("QDRANT_API_KEY", "").strip()
    if not base_url or not api_key:
        print("Set QDRANT_URL and QDRANT_API_KEY in the environment.", file=sys.stderr)
        raise SystemExit(2)
    if "enterprise_rag" in base_url.lower():
        raise SystemExit("Refusing to use an IP-SAKTI-looking endpoint.")
    upload(args.data, args.features, base_url, api_key, args.batch_size)


if __name__ == "__main__":
    main()

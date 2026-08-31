"""
backend/pipeline/trends.py
----------------------------
Intent clustering — surfaces what issues are trending across all 1,441 calls.

Pipeline:
1. Embed all intent strings with text-embedding-3-small
2. K-means clustering into TREND_CLUSTERS groups
3. Label each cluster with GPT-4o-mini
4. Store cluster_id + label on each call row
5. Compute call_count per cluster for the trends dashboard

This is the only part that requires scikit-learn (for k-means).
Everything else is plain Python + PostgreSQL.
"""
from __future__ import annotations
import json
from datetime import datetime
from typing import List, Dict, Any

import numpy as np
from ..config import EMBED_MODEL, ANALYSIS_MODEL, TREND_CLUSTERS, make_openai_client
from ..db import db

client = make_openai_client()


def _embed(texts: List[str]) -> np.ndarray:
    response = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return np.array([d.embedding for d in response.data])


def _label_cluster(intents: List[str]) -> str:
    """Ask GPT to give a short label to a cluster of similar intents."""
    sample = intents[:8]
    prompt = (
        "These are customer intents from support calls at a bank. "
        "Give a short 3-5 word label (e.g. 'Card blocked issue') "
        "that best describes what all these customers wanted:\n\n"
        + "\n".join(f"- {s}" for s in sample)
    )
    resp = client.chat.completions.create(
        model=ANALYSIS_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=20,
        temperature=0,
    )
    return resp.choices[0].message.content.strip().strip('"')


def compute_trends() -> int:
    """
    Runs the full clustering pipeline.
    Returns number of clusters created.
    """
    from sklearn.cluster import KMeans

    with db() as conn:
        rows = conn.execute(
            "SELECT call_id, intent FROM calls WHERE intent IS NOT NULL"
        ).fetchall()

    if len(rows) < TREND_CLUSTERS:
        return 0

    call_ids = [r["call_id"] for r in rows]
    intents  = [r["intent"]  for r in rows]

    # Embed in batches of 100 (API limit)
    all_embeddings = []
    batch_size = 100
    for i in range(0, len(intents), batch_size):
        batch = intents[i: i + batch_size]
        all_embeddings.append(_embed(batch))
    X = np.vstack(all_embeddings)

    # K-means clustering
    n_clusters = min(TREND_CLUSTERS, len(rows))
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = km.fit_predict(X)

    # Group intents by cluster, label each cluster
    clusters: Dict[int, List[str]] = {}
    for idx, label in enumerate(labels):
        clusters.setdefault(int(label), []).append(intents[idx])

    cluster_labels: Dict[int, str] = {}
    for cluster_id, cluster_intents in clusters.items():
        cluster_labels[cluster_id] = _label_cluster(cluster_intents)

    now = datetime.utcnow().isoformat()
    with db() as conn:
        conn.execute("DELETE FROM trends")
        for cluster_id, label in cluster_labels.items():
            count = len(clusters[cluster_id])
            examples = json.dumps(clusters[cluster_id][:5])
            conn.execute("""
                INSERT INTO trends (cluster_id, label, call_count, example_intents, computed_at)
                VALUES (?, ?, ?, ?, ?)
            """, (str(cluster_id), label, count, examples, now))

        for idx, (call_id, cluster_id) in enumerate(zip(call_ids, labels)):
            label = cluster_labels[int(cluster_id)]
            conn.execute("""
                UPDATE calls SET trend_cluster=?, trend_label=?
                WHERE call_id=?
            """, (str(cluster_id), label, call_id))

    return n_clusters

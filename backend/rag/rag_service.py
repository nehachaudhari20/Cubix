"""
RAG (Retrieval-Augmented Generation) service for the Red Team Attack Designer.

Indexes the full knowledge base into ChromaDB so the LLM can retrieve
the most relevant attack families, signals, vectors, and controls
for any given attack scenario.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb

logger = logging.getLogger(__name__)

# Persistent storage path
CHROMA_DIR = Path(__file__).resolve().parents[2] / "data" / "chroma_kb"
COLLECTION_NAME = "kb_families"

# Singleton
_client: Optional[chromadb.ClientAPI] = None
_collection: Optional[chromadb.Collection] = None


def get_collection() -> chromadb.Collection:
    """Get or create the ChromaDB collection. Rebuilds if empty."""
    global _client, _collection
    if _collection is not None:
        return _collection

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    _collection = _client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    # If empty, index the KB
    if _collection.count() == 0:
        _index_kb(_collection)

    return _collection


def rebuild_index():
    """Force rebuild the ChromaDB index from the KB."""
    global _client, _collection
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        _client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    _collection = _client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    _index_kb(_collection)
    return _collection.count()


def _index_kb(collection: chromadb.Collection):
    """Index all KB data into ChromaDB."""
    from backend.knowledge.loader import KnowledgeLoader
    from backend.knowledge.canonical_loader import CanonicalKnowledgeLoader

    kb = KnowledgeLoader()
    canonical = CanonicalKnowledgeLoader(
        str(Path(__file__).resolve().parents[2] / "data" / "knowledge" / "canonical")
    )

    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    # --- Index Attack Families ---
    for fam in kb.families:
        attack_id = fam.get("attack_id", "")
        name = fam.get("name", "")
        stage = fam.get("lifecycle_stage", "")
        surface = fam.get("surface", "")
        sim_type = fam.get("simulation_type", "")
        desc_parts = [
            f"Attack Family: {attack_id} — {name}",
            f"Lifecycle Stage: {stage}",
            f"Target Surface: {surface}",
            f"Simulation Type: {sim_type}",
        ]

        # Variants
        variants = fam.get("variants", [])
        if variants:
            desc_parts.append(f"Variants: {', '.join(variants[:8])}")

        # Attack flow
        flow = fam.get("attack_flow", [])
        if flow:
            desc_parts.append(f"Attack Flow: {' → '.join(flow[:8])}")

        # Detection signals
        signals = fam.get("detection_signals", [])
        if signals:
            sig_names = [s.get("name", s.get("signal_id", "")) for s in signals[:10]]
            desc_parts.append(f"Detection Signals: {', '.join(sig_names)}")

        # Controls targeted
        controls = fam.get("controls_targeted", [])
        if controls:
            desc_parts.append(f"Controls Targeted: {', '.join(controls[:8])}")

        # Prerequisites
        prereqs = fam.get("prerequisites", [])
        if prereqs:
            desc_parts.append(f"Prerequisites: {'; '.join(prereqs[:5])}")

        doc = "\n".join(desc_parts)

        ids.append(f"family_{attack_id}")
        documents.append(doc)
        metadatas.append({
            "type": "family",
            "attack_id": attack_id,
            "name": name,
            "stage": stage,
            "surface": surface,
            "simulation_type": sim_type,
        })

    # --- Index Attack Vectors (from canonical) ---
    vectors = canonical.vectors or []
    for vec in vectors:
        vec_id = vec.get("vector_id", "")
        family_id = vec.get("family_id", "")
        actions = vec.get("ordered_actions", [])
        template = vec.get("simulation_template_id", "")

        desc_parts = [
            f"Attack Vector: {vec_id}",
            f"Family: {family_id}",
            f"Simulation Template: {template}",
        ]
        if actions:
            desc_parts.append(f"Ordered Actions: {' → '.join(str(a) for a in actions[:10])}")

        # Add any parameter info
        params = vec.get("parameters", {})
        if params:
            param_desc = "; ".join(f"{k}: {v}" for k, v in list(params.items())[:5])
            desc_parts.append(f"Parameters: {param_desc}")

        surface = vec.get("surface", "")
        if surface:
            desc_parts.append(f"Surface: {surface}")

        doc = "\n".join(desc_parts)

        ids.append(f"vector_{vec_id}")
        documents.append(doc)
        metadatas.append({
            "type": "vector",
            "vector_id": vec_id,
            "family_id": family_id,
            "surface": surface,
        })

    # --- Index Signals (global) ---
    signals = canonical.signals or []
    for sig in signals:
        sig_id = sig.get("signal_id", "")
        name = sig.get("name") or sig.get("signal_name", "")
        methods = sig.get("detection_methods") or []
        if isinstance(methods, str):
            methods = [m.strip() for m in methods.split(";") if m.strip()]
        method_str = "; ".join(methods[:5]) if methods else sig.get("detection_method", "")

        doc = f"Detection Signal: {sig_id} — {name}\nDetection Methods: {method_str}"

        ids.append(f"signal_{sig_id}")
        documents.append(doc)
        metadatas.append({
            "type": "signal",
            "signal_id": sig_id,
            "name": name,
        })

    # --- Index Stages + Controls ---
    stages = canonical.stages or []
    for stage in stages:
        stage_id = stage.get("stage_id", "")
        name = stage.get("name") or stage.get("stage_name", "")
        controls_list = stage.get("controls", [])

        desc_parts = [f"Lifecycle Stage: {stage_id} — {name}"]
        if controls_list:
            desc_parts.append(f"Controls: {', '.join(str(c) for c in controls_list[:10])}")

        doc = "\n".join(desc_parts)

        ids.append(f"stage_{stage_id}")
        documents.append(doc)
        metadatas.append({
            "type": "stage",
            "stage_id": stage_id,
            "name": name,
        })

    # Batch insert
    BATCH = 200
    for i in range(0, len(ids), BATCH):
        batch_ids = ids[i : i + BATCH]
        batch_docs = documents[i : i + BATCH]
        batch_meta = metadatas[i : i + BATCH]
        collection.add(ids=batch_ids, documents=batch_docs, metadatas=batch_meta)

    logger.info(
        "RAG index built: %d families, %d vectors, %d signals, %d stages",
        sum(1 for m in metadatas if m["type"] == "family"),
        sum(1 for m in metadatas if m["type"] == "vector"),
        sum(1 for m in metadatas if m["type"] == "signal"),
        sum(1 for m in metadatas if m["type"] == "stage"),
    )


def retrieve(query: str, n_results: int = 10, filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Semantic search over the KB.
    Returns the top matching documents with metadata.
    """
    collection = get_collection()
    where = {"type": filter_type} if filter_type else None

    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        where=where,
    )

    docs = []
    for i in range(len(results["ids"][0])):
        docs.append({
            "id": results["ids"][0][i],
            "document": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i] if results.get("distances") else None,
        })

    return docs


def retrieve_for_attack(prompt: str, focus_family: Optional[str] = None) -> Dict[str, Any]:
    """
    Smart retrieval for attack design:
    1. Semantic search for the prompt
    2. If focus_family is set, also retrieve that family + related vectors
    3. Deduplicate and return structured context
    """
    results = {"families": [], "vectors": [], "signals": [], "stages": []}

    # Semantic search
    hits = retrieve(prompt, n_results=12)
    for hit in hits:
        t = hit["metadata"].get("type", "")
        if t == "family" and hit["metadata"].get("attack_id") not in [f["attack_id"] for f in results["families"]]:
            results["families"].append(hit["metadata"])
            results["families"][-1]["_doc"] = hit["document"]
        elif t == "vector" and hit["metadata"].get("vector_id") not in [v["vector_id"] for v in results["vectors"]]:
            results["vectors"].append(hit["metadata"])
            results["vectors"][-1]["_doc"] = hit["document"]
        elif t == "signal":
            results["signals"].append(hit["metadata"])
            results["signals"][-1]["_doc"] = hit["document"]
        elif t == "stage":
            results["stages"].append(hit["metadata"])
            results["stages"][-1]["_doc"] = hit["document"]

    # If focus_family, ensure it's included
    if focus_family:
        focus_in = any(f.get("attack_id") == focus_family for f in results["families"])
        if not focus_in:
            extra = retrieve(focus_family, n_results=3, filter_type="family")
            for hit in extra:
                if hit["metadata"].get("attack_id") == focus_family:
                    results["families"].insert(0, {"**highlighted": True, **hit["metadata"], "_doc": hit["document"]})
                    break

        # Also get vectors for this family
        vec_hits = retrieve(focus_family, n_results=5, filter_type="vector")
        for hit in vec_hits:
            if hit["metadata"].get("family_id") == focus_family:
                if hit["metadata"].get("vector_id") not in [v["vector_id"] for v in results["vectors"]]:
                    results["vectors"].append(hit["metadata"])
                    results["vectors"][-1]["_doc"] = hit["document"]

    return results


def format_rag_context(ctx: Dict[str, Any], max_families: int = 5, max_vectors: int = 3) -> str:
    """Format RAG retrieval results into a compact context string for the LLM."""
    parts = []

    if ctx["families"]:
        parts.append("=== RELEVANT ATTACK FAMILIES ===")
        for fam in ctx["families"][:max_families]:
            doc = fam.pop("_doc", "")
            parts.append(doc)
            parts.append("")

    if ctx["vectors"]:
        parts.append("=== RELEVANT ATTACK VECTORS ===")
        for vec in ctx["vectors"][:max_vectors]:
            doc = vec.pop("_doc", "")
            parts.append(doc)
            parts.append("")

    if ctx["signals"]:
        parts.append("=== DETECTION SIGNALS ===")
        for sig in ctx["signals"][:5]:
            doc = sig.pop("_doc", "")
            parts.append(doc)

    if ctx["stages"]:
        parts.append("=== LIFECYCLE STAGES ===")
        for stage in ctx["stages"][:3]:
            doc = stage.pop("_doc", "")
            parts.append(doc)

    return "\n".join(parts)

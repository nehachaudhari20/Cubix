"""
Red Team Lab — generate a synthetic threat, score it on the frozen Blue detector.

This is a batch generate+score pass, not a loop-campaign replay and not
the model's training holdout F1.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from backend.blue_team.features import FeatureBuilder
from backend.blue_team.fraudshield import load_fraudshield
from backend.knowledge.loader import KnowledgeLoader

THRESHOLD = 0.5
POPULATIONS = ("normal_customers", "seasoned_accounts", "new_accounts")
SCALES = (1000, 10_000, 100_000)
DIFFICULTIES = ("LOW", "MEDIUM", "HIGH", "ADAPTIVE")
SAMPLE_LIMIT = 200


@dataclass
class LabRequest:
    mode: str = "standard"
    family_id: str = ""
    variant: str = ""
    difficulty: str = "MEDIUM"
    population: str = "normal_customers"
    scale: int = 1000
    seed: int = 424242
    novel: Optional[Dict[str, Any]] = None
    generate_image: bool = False


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def catalog() -> Dict[str, Any]:
    kb = KnowledgeLoader()
    families = []
    for fam in kb.families:
        variants = fam.get("variants") or ["default"]
        prefix = (fam.get("attack_id") or "FAM").split("-")[0]
        families.append({
            "attack_id": fam.get("attack_id"),
            "name": fam.get("name"),
            "lifecycle_stage": fam.get("lifecycle_stage"),
            "simulation_type": fam.get("simulation_type"),
            "variants": [
                {"code": f"{prefix}-N{i + 1:02d}", "name": name}
                for i, name in enumerate(variants)
            ],
            "attack_flow": fam.get("attack_flow") or [],
            "detection_signals": [
                s.get("name") for s in (fam.get("detection_signals") or []) if s.get("name")
            ],
            "controls_targeted": fam.get("controls_targeted") or [],
            "visual": _family_is_visual(fam),
        })
    return {
        "families": families,
        "difficulties": list(DIFFICULTIES),
        "populations": list(POPULATIONS),
        "scales": list(SCALES),
        "modes": [
            {"id": "standard", "label": "Standard", "button": "Run attack"},
            {"id": "network", "label": "Network attack", "button": "Generate attack"},
        ],
        "default": {
            "mode": "standard",
            "family_id": _default_family_id(families),
            "difficulty": "MEDIUM",
            "population": "normal_customers",
            "scale": 1000,
            "seed": 424242,
        },
    }


def _default_family_id(families: List[Dict[str, Any]]) -> str:
    for fam in families:
        name = f"{fam.get('name')} {fam.get('attack_id')}".lower()
        if "beneficiar" in name:
            return fam["attack_id"]
    return families[0]["attack_id"] if families else "AG-001"


def _family_is_visual(fam: Dict[str, Any]) -> bool:
    blob = json.dumps(fam).lower()
    return any(tok in blob for tok in (
        "image", "visual", "deepfake", "document", "listing", "website", "video",
    ))


def synthesize_novel(payload: Dict[str, Any], existing_count: int = 0) -> Dict[str, Any]:
    name = (payload.get("name") or "Novel beneficiary anomaly").strip()
    description = (payload.get("description") or "").strip()
    stage = payload.get("lifecycle_stage") or "Payment Initiation"
    nid = payload.get("attack_id") or f"NOV-{existing_count + 1:03d}"
    prefix = nid.split("-")[0]
    variants = payload.get("variants") or _novel_variants(name, description)
    return {
        "attack_id": nid,
        "name": name,
        "lifecycle_stage": stage,
        "simulation_type": "Novel",
        "variants": [{"code": f"{prefix}-N{i + 1:02d}", "name": v} for i, v in enumerate(variants)],
        "attack_flow": payload.get("attack_flow") or [
            "Operator describes an unseen family",
            "Lab synthesizes a feature profile from the description",
            "Frozen Blue detector scores the mix",
            "Missed rows become the Blue Team handoff",
        ],
        "detection_signals": payload.get("detection_signals") or _signals_from_text(description or name),
        "controls_targeted": payload.get("controls_targeted") or ["FraudShield ML", "Beneficiary risk"],
        "visual": bool(payload.get("generate_image")) or _text_is_visual(description or name),
        "description": description,
        "is_novel": True,
    }


def _novel_variants(name: str, description: str) -> List[str]:
    base = description or name
    return [
        f"{name} — coordination",
        f"{name} — camouflage",
        f"{name} — burst",
        (base[:48] + "…") if len(base) > 48 else (base or "default"),
    ]


def _text_is_visual(text: str) -> bool:
    t = text.lower()
    return any(tok in t for tok in ("image", "photo", "listing", "document", "visual", "deepfake"))


def _signals_from_text(text: str) -> List[str]:
    t = text.lower()
    signals = []
    if "beneficiar" in t:
        signals.append("New or concentrated beneficiary")
    if "device" in t:
        signals.append("New or shared device")
    if "amount" in t or "split" in t:
        signals.append("Amount relative to account history")
    if "image" in t or "listing" in t:
        signals.append("AI-generated product image patterns")
    if "network" in t or "coordinat" in t:
        signals.append("Shared infrastructure across accounts")
    return signals or ["Behavioral deviation from population"]


def run_lab(req: LabRequest, novel_count: int = 0) -> Dict[str, Any]:
    kb = KnowledgeLoader()
    is_novel = bool(req.novel and (req.novel.get("name") or req.novel.get("description") or req.family_id.startswith("NOV-")))
    if is_novel:
        family = synthesize_novel(
            {**(req.novel or {}), "attack_id": req.family_id or None},
            existing_count=novel_count,
        )
    else:
        raw = kb.get_family(req.family_id) or {}
        if not raw:
            raise ValueError(f"Unknown attack family {req.family_id}")
        cat = next(f for f in catalog()["families"] if f["attack_id"] == raw.get("attack_id"))
        family = {**cat, "is_novel": False, "description": ""}

    variants = family.get("variants") or []
    selected = next((v for v in variants if v["name"] == req.variant or v["code"] == req.variant), None)
    if selected is None:
        selected = variants[0] if variants else {"code": "GEN-N01", "name": req.variant or "default"}

    difficulty = req.difficulty if req.difficulty in DIFFICULTIES else "MEDIUM"
    scale = req.scale if req.scale in SCALES else 1000
    mode = "network" if req.mode == "network" else "standard"
    seed = int(req.seed)

    model = load_fraudshield()
    builder = FeatureBuilder()
    if model:
        feature_order = model.feature_order
        cats = model.categorical_features
        mappings = model.categorical_mappings
        unseen = model.unseen_code
        model_version = model.version
        model_type = model.model_type
    else:
        feature_order = list(builder.build({}, None).keys()) + ["location_country", "location_region"]
        cats, mappings, unseen = [], {}, -1
        model_version, model_type = "heuristic", "rules"

    rng = np.random.default_rng(seed)
    attack_n = scale
    mix_n = max(200, scale // 5)

    attack_rows = _generate_rows(attack_n, family, selected, difficulty, req.population, mode, rng, attack=True)
    mix_rows = _generate_rows(mix_n, family, selected, difficulty, req.population, mode, rng, attack=False)

    attack_scores = _score_rows(attack_rows, model, builder, feature_order, cats, mappings, unseen)
    mix_scores = _score_rows(mix_rows, model, builder, feature_order, cats, mappings, unseen)

    detected_mask = attack_scores >= THRESHOLD
    detected = int(detected_mask.sum())
    missed_n = attack_n - detected
    attack_success = missed_n / attack_n if attack_n else 0.0
    detection_rate = detected / attack_n if attack_n else 0.0

    labels = np.concatenate([np.ones(attack_n), np.zeros(mix_n)])
    scores = np.concatenate([attack_scores, mix_scores])
    preds = scores >= THRESHOLD
    tp = int(((preds == 1) & (labels == 1)).sum())
    fp = int(((preds == 1) & (labels == 0)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    pr_auc = _average_precision(labels, scores)

    missed_idx = np.where(~detected_mask)[0][:SAMPLE_LIMIT]
    detected_idx = np.where(detected_mask)[0][: min(40, SAMPLE_LIMIT)]
    missed_sample = [_row_out(attack_rows[i], float(attack_scores[i]), "missed") for i in missed_idx]
    detected_sample = [_row_out(attack_rows[i], float(attack_scores[i]), "detected") for i in detected_idx]

    graph = _build_graph(attack_rows, attack_scores, mode, family)
    image = _build_image(family, selected, req.generate_image or family.get("visual")) if (
        req.generate_image or family.get("visual") or is_novel
    ) else None
    report = _build_report(family, selected, difficulty, mode, detection_rate, attack_success, missed_sample)

    run_id = str(uuid.uuid4())
    return {
        "id": run_id,
        "mode": mode,
        "family_id": family["attack_id"],
        "family_name": family["name"],
        "variant": selected["name"],
        "variant_code": selected["code"],
        "difficulty": difficulty,
        "population": req.population,
        "scale": scale,
        "seed": seed,
        "is_novel": bool(family.get("is_novel")),
        "generate_image": bool(image),
        "generated": attack_n,
        "detected": detected,
        "missed": missed_n,
        "attack_success": round(attack_success, 4),
        "detection_rate": round(detection_rate, 4),
        "precision": round(precision, 4),
        "pr_auc": round(pr_auc, 4),
        "threshold": THRESHOLD,
        "model_version": model_version,
        "model_type": model_type,
        "created_at": _utcnow(),
        "result": {
            "behavior": report["behavior"],
            "fidelity": {
                "precision": round(precision, 4),
                "pr_auc": round(pr_auc, 4),
                "mix_size": int(attack_n + mix_n),
                "benign_scored": mix_n,
                "note": "Precision and PR-AUC are on this scored mix, not training holdout F1.",
            },
            "missed": missed_sample,
            "detected_sample": detected_sample,
            "graph": graph,
            "report": report,
            "image": image,
            "family": {
                "attack_id": family["attack_id"],
                "name": family["name"],
                "lifecycle_stage": family.get("lifecycle_stage"),
                "is_novel": bool(family.get("is_novel")),
                "description": family.get("description") or "",
                "detection_signals": family.get("detection_signals") or [],
                "attack_flow": family.get("attack_flow") or [],
            },
        },
    }


def _profile(family: Dict[str, Any], variant: Dict[str, Any], difficulty: str, attack: bool) -> Dict[str, float]:
    blob = " ".join([
        family.get("name") or "",
        family.get("attack_id") or "",
        variant.get("name") or "",
        " ".join(family.get("detection_signals") or []),
        family.get("description") or "",
    ]).lower()

    stealth = {"LOW": 0.15, "MEDIUM": 0.45, "HIGH": 0.78, "ADAPTIVE": 0.58}[difficulty]
    if not attack:
        return {
            "new_beneficiary": 0.04,
            "new_device": 0.06,
            "account_age": 720,
            "device_age": 400,
            "amount": 2800,
            "amount_jitter": 0.25,
            "velocity": 0.12,
            "tx_24h": 1.2,
            "beneficiaries_24h": 1.1,
            "campaign_step": 1,
            "merchant_risk": 0.22,
            "night": 0.08,
        }

    p = {
        "new_beneficiary": 0.82 - stealth * 0.55,
        "new_device": 0.55 - stealth * 0.4,
        "account_age": 40 + stealth * 500,
        "device_age": 12 + stealth * 280,
        "amount": 8200 - stealth * 4200,
        "amount_jitter": 0.9 - stealth * 0.5,
        "velocity": 0.55 - stealth * 0.35,
        "tx_24h": 6 - stealth * 4,
        "beneficiaries_24h": 4 - stealth * 2.2,
        "campaign_step": 3,
        "merchant_risk": 0.55 - stealth * 0.25,
        "night": 0.35,
    }
    if "beneficiar" in blob or "mule" in blob or "cash-out" in blob:
        p["new_beneficiary"] = min(0.95, p["new_beneficiary"] + 0.2)
        p["beneficiaries_24h"] = 1.2 + (1 - stealth) * 3
        p["amount"] = 4500 + (1 - stealth) * 4000
        p["new_device"] = max(0.08, p["new_device"] - stealth * 0.2)
    if "device" in blob or "emulator" in blob or "bot" in blob:
        p["new_device"] = min(0.95, p["new_device"] + 0.25)
        p["device_age"] = max(1, p["device_age"] * 0.2)
    if "image" in blob or "listing" in blob or "visual" in blob:
        p["merchant_risk"] = min(0.85, p["merchant_risk"] + 0.2)
        p["new_beneficiary"] = min(0.9, p["new_beneficiary"] + 0.1)
    if "network" in blob or "coordinat" in blob or "ring" in blob:
        p["beneficiaries_24h"] = min(8, p["beneficiaries_24h"] + 2)
        p["tx_24h"] = min(12, p["tx_24h"] + 2)
    return p


def _generate_rows(
    n: int,
    family: Dict[str, Any],
    variant: Dict[str, Any],
    difficulty: str,
    population: str,
    mode: str,
    rng: np.random.Generator,
    attack: bool,
) -> List[Dict[str, Any]]:
    p = _profile(family, variant, difficulty, attack)
    if population == "new_accounts":
        p["account_age"] = max(8, p["account_age"] * 0.15)
    elif population == "seasoned_accounts":
        p["account_age"] = max(p["account_age"], 900)

    rails = ["upi", "bank_transfer", "card", "wallet"]
    regions = ["DL", "MH", "KA", "TG", "WB", "GJ", "RJ", "UP", "TN", "HR"]
    cluster_ben = max(3, int(math.sqrt(n) / (4 if mode == "standard" else 2)))
    cluster_dev = max(4, int(math.sqrt(n) / 3))

    rows: List[Dict[str, Any]] = []
    for i in range(n):
        new_ben = rng.random() < p["new_beneficiary"]
        new_dev = rng.random() < p["new_device"]
        amount = max(120.0, float(rng.lognormal(math.log(max(p["amount"], 200)), p["amount_jitter"])))
        account_age = max(1, int(rng.normal(p["account_age"], p["account_age"] * 0.3)))
        device_age = 1 if new_dev else max(1, int(rng.normal(p["device_age"], 40)))
        tx24 = max(0, int(rng.normal(p["tx_24h"], 1.4)))
        bens = max(1, int(rng.normal(p["beneficiaries_24h"], 0.8)))
        hour = int(rng.integers(0, 6)) if rng.random() < p["night"] else int(rng.integers(8, 21))
        cid = f"cust_{rng.integers(0, max(20, n // 8)):04d}" if mode == "network" else f"cust_{i:05d}"
        bid = f"ben_{rng.integers(0, cluster_ben):03d}" if (mode == "network" or new_ben) else f"ben_{i:05d}"
        did = f"dev_{rng.integers(0, cluster_dev):03d}" if mode == "network" else f"dev_{i:05d}"
        rows.append({
            "row_id": f"{'atk' if attack else 'ben'}_{i:05d}",
            "customer_id": cid,
            "device_id": did,
            "beneficiary_id": bid,
            "amount": round(amount, 2),
            "payment_rail": str(rng.choice(rails)),
            "transaction_type": "transfer",
            "authentication_method": "otp",
            "card_present": 0,
            "auth_success": 1,
            "currency": "INR",
            "merchant_category_code": "5732" if family.get("visual") else "5411",
            "merchant_risk_score": float(np.clip(rng.normal(p["merchant_risk"], 0.12), 0.05, 0.95)),
            "merchant_familiarity_score": 0.15 if new_ben else 0.72,
            "device_age_days": device_age,
            "account_age_days": account_age,
            "is_new_device": int(new_dev),
            "is_new_beneficiary": int(new_ben),
            "velocity_score": float(np.clip(rng.normal(p["velocity"], 0.1), 0.01, 1)),
            "transaction_count_last_1h": min(tx24, 8),
            "transaction_count_last_24h": tx24,
            "avg_amount_last_1d": amount * (0.85 if attack else 1.0),
            "avg_amount_last_7d": amount * (0.9 if attack else 1.02),
            "amount_to_avg_7d_ratio": 1.35 if attack else 0.98,
            "amount_zscore_account": 1.8 if attack and difficulty == "LOW" else 0.4,
            "seconds_since_prev_tx": float(rng.integers(20, 400 if attack else 80000)),
            "distinct_beneficiaries_last_24h": bens,
            "distinct_devices_last_7d": 3 if new_dev else 1,
            "account_tx_count_to_date": max(2, int(account_age / 30)),
            "campaign_step": int(p["campaign_step"]),
            "location_country": "IN",
            "location_region": str(rng.choice(regions)),
            "hour_of_day": hour,
            "day_of_week": int(rng.integers(0, 7)),
            "is_night": int(hour < 6 or hour >= 22),
        })
    return rows


def _score_rows(
    rows: List[Dict[str, Any]],
    model,
    builder: FeatureBuilder,
    feature_order: List[str],
    cats: List[str],
    mappings: Dict[str, Dict[str, int]],
    unseen: int,
) -> np.ndarray:
    vectors = [builder.to_model_vector(r, feature_order, cats, mappings, unseen) for r in rows]
    if model is None:
        return np.array([_heuristic_score(r) for r in rows], dtype=float)
    try:
        if model.model_type == "LightGBM":
            return np.asarray(model.model.predict(vectors), dtype=float)
        import xgboost as xgb
        dmat = xgb.DMatrix(vectors, feature_names=feature_order)
        return np.asarray(model.model.predict(dmat), dtype=float)
    except Exception:
        return np.array([_heuristic_score(r) for r in rows], dtype=float)


def _heuristic_score(row: Dict[str, Any]) -> float:
    s = 0.22
    s += 0.28 * row.get("is_new_beneficiary", 0)
    s += 0.18 * row.get("is_new_device", 0)
    s += 0.12 * min(1.0, row.get("velocity_score", 0))
    s += 0.08 * min(1.0, row.get("merchant_risk_score", 0))
    s += 0.06 * (1 if row.get("amount", 0) > 8000 else 0)
    return float(min(0.99, max(0.02, s)))


def _average_precision(y: np.ndarray, s: np.ndarray) -> float:
    if y.sum() == 0:
        return 0.0
    try:
        from sklearn.metrics import average_precision_score
        return float(average_precision_score(y, s))
    except Exception:
        order = np.argsort(-s)
        y_sorted = y[order]
        tp = np.cumsum(y_sorted)
        prec = tp / np.arange(1, len(y) + 1)
        rec_diff = np.diff(np.concatenate([[0], tp / y.sum()]))
        return float(np.sum(prec * rec_diff))


def _row_out(row: Dict[str, Any], score: float, bucket: str) -> Dict[str, Any]:
    return {
        "row_id": row["row_id"],
        "customer_id": row["customer_id"],
        "device_id": row["device_id"],
        "beneficiary_id": row["beneficiary_id"],
        "amount": row["amount"],
        "rail": row["payment_rail"],
        "region": row["location_region"],
        "is_new_beneficiary": bool(row["is_new_beneficiary"]),
        "is_new_device": bool(row["is_new_device"]),
        "score": round(float(score), 4),
        "bucket": bucket,
    }


def _build_graph(rows: List[Dict[str, Any]], scores: np.ndarray, mode: str, family: Dict[str, Any]) -> Dict[str, Any]:
    take = rows[: min(len(rows), 80)]
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    for i, row in enumerate(take):
        missed = float(scores[i]) < THRESHOLD
        for nid, kind in (
            (row["customer_id"], "customer"),
            (row["device_id"], "device"),
            (row["beneficiary_id"], "beneficiary"),
        ):
            node = nodes.setdefault(nid, {"id": nid, "kind": kind, "missed": False, "count": 0})
            node["count"] += 1
            node["missed"] = node["missed"] or missed
        edges.append({
            "source": row["customer_id"],
            "target": row["beneficiary_id"],
            "via": row["device_id"],
            "amount": row["amount"],
            "missed": missed,
        })
    return {
        "mode": mode,
        "title": f"{family.get('name')} entity links",
        "nodes": list(nodes.values()),
        "edges": edges[:120],
    }


def _build_image(family: Dict[str, Any], variant: Dict[str, Any], enabled: bool) -> Optional[Dict[str, Any]]:
    if not enabled:
        return None
    name = family.get("name") or "Novel family"
    fid = family.get("attack_id") or "NOV"
    desc = family.get("description") or variant.get("name") or "Synthetic listing"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 400" role="img">
  <rect width="640" height="400" fill="#f4f5f7"/>
  <rect x="24" y="24" width="280" height="352" rx="10" fill="#ffffff" stroke="#e5e7eb"/>
  <rect x="40" y="40" width="248" height="168" rx="6" fill="#eef1f4"/>
  <circle cx="164" cy="116" r="36" fill="#d8dde4"/>
  <path d="M120 168 L148 132 L176 158 L196 140 L208 168 Z" fill="#c5ccd6"/>
  <text x="40" y="236" fill="#0f1419" font-size="15" font-family="system-ui" font-weight="600">{_xml(name[:34])}</text>
  <text x="40" y="258" fill="#667085" font-size="11" font-family="ui-monospace">{_xml(fid)} · synthetic listing</text>
  <text x="40" y="286" fill="#384250" font-size="12" font-family="system-ui">{_xml(desc[:48])}</text>
  <text x="40" y="322" fill="#0f1419" font-size="20" font-family="system-ui" font-weight="640">₹4,250</text>
  <rect x="40" y="336" width="88" height="22" rx="4" fill="#d6001c"/>
  <text x="52" y="351" fill="#ffffff" font-size="11" font-family="system-ui">Buy now</text>
  <rect x="328" y="24" width="288" height="352" rx="10" fill="#ffffff" stroke="#e5e7eb"/>
  <text x="348" y="56" fill="#667085" font-size="11" font-family="system-ui">Generated evidence image</text>
  <text x="348" y="84" fill="#0f1419" font-size="16" font-family="system-ui" font-weight="600">AI listing artifact</text>
  <text x="348" y="120" fill="#384250" font-size="12" font-family="system-ui">Not a real product photo.</text>
  <text x="348" y="142" fill="#384250" font-size="12" font-family="system-ui">Used only as Red Team evidence</text>
  <text x="348" y="164" fill="#384250" font-size="12" font-family="system-ui">for visual / novel families.</text>
  <rect x="348" y="200" width="248" height="8" rx="4" fill="#eef1f4"/>
  <rect x="348" y="200" width="168" height="8" rx="4" fill="#d6001c"/>
  <text x="348" y="236" fill="#667085" font-size="11" font-family="ui-monospace">forensics score 0.71 · synthetic</text>
  <text x="348" y="268" fill="#384250" font-size="12" font-family="system-ui">Signals: texture repeat, EXIF empty,</text>
  <text x="348" y="288" fill="#384250" font-size="12" font-family="system-ui">identical lighting across SKUs.</text>
</svg>"""
    return {
        "kind": "listing",
        "title": f"{fid} generated image",
        "svg": svg,
        "caption": "Synthetic evidence image for this family. No real catalog or customer data.",
    }


def _xml(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_report(
    family: Dict[str, Any],
    variant: Dict[str, Any],
    difficulty: str,
    mode: str,
    detection: float,
    success: float,
    missed: List[Dict[str, Any]],
) -> Dict[str, Any]:
    new_ben = sum(1 for r in missed if r.get("is_new_beneficiary"))
    new_dev = sum(1 for r in missed if r.get("is_new_device"))
    behavior = (
        "normal device and amount → new / concentrated beneficiary"
        if new_ben >= new_dev
        else "new or shared device with otherwise ordinary payment shape"
    )
    finding = (
        f"{family.get('name')} ({variant.get('code')}, {difficulty}) "
        f"{'bypassed' if success > 0.1 else 'was mostly contained by'} the frozen Blue detector. "
        f"Attack success {success:.1%} on generated rows. Missed rows show {behavior}."
    )
    signals = family.get("detection_signals") or []
    return {
        "finding": finding,
        "behavior": behavior,
        "detected_signals": signals[:6],
        "red_next": (
            f"Raise stealth on {variant.get('name')} — keep device/amount in-distribution and "
            f"rotate beneficiaries more slowly."
            if success < 0.25
            else f"Scale the same {mode} pattern; Blue is missing concentrated beneficiary links."
        ),
        "blue_fix": (
            "Add beneficiary-concentration and new-payee features to the next hardening round. "
            "Do not use holdout F1 as the gate for this family."
        ),
        "handoff": "Open Blue Team defense with this run in session.",
    }


def run_summary(row: Any) -> Dict[str, Any]:
    return {
        "id": row.id,
        "mode": row.mode,
        "family_id": row.family_id,
        "family_name": row.family_name,
        "variant": row.variant,
        "variant_code": row.variant_code,
        "difficulty": row.difficulty,
        "population": row.population,
        "scale": row.scale,
        "seed": row.seed,
        "is_novel": row.is_novel,
        "generate_image": row.generate_image,
        "generated": row.generated,
        "detected": row.detected,
        "missed": row.missed,
        "attack_success": row.attack_success,
        "detection_rate": row.detection_rate,
        "precision": row.precision,
        "pr_auc": row.pr_auc,
        "threshold": row.threshold,
        "model_version": row.model_version,
        "created_at": row.created_at,
    }


def run_detail(row: Any) -> Dict[str, Any]:
    detail = run_summary(row)
    try:
        detail["result"] = json.loads(row.result_json or "{}")
    except json.JSONDecodeError:
        detail["result"] = {}
    return detail


def failing_context(db, run_id: Optional[str] = None, limit: int = 5) -> Dict[str, Any]:
    """Missed / bypassed evidence the chat uses to draft the next novel family."""
    from backend.platform.models import Campaign, RedTeamRun
    from sqlalchemy import desc

    runs = db.query(RedTeamRun).order_by(desc(RedTeamRun.created_at)).limit(20).all()
    failing_runs = [r for r in runs if (r.missed or 0) > 0]
    failing_runs.sort(key=lambda r: r.attack_success or 0, reverse=True)

    seed = None
    if run_id:
        seed = db.get(RedTeamRun, run_id)
    if seed is None and failing_runs:
        seed = failing_runs[0]

    seed_result: Dict[str, Any] = {}
    if seed:
        try:
            seed_result = json.loads(seed.result_json or "{}")
        except json.JSONDecodeError:
            seed_result = {}

    missed = (seed_result.get("missed") or [])[:8]
    n = len(missed) or 1
    new_ben = sum(1 for r in missed if r.get("is_new_beneficiary"))
    new_dev = sum(1 for r in missed if r.get("is_new_device"))
    amounts = [float(r.get("amount") or 0) for r in missed] or [0]

    campaigns = (
        db.query(Campaign)
        .filter(Campaign.outcome == "bypassed")
        .order_by(desc(Campaign.created_at))
        .limit(limit)
        .all()
    )

    return {
        "seed_run_id": seed.id if seed else None,
        "seed": {
            "id": seed.id,
            "family_id": seed.family_id,
            "family_name": seed.family_name,
            "variant_code": seed.variant_code,
            "difficulty": seed.difficulty,
            "mode": seed.mode,
            "generated": seed.generated,
            "missed": seed.missed,
            "attack_success": seed.attack_success,
            "behavior": (seed_result.get("behavior") or seed_result.get("report", {}).get("behavior")),
            "red_next": (seed_result.get("report") or {}).get("red_next"),
        } if seed else None,
        "pattern": {
            "new_beneficiary_share": round(new_ben / n, 3),
            "new_device_share": round(new_dev / n, 3),
            "mean_amount": round(sum(amounts) / len(amounts), 2),
            "miss_sample": missed[:5],
        } if seed else {},
        "failing_runs": [
            {
                "id": r.id,
                "family_id": r.family_id,
                "family_name": r.family_name,
                "variant_code": r.variant_code,
                "missed": r.missed,
                "attack_success": r.attack_success,
            }
            for r in failing_runs[:limit]
        ],
        "bypassed_campaigns": [
            {
                "id": c.id,
                "family_id": c.family_id,
                "family_name": c.family_name,
                "steps_bypassed": c.steps_bypassed,
                "selected_variant": c.selected_variant,
            }
            for c in campaigns
        ],
        "summary": _failing_summary(seed, seed_result, new_ben / n if seed else 0, new_dev / n if seed else 0),
    }


def _failing_summary(seed, result: Dict[str, Any], ben_share: float, dev_share: float) -> str:
    if not seed:
        return "No scored misses yet. Generate a known family first, then chat a mutation from what Blue missed."
    behavior = result.get("behavior") or "ordinary payment shape with a new payee"
    return (
        f"{seed.family_id} {seed.variant_code} missed {seed.missed} of {seed.generated} "
        f"({(seed.attack_success or 0):.1%} attack success). "
        f"Miss pattern: {behavior}. "
        f"{ben_share:.0%} of sampled misses used a new beneficiary; "
        f"{dev_share:.0%} used a new device."
    )


def chat_novel(message: str, context: Dict[str, Any], history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """Draft a novel family from failing evidence. Uses an LLM when configured, otherwise a mutation."""
    history = history or []
    llm_used = False
    draft = _draft_from_failing(message, context)
    reply = _offline_chat_reply(message, context, draft)

    llm_draft = _llm_chat_novel(message, context, history)
    if llm_draft:
        llm_used = True
        draft = {**draft, **{k: v for k, v in llm_draft.items() if v}}
        reply = llm_draft.get("reply") or reply

    return {"reply": reply, "draft": draft, "llm": llm_used, "context": {
        "summary": context.get("summary"),
        "seed_run_id": context.get("seed_run_id"),
        "failing_runs": context.get("failing_runs") or [],
    }}


def _draft_from_failing(message: str, context: Dict[str, Any]) -> Dict[str, Any]:
    text = (message or "").lower()
    seed = context.get("seed") or {}
    pattern = context.get("pattern") or {}
    parent = seed.get("family_name") or "failing family"
    parent_id = seed.get("family_id") or "UNK"
    behavior = seed.get("behavior") or "new / concentrated beneficiary with normal device and amount"
    want_image = _text_is_visual(text) or "image" in text
    want_network = "network" in text or "coordinat" in text or seed.get("mode") == "network"
    want_stealth = any(tok in text for tok in ("stealth", "camouflage", "slow", "seasoned", "high"))

    if pattern.get("new_beneficiary_share", 0) >= pattern.get("new_device_share", 0):
        mutation = "keep the new/concentrated beneficiary that Blue missed; hold device age and amount in-distribution"
        name = f"{parent_id} beneficiary miss-mutation"
    else:
        mutation = "keep the new or shared device Blue missed; keep amount ordinary"
        name = f"{parent_id} device miss-mutation"

    if want_image:
        mutation += "; attach a synthetic product-listing image as the cash-out cover"
        name = f"{parent_id} visual miss-mutation"
    if want_network:
        mutation += "; fan the same payee across a small customer cluster"
        name = f"{parent_id} coordinated miss-mutation"
    if want_stealth:
        mutation += "; rotate payees more slowly on seasoned accounts"

    description = (
        f"Novel family mutated from failing {parent_id} ({parent}). "
        f"Observed miss: {behavior}. Next step: {mutation}. "
        f"{(message or '').strip() or 'Operator asked to create a novel attack from existing misses.'}"
    )
    difficulty = "HIGH" if want_stealth else (seed.get("difficulty") or "MEDIUM")
    return {
        "name": name,
        "description": description,
        "lifecycle_stage": "Payment Initiation",
        "variants": [
            f"{parent_id} miss — camouflage",
            f"{parent_id} miss — coordination",
            f"{parent_id} miss — listing cover",
        ],
        "detection_signals": _signals_from_text(description),
        "generate_image": want_image,
        "mode": "network" if want_network else (seed.get("mode") or "standard"),
        "difficulty": difficulty,
        "based_on": parent_id,
        "based_on_run": seed.get("id"),
    }


def _offline_chat_reply(message: str, context: Dict[str, Any], draft: Dict[str, Any]) -> str:
    summary = context.get("summary") or "No failing run is loaded yet."
    if not context.get("seed"):
        return (
            f"{summary} After a run with misses, ask me to mutate that family. "
            "Example: “create a novel attack from these misses, add a listing image.”"
        )
    return (
        f"{summary}\n\n"
        f"Drafted **{draft['name']}**. {draft['description']}\n\n"
        "Use this family to fill the generate form, then run it on the frozen Blue detector. "
        "This is a mutation of what already bypassed — not a holdout F1 score."
    )


def _llm_chat_novel(
    message: str,
    context: Dict[str, Any],
    history: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    try:
        from backend.red_team.agent_helpers import get_llm, parse_llm_json
    except Exception:
        return None
    llm = get_llm()
    if not llm:
        return None
    prompt = (
        "You are the Red Team lab operator assistant. "
        "Draft ONE novel attack family mutated from existing MISSED / bypassed rows. "
        "Do not use training holdout F1. Return JSON only:\n"
        '{ "reply": "short operator note", "name": "", "description": "", '
        '"variants": ["..."], "detection_signals": ["..."], '
        '"generate_image": false, "mode": "standard|network", "difficulty": "LOW|MEDIUM|HIGH|ADAPTIVE" }\n\n'
        f"Failing evidence:\n{json.dumps(context.get('seed'))}\n"
        f"Pattern: {json.dumps(context.get('pattern'))}\n"
        f"Summary: {context.get('summary')}\n"
        f"Recent chat: {json.dumps(history[-6:])}\n"
        f"Operator: {message}"
    )
    try:
        raw = llm.invoke(prompt)
        content = raw.content if hasattr(raw, "content") else str(raw)
        data = parse_llm_json(content)
        if isinstance(data, dict) and data.get("name"):
            return data
    except Exception:
        return None
    return None


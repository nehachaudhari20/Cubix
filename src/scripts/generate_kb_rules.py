"""Generate data/knowledge/canonical/defense/rules.json from KB signals/controls."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "data" / "knowledge" / "canonical"


def feature_condition(fname: str) -> dict:
    bool_true = {"is_new_device", "is_new_beneficiary", "is_night", "auth_success"}
    count_fields = {
        "transaction_count_last_1h",
        "transaction_count_last_24h",
        "distinct_beneficiaries_last_24h",
        "distinct_devices_last_7d",
        "account_tx_count_to_date",
    }
    score_fields = {
        "velocity_score",
        "merchant_risk_score",
        "merchant_familiarity_score",
        "amount_to_avg_7d_ratio",
        "amount_zscore_account",
    }
    if fname in {"is_new_device", "is_new_beneficiary", "is_night"}:
        return {"field": fname, "op": "==", "value": True}
    if fname == "auth_success":
        return {"field": "auth_success", "op": "==", "value": False}
    if fname in count_fields:
        return {
            "field": fname,
            "op": ">=",
            "param": "velocity_limit_24h",
            "registry": "payment_initiation",
            "default": 5,
        }
    if fname == "device_age_days":
        return {
            "field": fname,
            "op": "<",
            "param": "device_age_threshold",
            "registry": "device_session",
            "default": 30,
        }
    if fname == "account_age_days":
        return {
            "field": fname,
            "op": "<",
            "param": "young_account_days",
            "registry": "identity_kyc",
            "default": 30,
        }
    if fname in score_fields or fname.endswith("_score") or fname.endswith("_ratio") or "zscore" in fname:
        return {"field": fname, "op": ">=", "value": 0.55}
    if fname in {"amount", "avg_amount_last_7d"}:
        return {
            "field": fname,
            "op": ">",
            "param": "amount_limit_tier1",
            "registry": "payment_initiation",
            "default": 25000,
        }
    if fname == "hour_of_day":
        return {"field": "is_night", "op": "==", "value": True}
    if fname == "day_of_week":
        return {"field": "day_of_week", "op": "in", "value": [5, 6]}
    if fname == "authentication_method":
        return {"field": "authentication_method", "op": "in", "value": ["none", "bypass", "sms"]}
    if fname == "payment_rail":
        return {"field": "payment_rail", "op": "in", "value": ["crypto", "wallet"]}
    if fname == "merchant_category_code":
        return {
            "field": "merchant_risk_score",
            "op": ">=",
            "param": "merchant_high_risk_threshold",
            "registry": "merchant",
            "default": 0.7,
        }
    return {"field": fname, "op": "truthy"}


def main() -> None:
    signals = json.loads((BASE / "defense" / "signals.json").read_text(encoding="utf-8"))["signals"]
    mappings = json.loads(
        (BASE / "defense" / "signal_feature_mappings.json").read_text(encoding="utf-8")
    )["signal_feature_mappings"]
    controls = json.loads((BASE / "defense" / "controls.json").read_text(encoding="utf-8"))["controls"]

    sig_features: dict[str, list[str]] = {}
    for mapping in mappings:
        sid = mapping.get("signal_id")
        if not sid:
            continue
        sig_features.setdefault(sid, [])
        for feat in mapping.get("feature_names") or []:
            if feat not in sig_features[sid]:
                sig_features[sid].append(feat)

    sig_to_controls: dict[str, list[str]] = defaultdict(list)
    for control in controls:
        for sid in control.get("detects_signal_ids") or []:
            sig_to_controls[sid].append(control["control_id"])

    engine_by_feature = {
        "is_new_device": "device",
        "device_age_days": "device",
        "distinct_devices_last_7d": "device",
        "account_age_days": "identity",
        "auth_success": "auth",
        "authentication_method": "auth",
        "is_new_beneficiary": "beneficiary",
        "distinct_beneficiaries_last_24h": "beneficiary",
        "amount": "payment_init",
        "velocity_score": "payment_init",
        "transaction_count_last_1h": "payment_init",
        "transaction_count_last_24h": "payment_init",
        "hour_of_day": "payment_init",
        "is_night": "payment_init",
        "day_of_week": "payment_init",
        "payment_rail": "payment_init",
        "amount_to_avg_7d_ratio": "payment_init",
        "amount_zscore_account": "payment_init",
        "avg_amount_last_7d": "payment_init",
        "account_tx_count_to_date": "identity",
        "merchant_category_code": "acquirer",
        "merchant_risk_score": "acquirer",
        "merchant_familiarity_score": "acquirer",
    }
    category_engine = {
        "Device": "device",
        "Device/Session": "device",
        "Session": "auth",
        "Identity": "identity",
        "Identity/KYC": "identity",
        "Transaction": "payment_init",
        "Temporal": "payment_init",
        "Behavioral": "risk",
        "Network": "mule",
        "Graph/Network": "mule",
        "Network/Graph": "mule",
        "Merchant": "acquirer",
        "API": "gateway",
        "Account": "identity",
        "Documentation": "identity",
        "Human Intent": "agent_commerce",
        "Agent Identity": "agent_commerce",
        "Agent Permissions": "agent_commerce",
    }
    category_risk = {
        "Human Intent": 0.28,
        "Agent Identity": 0.26,
        "Agent Permissions": 0.26,
        "Device": 0.18,
        "Device/Session": 0.18,
        "Session": 0.16,
        "Identity": 0.22,
        "Identity/KYC": 0.22,
        "Documentation": 0.2,
        "Transaction": 0.2,
        "Temporal": 0.15,
        "Behavioral": 0.18,
        "Network": 0.22,
        "Graph/Network": 0.22,
        "Network/Graph": 0.22,
        "Merchant": 0.2,
        "API": 0.18,
        "Account": 0.16,
    }

    rules: list[dict] = []

    threshold_rules = [
        ("RUL-AMOUNT-T1", "Amount exceeds tier 1", ["payment_init"],
         [{"field": "amount", "op": ">", "param": "amount_limit_tier1", "registry": "payment_initiation", "default": 25000}],
         {"param": "amount_tier1_risk", "registry": "payment_initiation", "default": 0.25},
         "amount_exceeds_tier1", "CTL-0105", 0.75),
        ("RUL-AMOUNT-T2", "Amount exceeds tier 2", ["payment_init"],
         [{"field": "amount", "op": ">", "param": "amount_limit_tier2", "registry": "payment_initiation", "default": 50000}],
         {"param": "amount_tier2_risk", "registry": "payment_initiation", "default": 0.25},
         "amount_exceeds_tier2", "CTL-0105", 0.75),
        ("RUL-AMOUNT-T3", "Amount exceeds tier 3", ["payment_init"],
         [{"field": "amount", "op": ">", "param": "amount_limit_tier3", "registry": "payment_initiation", "default": 100000}],
         {"param": "amount_tier3_risk", "registry": "payment_initiation", "default": 0.25},
         "amount_exceeds_tier3", "CTL-0105", 0.75),
        ("RUL-VEL-T1", "Velocity exceeds 24h limit", ["payment_init"],
         [{"field": "transaction_count_last_24h", "op": ">", "param": "velocity_limit_24h", "registry": "payment_initiation", "default": 5}],
         {"param": "velocity_tier1_risk", "registry": "payment_initiation", "default": 0.25},
         "velocity_exceeds_limit_24h", "CTL-0013", 0.5),
        ("RUL-VEL-T2", "Velocity exceeds high risk", ["payment_init"],
         [{"field": "transaction_count_last_24h", "op": ">", "param": "velocity_high_risk", "registry": "payment_initiation", "default": 10}],
         {"param": "velocity_tier2_risk", "registry": "payment_initiation", "default": 0.5},
         "velocity_exceeds_high_24h", "CTL-0013", 0.5),
        ("RUL-DEV-UNKNOWN", "Unknown device", ["device"],
         [{"field": "is_unknown_device", "op": "==", "value": True}],
         {"param": "unknown_device_risk", "registry": "device_session", "default": 0.3},
         "unknown_device", "CTL-0096", 0.4),
        ("RUL-DEV-NEW", "New device", ["device"],
         [{"field": "is_new_device", "op": "==", "value": True}],
         {"param": "new_device_risk", "registry": "device_session", "default": 0.2},
         "new_device_less_than_7_days", "CTL-0096", 0.4),
        ("RUL-DEV-AGE", "Young device age", ["device"],
         [{"field": "device_age_days", "op": "<", "param": "device_age_threshold", "registry": "device_session", "default": 30},
          {"field": "is_new_device", "op": "==", "value": False}],
         {"param": "device_age_risk", "registry": "device_session", "default": 0.1},
         "device_age_less_than_threshold", "CTL-0096", 0.4),
        ("RUL-ID-TRUST", "Low trust score", ["identity"],
         [{"field": "trust_score", "op": "<", "param": "low_trust_threshold", "registry": "identity_kyc", "default": 0.35}],
         {"param": "low_trust_risk", "registry": "identity_kyc", "default": 0.25},
         "low_trust_score", "CTL-0172", 0.5),
        ("RUL-ID-UNVERIFIED", "Unverified identity", ["identity"],
         [{"field": "verified", "op": "==", "value": False}],
         {"param": "unverified_identity_risk", "registry": "identity_kyc", "default": 0.35},
         "unverified_identity", "CTL-0018", 0.5),
        ("RUL-ID-YOUNG", "Young account low trust", ["identity"],
         [{"field": "account_age_days", "op": "<", "param": "young_account_days", "registry": "identity_kyc", "default": 30},
          {"field": "trust_score", "op": "<", "value": 0.7}],
         {"param": "young_account_risk", "registry": "identity_kyc", "default": 0.15},
         "account_younger_than_threshold", "CTL-0268", 0.5),
        ("RUL-ID-SYNTH", "Synthetic identity pattern", ["identity"],
         [{"field": "synthetic_identity_flag", "op": "==", "value": True}],
         {"param": "synthetic_identity_risk", "registry": "identity_kyc", "default": 0.3},
         "synthetic_identity_pattern", "CTL-0018", 0.5),
        ("RUL-AML-STRUCT", "Structuring amount band", ["aml"],
         [{"field": "amount", "op": ">=", "param": "structuring_min_amount", "registry": "aml_compliance", "default": 20000},
          {"field": "amount", "op": "<=", "param": "structuring_max_amount", "registry": "aml_compliance", "default": 24999}],
         {"param": "structuring_risk", "registry": "aml_compliance", "default": 0.35},
         "structuring_amount_band", "CTL-0276", 0.5),
        ("RUL-AML-HIGH", "High amount AML", ["aml"],
         [{"field": "amount", "op": ">=", "param": "high_amount_aml_threshold", "registry": "aml_compliance", "default": 50000},
          {"field": "trust_score", "op": "<", "param": "low_trust_threshold", "registry": "identity_kyc", "default": 0.35}],
         {"param": "high_amount_aml_risk", "registry": "aml_compliance", "default": 0.25},
         "high_amount_low_trust", "CTL-0276", 0.5),
        ("RUL-AML-ROUND", "Round amount pattern", ["aml"],
         [{"field": "round_amount_flag", "op": "==", "value": True}],
         {"param": "round_amount_risk", "registry": "aml_compliance", "default": 0.1},
         "round_amount_pattern", "CTL-0276", 0.5),
        ("RUL-MERCH-HIGH", "Merchant high risk", ["acquirer"],
         [{"field": "merchant_risk_score", "op": ">=", "param": "merchant_high_risk_threshold", "registry": "merchant", "default": 0.7}],
         {"param": "merchant_high_risk_contribution", "registry": "merchant", "default": 0.25},
         "merchant_high_risk", "CTL-0323", 0.5),
        ("RUL-MERCH-VHIGH", "Merchant very high risk", ["acquirer"],
         [{"field": "merchant_risk_score", "op": ">=", "param": "merchant_very_high_risk_threshold", "registry": "merchant", "default": 0.9}],
         {"param": "merchant_very_high_risk_contribution", "registry": "merchant", "default": 0.25},
         "merchant_very_high_risk", "CTL-0323", 0.5),
        ("RUL-MULE-NEW-BEN", "New beneficiary high amount", ["mule", "beneficiary"],
         [{"field": "is_new_beneficiary", "op": "==", "value": True},
          {"field": "amount", "op": ">=", "param": "new_beneficiary_amount_threshold", "registry": "mule_cashout", "default": 25000}],
         {"param": "new_beneficiary_risk", "registry": "mule_cashout", "default": 0.35},
         "new_beneficiary_high_amount", "CTL-0009", 0.5),
        ("RUL-MULE-SHARED", "Shared beneficiary payers", ["mule"],
         [{"field": "shared_beneficiary_payers", "op": ">=", "param": "shared_beneficiary_customers_threshold", "registry": "mule_cashout", "default": 3}],
         {"param": "shared_beneficiary_risk", "registry": "mule_cashout", "default": 0.4},
         "shared_beneficiary_payers", "CTL-0009", 0.5),
    ]

    for rule_id, name, engines, conditions, risk, trigger, control_id, cap in threshold_rules:
        rules.append(
            {
                "rule_id": rule_id,
                "name": name,
                "rule_type": "threshold",
                "engines": engines,
                "signal_ids": [],
                "logic": "all",
                "conditions": conditions,
                "risk_contribution": risk,
                "trigger": trigger,
                "control_id": control_id,
                "expected_control_ids": [control_id],
                "risk_cap": cap,
                "enabled": True,
                "origin": "migrated_threshold",
            }
        )

    composites = [
        (
            "RUL-COMP-DEV-ID-PAY",
            "New device + low trust + high amount",
            ["device", "identity", "payment_init"],
            [
                {"field": "is_new_device", "op": "==", "value": True},
                {"field": "trust_score", "op": "<", "param": "low_trust_threshold", "registry": "identity_kyc", "default": 0.35},
                {"field": "amount", "op": ">", "param": "amount_limit_tier1", "registry": "payment_initiation", "default": 25000},
            ],
            {"default": 0.45},
            "composite_new_device_low_trust_high_amount",
            "CTL-0096",
            ["CTL-0096", "CTL-0172", "CTL-0105"],
        ),
        (
            "RUL-COMP-BEN-VEL-AML",
            "New beneficiary + velocity + structuring band",
            ["beneficiary", "payment_init", "aml"],
            [
                {"field": "is_new_beneficiary", "op": "==", "value": True},
                {"field": "transaction_count_last_24h", "op": ">", "param": "velocity_limit_24h", "registry": "payment_initiation", "default": 5},
                {"field": "amount", "op": ">=", "param": "structuring_min_amount", "registry": "aml_compliance", "default": 20000},
            ],
            {"default": 0.5},
            "composite_beneficiary_velocity_structuring",
            "CTL-0009",
            ["CTL-0009", "CTL-0013", "CTL-0276"],
        ),
        (
            "RUL-COMP-GW-ACQ-RISK",
            "Gateway flags + high merchant risk",
            ["gateway", "acquirer", "risk"],
            [
                {"field": "journey_gateway_flag_count", "op": ">=", "value": 1},
                {"field": "merchant_risk_score", "op": ">=", "param": "merchant_high_risk_threshold", "registry": "merchant", "default": 0.7},
            ],
            {"default": 0.4},
            "composite_gateway_merchant_risk",
            "CTL-0323",
            ["CTL-0323"],
        ),
        (
            "RUL-COMP-GENAI-PAYMENT",
            "GenAI load-bearing + payment initiation",
            ["agent_commerce", "payment_init", "risk"],
            [
                {"field": "genai_load_bearing_flag", "op": "==", "value": True},
                {"field": "amount", "op": ">", "param": "amount_limit_tier1", "registry": "payment_initiation", "default": 25000},
            ],
            {"default": 0.42},
            "composite_genai_payment",
            "CTL-0236",
            ["CTL-0236", "CTL-0105"],
        ),
        (
            "RUL-COMP-JOURNEY-FAILS",
            "Multi-engine journey flags without early block",
            ["device", "identity", "payment_init", "aml", "risk"],
            [
                {"field": "journey_flag_engines", "op": ">=", "value": 3},
                {"field": "journey_early_block", "op": "==", "value": False},
            ],
            {"default": 0.35},
            "composite_journey_multi_engine_flags",
            "CTL-0140",
            ["CTL-0140"],
        ),
        (
            "RUL-COMP-MULE-YOUNG",
            "Young account + mule cashout pattern",
            ["identity", "mule", "beneficiary"],
            [
                {"field": "account_age_days", "op": "<", "param": "young_account_days", "registry": "identity_kyc", "default": 30},
                {"field": "amount", "op": ">=", "param": "new_beneficiary_amount_threshold", "registry": "mule_cashout", "default": 25000},
                {"field": "is_new_beneficiary", "op": "==", "value": True},
            ],
            {"default": 0.48},
            "composite_young_account_mule",
            "CTL-0009",
            ["CTL-0268", "CTL-0009"],
        ),
    ]

    for rule_id, name, engines, conditions, risk, trigger, control_id, expected in composites:
        rules.append(
            {
                "rule_id": rule_id,
                "name": name,
                "rule_type": "composite",
                "engines": engines,
                "signal_ids": [],
                "logic": "all",
                "conditions": conditions,
                "risk_contribution": risk,
                "trigger": trigger,
                "control_id": control_id,
                "expected_control_ids": expected,
                "risk_cap": 0.6,
                "enabled": True,
                "origin": "composite",
            }
        )

    for sig in signals:
        sid = sig["signal_id"]
        feats = sig_features.get(sid, [])
        cat = sig.get("category") or "Behavioral"
        engines = sorted(
            {
                engine_by_feature.get(f, category_engine.get(cat, "risk"))
                for f in feats
            }
            or {category_engine.get(cat, "risk")}
        )
        ctl_ids = sig_to_controls.get(sid, [])
        control_id = ctl_ids[0] if ctl_ids else None
        if feats:
            conditions = [feature_condition(f) for f in feats]
            logic = "any"
            origin = "signal_mapped"
        else:
            conditions = [
                {"field": "family_signal_ids", "op": "contains", "value": sid},
                {"field": "signal_context_active", "op": "==", "value": True},
            ]
            logic = "all"
            origin = "signal_context"

        trigger = f"signal_{sid.lower().replace('-', '_')}"
        rules.append(
            {
                "rule_id": f"RUL-{sid}",
                "name": sig.get("name") or sid,
                "rule_type": "signal",
                "engines": engines,
                "signal_ids": [sid],
                "logic": logic,
                "conditions": conditions,
                "risk_contribution": {"default": round(category_risk.get(cat, 0.15), 4)},
                "trigger": trigger,
                "control_id": control_id,
                "expected_control_ids": ctl_ids[:5],
                "risk_cap": 0.35,
                "category": cat,
                "enabled": True,
                "origin": origin,
                "mapped_features": feats,
            }
        )

    out = {
        "registry_version": "2.0",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "description": "Data-driven sandbox rules compiled from KB signals, controls, and parameter bindings.",
        "counts": {
            "total": len(rules),
            "threshold": sum(1 for r in rules if r["rule_type"] == "threshold"),
            "composite": sum(1 for r in rules if r["rule_type"] == "composite"),
            "signal": sum(1 for r in rules if r["rule_type"] == "signal"),
        },
        "rules": rules,
    }
    path = BASE / "defense" / "rules.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {path} rules={len(rules)} {out['counts']}")


if __name__ == "__main__":
    main()

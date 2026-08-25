"""
Data-driven RuleEngine — loads rules.json from KB at boot.

Replaces hardcoded IF-ELSE rule classes with declarative conditions.
Thresholds resolve from CompiledControlSet.parameter_bindings / thresholds.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from .compiled_controls import CompiledControlSet, get_global_compiled_controls


OPS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: float(a or 0) > float(b),
    ">=": lambda a, b: float(a or 0) >= float(b),
    "<": lambda a, b: float(a or 0) < float(b),
    "<=": lambda a, b: float(a or 0) <= float(b),
    "in": lambda a, b: a in (b or []),
    "contains": lambda a, b: b in (a or []),
    "truthy": lambda a, _b: bool(a),
}


@dataclass
class RuleHit:
    rule_id: str
    trigger: str
    control_id: Optional[str]
    signal_ids: List[str]
    engines: List[str]
    rule_type: str
    risk_contribution: float
    expected_control_ids: List[str] = field(default_factory=list)


@dataclass
class RuleEngineResult:
    risk_contribution: float
    triggered_rules: List[str]
    triggered_controls: List[str]
    triggered_signals: List[str]
    hits: List[RuleHit]
    control_gaps: Dict[str, Any]
    thresholds_used: Dict[str, Any]
    rule_details: List[Dict[str, Any]]


class RuleEngine:
    """Evaluate KB rules against a feature context."""

    def __init__(
        self,
        rules: Optional[List[Dict[str, Any]]] = None,
        compiled_controls: Optional[CompiledControlSet] = None,
        kb_path: str = "data/knowledge/canonical",
    ):
        self.compiled = compiled_controls or get_global_compiled_controls()
        if rules is not None:
            self.rules = [r for r in rules if r.get("enabled", True)]
        else:
            self.rules = self._load_rules(kb_path)
        self._param_index = self._build_param_index()

    @staticmethod
    def _load_rules(kb_path: str) -> List[Dict[str, Any]]:
        path = Path(kb_path) / "defense" / "rules.json"
        if not path.exists():
            # Flat layout fallback
            path = Path(kb_path) / "rules.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [r for r in data.get("rules", []) if r.get("enabled", True)]

    def _build_param_index(self) -> Dict[str, Any]:
        """Index parameter values from parameter_bindings + registry thresholds."""
        index: Dict[str, Any] = {}
        compiled = self.compiled
        if compiled is None:
            return index

        for registry, values in (compiled.thresholds or {}).items():
            for key, val in values.items():
                if key.startswith("_"):
                    continue
                index[f"{registry}.{key}"] = val
                index[key] = val  # last-write wins for bare keys

        for binding in (compiled.parameter_bindings or {}).values():
            resolved = binding.get("resolved") or {}
            for key, val in resolved.items():
                index[key] = val
                ref = binding.get("sandbox_config_ref") or ""
                # Prefer binding-resolved values as source of truth
                if "EXECUTABLE_DEFAULTS." in ref:
                    parts = ref.replace("EXECUTABLE_DEFAULTS.", "").split(".")
                    if parts:
                        index[f"{parts[0]}.{key}"] = val
        return index

    def resolve_threshold(
        self,
        param: Optional[str],
        registry: Optional[str] = None,
        default: Any = None,
    ) -> Any:
        """Resolve a threshold solely via KB parameter_bindings / compiled thresholds."""
        if param is None:
            return default
        if registry:
            keyed = f"{registry}.{param}"
            if keyed in self._param_index:
                return self._param_index[keyed]
        if param in self._param_index:
            return self._param_index[param]
        # Try parameter_bindings by name match
        if self.compiled:
            for binding in (self.compiled.parameter_bindings or {}).values():
                resolved = binding.get("resolved") or {}
                if param in resolved:
                    return resolved[param]
        return default

    def evaluate(
        self,
        context: Dict[str, Any],
        *,
        expected_controls: Optional[Sequence[str]] = None,
        engines: Optional[Sequence[str]] = None,
        rule_types: Optional[Sequence[str]] = None,
    ) -> RuleEngineResult:
        """Evaluate enabled rules; optionally filter by engine or type."""
        engine_filter: Optional[Set[str]] = set(engines) if engines else None
        type_filter: Optional[Set[str]] = set(rule_types) if rule_types else None

        hits: List[RuleHit] = []
        thresholds_used: Dict[str, Any] = {}
        risk_by_cap: Dict[str, float] = {}  # group soft-caps by primary engine

        for rule in self.rules:
            if type_filter and rule.get("rule_type") not in type_filter:
                continue
            rule_engines = rule.get("engines") or []
            if engine_filter and rule_engines and not (set(rule_engines) & engine_filter):
                # Composites need all engines conceptually present in path OR no filter
                if rule.get("rule_type") != "composite":
                    continue
                if not (set(rule_engines) & engine_filter):
                    continue

            fired, used = self._eval_rule(rule, context)
            thresholds_used.update(used)
            if not fired:
                continue

            risk_spec = rule.get("risk_contribution") or {}
            risk = float(
                self.resolve_threshold(
                    risk_spec.get("param"),
                    risk_spec.get("registry"),
                    risk_spec.get("default", 0.15),
                )
            )
            # Soft-cap per rule type bucket
            cap = float(rule.get("risk_cap") or 1.0)
            bucket = rule.get("rule_type") or "other"
            risk_by_cap[bucket] = min(cap, risk_by_cap.get(bucket, 0.0) + risk)

            hits.append(
                RuleHit(
                    rule_id=rule.get("rule_id") or "",
                    trigger=rule.get("trigger") or rule.get("rule_id") or "",
                    control_id=rule.get("control_id"),
                    signal_ids=list(rule.get("signal_ids") or []),
                    engines=list(rule_engines),
                    rule_type=rule.get("rule_type") or "threshold",
                    risk_contribution=risk,
                    expected_control_ids=list(rule.get("expected_control_ids") or []),
                )
            )

        total_risk = min(1.0, sum(risk_by_cap.values()))
        triggered_rules = [h.trigger for h in hits]
        triggered_controls = []
        seen_ctl: Set[str] = set()
        for h in hits:
            ctl = h.control_id
            if ctl and ctl not in seen_ctl:
                seen_ctl.add(ctl)
                triggered_controls.append(ctl)
            for extra in h.expected_control_ids:
                if extra and extra not in seen_ctl:
                    # only count as triggered if rule itself fired with that control
                    pass

        # Resolve through compiled trigger map when available
        if self.compiled is not None:
            triggered_controls = self.compiled.resolve_triggers(
                [c for c in triggered_controls if c] + triggered_rules
            )
            # Keep only CTL-* ids
            triggered_controls = [c for c in triggered_controls if str(c).startswith("CTL-")]
            # Dedupe preserve order
            deduped: List[str] = []
            seen: Set[str] = set()
            for c in triggered_controls:
                if c not in seen:
                    seen.add(c)
                    deduped.append(c)
            triggered_controls = deduped

        triggered_signals: List[str] = []
        seen_sig: Set[str] = set()
        for h in hits:
            for sid in h.signal_ids:
                if sid not in seen_sig:
                    seen_sig.add(sid)
                    triggered_signals.append(sid)

        # Expected controls: caller + union of fired rule expected sets for composites
        expected: List[str] = list(expected_controls or [])
        if not expected:
            family_expected = context.get("expected_controls") or context.get("targeted_control_ids") or []
            expected = list(family_expected)

        control_gaps = self.detect_control_gaps(triggered_controls, expected)

        rule_details = [
            {
                "rule_set": "kb_rule_engine",
                "rule_id": h.rule_id,
                "rule_type": h.rule_type,
                "engines": h.engines,
                "risk_contribution": round(h.risk_contribution, 4),
                "triggered_rules": [h.trigger],
                "control_id": h.control_id,
                "signal_ids": h.signal_ids,
            }
            for h in hits
        ]

        return RuleEngineResult(
            risk_contribution=round(total_risk, 4),
            triggered_rules=triggered_rules,
            triggered_controls=triggered_controls,
            triggered_signals=triggered_signals,
            hits=hits,
            control_gaps=control_gaps,
            thresholds_used=thresholds_used,
            rule_details=rule_details,
        )

    def _eval_rule(
        self, rule: Dict[str, Any], context: Dict[str, Any]
    ) -> tuple[bool, Dict[str, Any]]:
        # Signal rules only fire for the family's observable signals (or active GenAI context)
        if rule.get("rule_type") == "signal":
            sig_ids = set(rule.get("signal_ids") or [])
            family_sigs = set(context.get("family_signal_ids") or [])
            if family_sigs:
                if not (sig_ids & family_sigs):
                    return False, {}
            elif not context.get("signal_context_active"):
                return False, {}

        conditions = rule.get("conditions") or []
        if not conditions:
            return False, {}
        logic = (rule.get("logic") or "all").lower()
        used: Dict[str, Any] = {}
        results: List[bool] = []
        for cond in conditions:
            ok, meta = self._eval_condition(cond, context)
            results.append(ok)
            used.update(meta)
        if logic == "any":
            return any(results), used
        return all(results), used

    def _eval_condition(
        self, cond: Dict[str, Any], context: Dict[str, Any]
    ) -> tuple[bool, Dict[str, Any]]:
        field_name = cond.get("field")
        op = cond.get("op") or "=="
        used: Dict[str, Any] = {}

        if "param" in cond:
            rhs = self.resolve_threshold(
                cond.get("param"),
                cond.get("registry"),
                cond.get("default"),
            )
            used[cond["param"]] = rhs
        else:
            rhs = cond.get("value")

        lhs = context.get(field_name) if field_name else None
        fn = OPS.get(op)
        if fn is None:
            return False, used
        try:
            if op == "truthy":
                return bool(lhs), used
            return bool(fn(lhs, rhs)), used
        except (TypeError, ValueError):
            return False, used

    @staticmethod
    def detect_control_gaps(
        triggered_controls: Sequence[str],
        expected_controls: Sequence[str],
    ) -> Dict[str, Any]:
        """Compare triggered vs expected KB controls (real-time gap detection)."""
        triggered = {c for c in triggered_controls if c}
        expected = {c for c in expected_controls if c}
        missing = sorted(expected - triggered)
        unexpected = sorted(triggered - expected)
        covered = sorted(expected & triggered)
        coverage = (len(covered) / len(expected)) if expected else 1.0
        return {
            "expected_controls": sorted(expected),
            "triggered_controls": sorted(triggered),
            "missing_controls": missing,
            "unexpected_controls": unexpected,
            "covered_controls": covered,
            "coverage": round(coverage, 4),
            "has_gap": bool(missing),
            "gap_count": len(missing),
        }

    def stats(self) -> Dict[str, int]:
        counts: Dict[str, int] = {"total": len(self.rules)}
        for rule in self.rules:
            rt = rule.get("rule_type") or "other"
            counts[rt] = counts.get(rt, 0) + 1
        return counts

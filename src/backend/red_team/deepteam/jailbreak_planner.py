"""Tree / Crescendo / Sequential jailbreak planners (DeepTeam-inspired). Phase 2."""

from __future__ import annotations

from typing import Any, Dict, List

from backend.red_team.schemas import AttackPlan, PlanStep

from .schemas import JailbreakStrategy


class JailbreakPlanner:
    """Produce multi-step or parallel plans from a KB attack family."""

    def plan(
        self,
        attack_family: Dict[str, Any],
        strategy: JailbreakStrategy = JailbreakStrategy.CRESCENDO,
    ) -> List[AttackPlan]:
        if strategy == JailbreakStrategy.TREE:
            return self._tree_plans(attack_family)
        if strategy == JailbreakStrategy.SEQUENTIAL:
            return [self._sequential_plan(attack_family)]
        return [self._crescendo_plan(attack_family)]

    def _crescendo_plan(self, family: Dict[str, Any]) -> AttackPlan:
        attack_id = family.get("attack_id", "UNKNOWN")
        return AttackPlan(
            campaign_name=f"Crescendo {attack_id}",
            objective="Multi-stage trust build then bust-out",
            target_stages=[family.get("lifecycle_stage") or "Authorization"],
            primary_family=attack_id,
            selected_variant=(family.get("variants") or ["default"])[0],
            steps=[
                PlanStep(step=1, action_type="register_customer", action="Register customer",
                         target_control="KYC", payload_template={"trust_score": 0.65},
                         expected_outcome="PASS", rationale="Create payer identity"),
                PlanStep(step=2, action_type="register_device", action="Register device",
                         target_control="Device trust", payload_template={"device_age_days": 0},
                         expected_outcome="PASS", rationale="Establish device footprint"),
                PlanStep(step=3, action_type="authenticate", action="Authenticate",
                         target_control="Authentication", payload_template={},
                         expected_outcome="PASS", rationale="Build session trust"),
                PlanStep(step=4, action_type="initiate_payment", action="Low-value payment",
                         target_control="Velocity", payload_template={"amount": 2500},
                         expected_outcome="ALLOW", rationale="Low-and-slow probe"),
                PlanStep(step=5, action_type="initiate_payment", action="High-value payment",
                         target_control="Amount limit", payload_template={"amount": 35000},
                         expected_outcome="ALLOW", rationale="Bust-out after trust build"),
            ],
            success_criteria="High-value payment ALLOW",
            estimated_complexity="high",
            reasoning="Crescendo: customer -> device -> auth -> low pay -> high pay",
        )

    def _sequential_plan(self, family: Dict[str, Any]) -> AttackPlan:
        attack_id = family.get("attack_id", "UNKNOWN")
        return AttackPlan(
            campaign_name=f"Sequential {attack_id}",
            objective="Cross-stage composite attack",
            target_stages=[family.get("lifecycle_stage") or "Payment Initiation"],
            primary_family=attack_id,
            selected_variant=(family.get("variants") or ["default"])[0],
            steps=[
                PlanStep(step=1, action_type="register_customer", action="Register customer",
                         target_control="KYC", payload_template={"trust_score": 0.55},
                         expected_outcome="PASS", rationale="Create identity"),
                PlanStep(step=2, action_type="register_device", action="Register device",
                         target_control="Device", payload_template={},
                         expected_outcome="PASS", rationale="Bind device"),
                PlanStep(step=3, action_type="onboard_merchant", action="Onboard merchant",
                         target_control="Merchant KYB", payload_template={"mcc": "5411"},
                         expected_outcome="PASS", rationale="Merchant setup"),
                PlanStep(step=4, action_type="initiate_payment", action="High-value payment",
                         target_control="Authorization", payload_template={"amount": 45000},
                         expected_outcome="ALLOW", rationale="Exploit built state"),
            ],
            success_criteria="Final payment ALLOW",
            estimated_complexity="high",
            reasoning="Sequential cross-stage composite",
        )

    def _tree_plans(self, family: Dict[str, Any]) -> List[AttackPlan]:
        attack_id = family.get("attack_id", "UNKNOWN")
        variant = (family.get("variants") or ["default"])[0]
        base = dict(
            target_stages=[family.get("lifecycle_stage") or "Authorization"],
            primary_family=attack_id,
            selected_variant=variant,
            estimated_complexity="medium",
        )
        return [
            AttackPlan(
                campaign_name=f"Tree-Amount {attack_id}",
                objective="Amount threshold attack branch",
                steps=[
                    PlanStep(step=1, action_type="register_customer", action="Register customer",
                             target_control="KYC", payload_template={"trust_score": 0.65},
                             expected_outcome="PASS", rationale="Setup payer"),
                    PlanStep(step=2, action_type="register_device", action="Register device",
                             target_control="Device", payload_template={},
                             expected_outcome="PASS", rationale="Bind device"),
                    PlanStep(step=3, action_type="initiate_payment", action="Amount spike",
                             target_control="Per-transaction amount limits",
                             payload_template={"amount": 50000}, expected_outcome="ALLOW",
                             rationale="Amount branch"),
                ],
                success_criteria="ALLOW via amount mutation",
                reasoning="Tree branch: amount",
                **base,
            ),
            AttackPlan(
                campaign_name=f"Tree-Velocity {attack_id}",
                objective="Velocity burst branch",
                steps=[
                    PlanStep(step=1, action_type="register_customer", action="Register customer",
                             target_control="KYC", payload_template={"trust_score": 0.65},
                             expected_outcome="PASS", rationale="Setup payer"),
                    PlanStep(step=2, action_type="register_device", action="Register device",
                             target_control="Device", payload_template={},
                             expected_outcome="PASS", rationale="Bind device"),
                    PlanStep(step=3, action_type="initiate_payment", action="Velocity burst",
                             target_control="Velocity rules",
                             payload_template={"amount": 8000, "velocity_burst": True},
                             expected_outcome="ALLOW", rationale="Velocity branch"),
                ],
                success_criteria="ALLOW via velocity",
                reasoning="Tree branch: velocity",
                **base,
            ),
            AttackPlan(
                campaign_name=f"Tree-Beneficiary {attack_id}",
                objective="New beneficiary branch",
                steps=[
                    PlanStep(step=1, action_type="register_customer", action="Register customer",
                             target_control="KYC", payload_template={"trust_score": 0.65},
                             expected_outcome="PASS", rationale="Setup payer"),
                    PlanStep(step=2, action_type="register_device", action="Register device",
                             target_control="Device", payload_template={},
                             expected_outcome="PASS", rationale="Bind device"),
                    PlanStep(step=3, action_type="link_beneficiary", action="Link beneficiary",
                             target_control="Beneficiary verification", payload_template={},
                             expected_outcome="PASS", rationale="New payee"),
                    PlanStep(step=4, action_type="initiate_payment", action="Pay new beneficiary",
                             target_control="Mule detection", payload_template={"amount": 35000},
                             expected_outcome="ALLOW", rationale="Beneficiary branch"),
                ],
                success_criteria="ALLOW via beneficiary mutation",
                reasoning="Tree branch: beneficiary",
                **base,
            ),
        ]

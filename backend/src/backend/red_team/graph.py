"""
Red Team LangGraph Workflow
Orchestrates the complete pipeline against the real Payment Sandbox.
"""

import os
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import RedTeamState
from .sandbox_client import SandboxClient
from .deepteam.linear_mutator import LinearMutator
from .agents.threat_hunter import ThreatHunter
from .agents.attack_planner import AttackPlanner
from .agents.attack_generator import AttackGenerator
from .agents.failure_analyzer import FailureAnalyzer
from .agents.memory_agent import MemoryAgent
from .agents.strategy_layer import StrategyLayer
from .schemas import Hypothesis, AttackPlan, ActionPayload, AnalysisResult


class RedTeamGraphState(TypedDict):
    """State passed between graph nodes."""
    hypothesis: Optional[Dict[str, Any]]
    hypotheses_queue: List[Dict[str, Any]]
    plan: Optional[Dict[str, Any]]
    plan_branches: List[Dict[str, Any]]
    current_branch_index: int
    payloads: List[Dict[str, Any]]
    current_payload_index: int
    sandbox_response: Optional[Dict[str, Any]]
    analysis: Optional[Dict[str, Any]]
    iteration: int
    max_iterations: int
    done: bool


class RedTeamGraph:
    """LangGraph workflow for the Red Team."""

    def __init__(self, sandbox_client: Optional[SandboxClient] = None, ml_model=None):
        self.threat_hunter = ThreatHunter()
        self.attack_planner = AttackPlanner()
        self.attack_generator = AttackGenerator()
        self.failure_analyzer = FailureAnalyzer()
        self.memory_agent = MemoryAgent()
        self.strategy_layer = StrategyLayer(self.memory_agent)
        self.sandbox_client = sandbox_client or SandboxClient()
        self.linear_mutator = LinearMutator()
        self.evidence_collector = self._init_evidence_collector()

        self.state = RedTeamState()
        self.graph = self._build_graph()
        self.memory = MemorySaver()
        self.app = self.graph.compile(checkpointer=self.memory)

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(RedTeamGraphState)

        graph.add_node("hunt", self._hunt_node)
        graph.add_node("plan", self._plan_node)
        graph.add_node("generate", self._generate_node)
        graph.add_node("execute", self._execute_node)
        graph.add_node("analyze", self._analyze_node)
        graph.add_node("remember", self._remember_node)
        graph.add_node("decide", self._decide_node)
        graph.add_node("next_branch", self._next_branch_node)

        graph.set_entry_point("hunt")
        graph.add_edge("hunt", "plan")
        graph.add_edge("plan", "generate")
        graph.add_edge("generate", "execute")
        graph.add_edge("execute", "analyze")
        graph.add_edge("analyze", "remember")

        graph.add_conditional_edges(
            "remember",
            self._after_remember,
            {"execute": "execute", "next_branch": "next_branch", "decide": "decide"},
        )

        graph.add_edge("next_branch", "generate")

        graph.add_conditional_edges(
            "decide",
            self._should_continue,
            {"continue": "hunt", "plan": "plan", "end": END},
        )

        return graph

    def _init_evidence_collector(self):
        try:
            from backend.blue_team.collector import EvidenceCollector
            return EvidenceCollector.from_env()
        except Exception:
            return None

    def _after_remember(self, state: RedTeamGraphState) -> str:
        """Continue payloads, next tree branch, or decide."""
        if not state.get("done", True):
            return "execute"
        branches = state.get("plan_branches") or []
        next_idx = state.get("current_branch_index", 0) + 1
        if branches and next_idx < len(branches):
            return "next_branch"
        return "decide"

    def _next_branch_node(self, state: RedTeamGraphState) -> RedTeamGraphState:
        """Advance to the next parallel tree jailbreak branch."""
        next_idx = state.get("current_branch_index", 0) + 1
        branches = state.get("plan_branches") or []
        state["current_branch_index"] = next_idx
        state["plan"] = branches[next_idx]
        state["payloads"] = []
        state["current_payload_index"] = 0
        state["sandbox_response"] = None
        state["analysis"] = None
        state["done"] = False
        return state

    def _hunt_node(self, state: RedTeamGraphState) -> RedTeamGraphState:
        context = self.memory_agent.get_memory_context()
        tested = []
        for m in self.memory_agent.memories:
            conditions = m.applicable_conditions or {}
            if conditions.get("primary_family"):
                tested.append(conditions["primary_family"])
            tested.extend(conditions.get("composite_families") or [])
            tested.extend(conditions.get("covered_families") or [])

        queue = list(state.get("hypotheses_queue") or [])
        if queue:
            state["hypothesis"] = queue.pop(0)
            state["hypotheses_queue"] = queue
            state["iteration"] = state.get("iteration", 0) + 1
            return state

        output = self.threat_hunter.discover(
            memory_context=context,
            tested_families=list(dict.fromkeys(tested)),
            prefer_composites=True,
            max_hypotheses=5,
        )

        if output.hypotheses:
            dumped = [h.model_dump() for h in output.hypotheses]
            state["hypothesis"] = dumped[0]
            state["hypotheses_queue"] = dumped[1:]
        else:
            state["hypothesis"] = None
            state["hypotheses_queue"] = []

        state["iteration"] = state.get("iteration", 0) + 1
        return state

    def _plan_node(self, state: RedTeamGraphState) -> RedTeamGraphState:
        if not state.get("hypothesis"):
            state["done"] = True
            return state

        hypothesis = Hypothesis(**state["hypothesis"])
        branches = self.attack_planner.plan_branches(hypothesis)
        state["plan_branches"] = [branch.model_dump() for branch in branches] if len(branches) > 1 else []
        state["current_branch_index"] = 0
        plan = branches[0]
        state["plan"] = plan.model_dump()

        self.state.create_campaign(
            hypothesis=hypothesis.name,
            objective=plan.objective,
            target_stage=", ".join(plan.target_stages),
            attack_family=plan.primary_family,
        )

        return state

    def _generate_node(self, state: RedTeamGraphState) -> RedTeamGraphState:
        if not state.get("plan"):
            state["done"] = True
            return state

        plan = AttackPlan(**state["plan"])
        sequence = self.attack_generator.generate_sequence(plan)
        state["payloads"] = [p.model_dump() for p in sequence.payloads]
        state["current_payload_index"] = 0
        state["done"] = False
        return state

    def _execute_node(self, state: RedTeamGraphState) -> RedTeamGraphState:
        if not state.get("payloads"):
            state["done"] = True
            return state

        idx = state["current_payload_index"]
        payload = state["payloads"][idx]
        state["sandbox_response"] = self.sandbox_client.execute_payload(payload)
        return state

    def _analyze_node(self, state: RedTeamGraphState) -> RedTeamGraphState:
        if not state.get("sandbox_response"):
            state["done"] = True
            return state

        hypothesis = Hypothesis(**state["hypothesis"]) if state.get("hypothesis") else None
        plan = AttackPlan(**state["plan"]) if state.get("plan") else None
        payload = ActionPayload(**state["payloads"][state["current_payload_index"]]) if state.get("payloads") else None

        if not hypothesis or not plan or not payload:
            state["done"] = True
            return state

        analysis = self.failure_analyzer.analyze(
            sandbox_response=state["sandbox_response"],
            payload=payload,
            plan=plan,
        )
        state["analysis"] = analysis.model_dump()
        return state

    def _remember_node(self, state: RedTeamGraphState) -> RedTeamGraphState:
        if not state.get("analysis"):
            state["done"] = True
            return state

        analysis = AnalysisResult(**state["analysis"])
        hypothesis = Hypothesis(**state["hypothesis"]) if state.get("hypothesis") else None

        if hypothesis:
            self.memory_agent.store_analysis(analysis=analysis, hypothesis=hypothesis, context=state)

        # Feed Blue Team adversarial buffer (Loop B input)
        if self.evidence_collector and state.get("payloads") and state.get("sandbox_response"):
            try:
                payload = ActionPayload(**state["payloads"][state["current_payload_index"]])
                plan = AttackPlan(**state["plan"]) if state.get("plan") else None
                if plan:
                    self.evidence_collector.collect(
                        sandbox_response=state["sandbox_response"],
                        payload=payload,
                        plan=plan,
                        hypothesis=hypothesis,
                        analysis=analysis,
                        sandbox=self.sandbox_client.get_sandbox(),
                    )
            except Exception:
                pass

        if analysis.outcome == "success":
            self.state.successful_attacks += 1
        else:
            self.state.failed_attacks += 1
        self.state.experiment_count += 1

        idx = state.get("current_payload_index", 0)
        payload = ActionPayload(**state["payloads"][idx]) if state.get("payloads") else None
        linear_limit = max(0, int(os.environ.get("RED_TEAM_LINEAR_RETRIES", "2")))

        if (
            payload
            and analysis.outcome == "failure"
            and payload.action_type == "initiate_payment"
            and linear_limit > 0
            and not (payload.variation_label or "").startswith("linear_")
        ):
            for attempt in range(linear_limit):
                mutated = self.linear_mutator.mutate(payload, analysis, attempt=attempt)
                state["payloads"].insert(idx + 1 + attempt, mutated.model_dump())

        next_idx = idx + 1
        if next_idx < len(state.get("payloads", [])):
            state["current_payload_index"] = next_idx
            state["done"] = False
        else:
            state["done"] = True

        return state

    def _decide_node(self, state: RedTeamGraphState) -> RedTeamGraphState:
        # Drain remaining Threat Hunter hypotheses before StrategyLayer stop/continue
        queue = list(state.get("hypotheses_queue") or [])
        if queue:
            state["done"] = False
            state["hypothesis"] = queue.pop(0)
            state["hypotheses_queue"] = queue
            state["plan"] = None
            state["plan_branches"] = []
            state["current_branch_index"] = 0
            state["payloads"] = []
            state["current_payload_index"] = 0
            state["sandbox_response"] = None
            state["analysis"] = None
            return state

        hypothesis = Hypothesis(**state["hypothesis"]) if state.get("hypothesis") else None
        decision = self.strategy_layer.decide(
            current_hypothesis=hypothesis,
            last_analysis=state.get("analysis"),
            iteration=state.get("iteration", 0),
            max_iterations=state.get("max_iterations", 5),
        )

        if decision.action == "stop":
            state["done"] = True
        elif decision.action == "mutate" and decision.next_hypothesis:
            # Stay on same composite family with mutated strategy — go to plan
            state["done"] = False
            state["hypothesis"] = decision.next_hypothesis.model_dump()
            state["plan"] = None
            state["plan_branches"] = []
            state["current_branch_index"] = 0
            state["payloads"] = []
            state["current_payload_index"] = 0
            state["sandbox_response"] = None
            state["analysis"] = None
        else:
            state["done"] = False
            # Prefer strategy next_hypothesis if provided; else clear for re-hunt
            if decision.next_hypothesis:
                state["hypothesis"] = decision.next_hypothesis.model_dump()
                state["hypotheses_queue"] = list(state.get("hypotheses_queue") or [])
            else:
                state["hypothesis"] = None
                state["hypotheses_queue"] = []
            state["plan"] = None
            state["plan_branches"] = []
            state["current_branch_index"] = 0
            state["payloads"] = []
            state["current_payload_index"] = 0
            state["sandbox_response"] = None
            state["analysis"] = None

        return state

    def _should_continue(self, state: RedTeamGraphState) -> str:
        if state.get("done", False):
            return "end"
        # Next hypothesis already loaded from queue — skip re-hunt
        if state.get("hypothesis") and not state.get("plan"):
            return "plan"
        if state.get("iteration", 0) >= state.get("max_iterations", 3):
            return "end"
        return "continue"

    def run(self, max_iterations: int = 5):
        """Run the Red Team graph."""
        initial_state = {
            "hypothesis": None,
            "hypotheses_queue": [],
            "plan": None,
            "plan_branches": [],
            "current_branch_index": 0,
            "payloads": [],
            "current_payload_index": 0,
            "sandbox_response": None,
            "analysis": None,
            "iteration": 0,
            "max_iterations": max_iterations,
            "done": False,
        }

        config = {"configurable": {"thread_id": "red_team_1"}}
        return self.app.invoke(initial_state, config)

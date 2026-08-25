"""
Red Team LangGraph Workflow
Orchestrates the complete pipeline against the real Payment Sandbox.
"""

from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import RedTeamState
from .sandbox_client import SandboxClient
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
            {"continue": "hunt", "end": END},
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
        tested = [
            m.applicable_conditions.get("primary_family")
            for m in self.memory_agent.memories
            if m.applicable_conditions.get("primary_family")
        ]
        output = self.threat_hunter.discover(memory_context=context, tested_families=tested)

        if output.hypotheses:
            state["hypothesis"] = output.hypotheses[0].model_dump()
        else:
            state["hypothesis"] = None

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

        next_idx = state.get("current_payload_index", 0) + 1
        if next_idx < len(state.get("payloads", [])):
            state["current_payload_index"] = next_idx
            state["done"] = False
        else:
            state["done"] = True

        return state

    def _decide_node(self, state: RedTeamGraphState) -> RedTeamGraphState:
        hypothesis = Hypothesis(**state["hypothesis"]) if state.get("hypothesis") else None
        decision = self.strategy_layer.decide(
            current_hypothesis=hypothesis,
            last_analysis=state.get("analysis"),
            iteration=state.get("iteration", 0),
            max_iterations=state.get("max_iterations", 3),
        )

        if decision.action == "stop":
            state["done"] = True
        else:
            state["done"] = False
            state["hypothesis"] = None
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
        if state.get("iteration", 0) >= state.get("max_iterations", 3):
            return "end"
        return "continue"

    def run(self, max_iterations: int = 3):
        """Run the Red Team graph."""
        initial_state = {
            "hypothesis": None,
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

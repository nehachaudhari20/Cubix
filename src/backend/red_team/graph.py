"""
Red Team LangGraph Workflow
Orchestrates the complete pipeline.
"""

from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint import MemorySaver

from .state import RedTeamState
from .agents.threat_hunter import ThreatHunter
from .agents.attack_planner import AttackPlanner
from .agents.attack_generator import AttackGenerator
from .agents.failure_analyzer import FailureAnalyzer
from .agents.memory_agent import MemoryAgent
from .agents.strategy_layer import StrategyLayer
from .schemas import Hypothesis, AttackPlan, Payload, AnalysisResult


class RedTeamGraphState(TypedDict):
    """State passed between graph nodes."""
    hypothesis: Optional[Dict[str, Any]]
    plan: Optional[Dict[str, Any]]
    payloads: List[Dict[str, Any]]
    current_payload_index: int
    sandbox_response: Optional[Dict[str, Any]]
    analysis: Optional[Dict[str, Any]]
    iteration: int
    max_iterations: int
    done: bool


class RedTeamGraph:
    """LangGraph workflow for the Red Team."""
    
    def __init__(self, sandbox_client=None, ml_model=None):
        self.threat_hunter = ThreatHunter()
        self.attack_planner = AttackPlanner()
        self.attack_generator = AttackGenerator()
        self.failure_analyzer = FailureAnalyzer()
        self.memory_agent = MemoryAgent()
        self.strategy_layer = StrategyLayer(self.memory_agent)
        self.sandbox_client = sandbox_client
        
        self.state = RedTeamState()
        self.graph = self._build_graph()
        self.memory = MemorySaver()
        self.app = self.graph.compile(checkpointer=self.memory)
    
    def _build_graph(self) -> StateGraph:
        graph = StateGraph(RedTeamGraphState)
        
        # Nodes
        graph.add_node("hunt", self._hunt_node)
        graph.add_node("plan", self._plan_node)
        graph.add_node("generate", self._generate_node)
        graph.add_node("execute", self._execute_node)
        graph.add_node("analyze", self._analyze_node)
        graph.add_node("remember", self._remember_node)
        graph.add_node("decide", self._decide_node)
        
        # Edges
        graph.set_entry_point("hunt")
        graph.add_edge("hunt", "plan")
        graph.add_edge("plan", "generate")
        graph.add_edge("generate", "execute")
        graph.add_edge("execute", "analyze")
        graph.add_edge("analyze", "remember")
        graph.add_edge("remember", "decide")
        
        graph.add_conditional_edges(
            "decide",
            self._should_continue,
            {
                "continue": "hunt",
                "end": END
            }
        )
        
        return graph
    
    # ============================================================
    # Node Implementations
    # ============================================================
    
    def _hunt_node(self, state: RedTeamGraphState) -> RedTeamGraphState:
        """Threat Hunter: discover hypotheses."""
        # Get memory context
        context = self.memory_agent.get_memory_context()
        
        # Discover hypotheses
        output = self.threat_hunter.discover(memory_context=context)
        
        if output.hypotheses:
            state["hypothesis"] = output.hypotheses[0].model_dump()
        else:
            state["hypothesis"] = None
        
        state["iteration"] = state.get("iteration", 0) + 1
        return state
    
    def _plan_node(self, state: RedTeamGraphState) -> RedTeamGraphState:
        """Attack Planner: convert hypothesis to plan."""
        if not state.get("hypothesis"):
            state["done"] = True
            return state
        
        hypothesis = Hypothesis(**state["hypothesis"])
        plan = self.attack_planner.plan(hypothesis)
        state["plan"] = plan.model_dump()
        
        # Create campaign in state
        self.state.create_campaign(
            hypothesis=hypothesis.name,
            objective=plan.objective,
            target_stage=", ".join(plan.target_stages),
            attack_family=plan.primary_family
        )
        
        return state
    
    def _generate_node(self, state: RedTeamGraphState) -> RedTeamGraphState:
        """Attack Generator: create payloads."""
        if not state.get("plan"):
            state["done"] = True
            return state
        
        plan = AttackPlan(**state["plan"])
        sequence = self.attack_generator.generate_sequence(plan)
        state["payloads"] = [p.model_dump() for p in sequence.payloads]
        state["current_payload_index"] = 0
        
        return state
    
    def _execute_node(self, state: RedTeamGraphState) -> RedTeamGraphState:
        """Execute the current payload in Sandbox."""
        if not state.get("payloads"):
            state["done"] = True
            return state
        
        idx = state["current_payload_index"]
        payload = state["payloads"][idx]
        
        # For now, simulate Sandbox response
        # In production, this would call the actual Sandbox API
        amount = payload.get("amount", 0)
        is_new = payload.get("is_new_device", True)
        is_final = payload.get("is_final", False)
        
        # Simple simulation: high amount + new device = BLOCK
        if amount > 50000 and is_new:
            decision = "BLOCK"
            reason = "high_risk"
            risk_score = 0.85
        elif amount > 25000 and is_new:
            decision = "CHALLENGE"
            reason = "medium_risk_step_up"
            risk_score = 0.55
        else:
            decision = "ALLOW"
            reason = "low_risk"
            risk_score = 0.25
        
        state["sandbox_response"] = {
            "transaction_id": payload.get("transaction_id"),
            "decision": decision,
            "reason": reason,
            "state": {"risk_score": risk_score},
            "journey": [
                {"step": "KYC", "result": {"status": "PASS"}},
                {"step": "Device", "result": {"status": "PASS" if not is_new else "FLAG"}},
                {"step": "Authentication", "result": {"status": "PASS"}},
                {"step": "Risk", "result": {"risk_score": risk_score}},
                {"step": "Authorization", "result": {"decision": decision, "reason": reason}}
            ]
        }
        
        return state
    
    def _analyze_node(self, state: RedTeamGraphState) -> RedTeamGraphState:
        """Failure Analyzer: analyze response."""
        if not state.get("sandbox_response"):
            state["done"] = True
            return state
        
        hypothesis = Hypothesis(**state["hypothesis"]) if state.get("hypothesis") else None
        plan = AttackPlan(**state["plan"]) if state.get("plan") else None
        payload = Payload(**state["payloads"][state["current_payload_index"]]) if state.get("payloads") else None
        
        if not hypothesis or not plan or not payload:
            state["done"] = True
            return state
        
        analysis = self.failure_analyzer.analyze(
            sandbox_response=state["sandbox_response"],
            payload=payload,
            plan=plan
        )
        state["analysis"] = analysis.model_dump()
        
        return state
    
    def _remember_node(self, state: RedTeamGraphState) -> RedTeamGraphState:
        """Memory Agent: store analysis."""
        if not state.get("analysis"):
            state["done"] = True
            return state
        
        analysis = AnalysisResult(**state["analysis"])
        hypothesis = Hypothesis(**state["hypothesis"]) if state.get("hypothesis") else None
        
        if hypothesis:
            self.memory_agent.store_analysis(
                analysis=analysis,
                hypothesis=hypothesis,
                context=state
            )
        
        # Update state counters
        if analysis.outcome == "success":
            self.state.successful_attacks += 1
        else:
            self.state.failed_attacks += 1
        self.state.experiment_count += 1
        
        # Move to next payload or mark done
        if state.get("current_payload_index", 0) + 1 < len(state.get("payloads", [])):
            state["current_payload_index"] = state["current_payload_index"] + 1
            state["done"] = False
        else:
            state["done"] = True
        
        return state
    
    def _decide_node(self, state: RedTeamGraphState) -> RedTeamGraphState:
        """Strategy Layer: decide next action."""
        if not state.get("done"):
            # Still have more payloads to execute
            state["done"] = False
            return state
        
        hypothesis = Hypothesis(**state["hypothesis"]) if state.get("hypothesis") else None
        decision = self.strategy_layer.decide(hypothesis)
        
        if decision.action == "stop":
            state["done"] = True
        else:
            state["done"] = False
            # Reset for next campaign
            state["hypothesis"] = None
            state["plan"] = None
            state["payloads"] = []
            state["current_payload_index"] = 0
            state["sandbox_response"] = None
            state["analysis"] = None
        
        return state
    
    def _should_continue(self, state: RedTeamGraphState) -> str:
        """Decide whether to continue the loop."""
        if state.get("done", False):
            return "end"
        if state.get("iteration", 0) >= state.get("max_iterations", 3):
            return "end"
        return "continue"
    
    # ============================================================
    # Public API
    # ============================================================
    
    def run(self, max_iterations: int = 3):
        """Run the Red Team graph."""
        initial_state = {
            "hypothesis": None,
            "plan": None,
            "payloads": [],
            "current_payload_index": 0,
            "sandbox_response": None,
            "analysis": None,
            "iteration": 0,
            "max_iterations": max_iterations,
            "done": False
        }
        
        config = {"configurable": {"thread_id": "red_team_1"}}
        
        final_state = self.app.invoke(initial_state, config)
        return final_state
"""
Red Team State Management
Tracks campaigns, experiments, and statistics.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime


class RedTeamState:
    """Central state management for the Red Team."""
    
    def __init__(self):
        self.campaigns: List[Dict] = []
        self.experiment_count: int = 0
        self.successful_attacks: int = 0
        self.failed_attacks: int = 0
        self.attack_history: List[Dict] = []
    
    def create_campaign(self, hypothesis: str, objective: str, target_stage: str, attack_family: str) -> str:
        campaign_id = f"camp_{len(self.campaigns) + 1:04d}"
        self.campaigns.append({
            "campaign_id": campaign_id,
            "hypothesis": hypothesis,
            "objective": objective,
            "target_stage": target_stage,
            "attack_family": attack_family,
            "status": "planning",
            "created_at": datetime.now().isoformat()
        })
        return campaign_id
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_campaigns": len(self.campaigns),
            "experiment_count": self.experiment_count,
            "successful_attacks": self.successful_attacks,
            "failed_attacks": self.failed_attacks,
            "success_rate": self.successful_attacks / max(1, self.experiment_count)
        }
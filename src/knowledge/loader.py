import json
import os
from typing import List, Dict, Any

class KnowledgeLoader:
    def __init__(self, kb_path: str = "data/knowledge/"):
        self.kb_path = kb_path
        self.families = self._load("attack_families.json", "attack_families")
        self.signals = self._load("attack_signals.json", "signals")
        self.stages = self._load("lifecycle_stages.json", "lifecycle_stages")
    
    def _load(self, filename: str, key: str) -> List[Dict]:
        path = os.path.join(self.kb_path, filename)
        with open(path, 'r') as f:
            data = json.load(f)
            return data.get(key, [])
    
    def get_family(self, family_id: str) -> Dict:
        for f in self.families:
            if f.get("attack_id") == family_id:
                return f
        return None
    
    def get_families_by_stage(self, stage: str) -> List[Dict]:
        return [f for f in self.families if f.get("lifecycle_stage") == stage]
    
    def get_signals_by_family(self, family_id: str) -> List[Dict]:
        family = self.get_family(family_id)
        if family:
            return family.get("detection_signals", [])
        return []
    
    def get_all_controls(self) -> Dict[str, List[str]]:
        controls = {}
        for stage in self.stages:
            controls[stage.get("stage", "Unknown")] = stage.get("controls", [])
        return controls
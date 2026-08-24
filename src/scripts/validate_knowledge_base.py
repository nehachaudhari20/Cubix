import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.knowledge.loader import KnowledgeLoader

print("=" * 60)
print("VALIDATING KNOWLEDGE BASE (canonical -> KnowledgeLoader)")
print("=" * 60)

loader = KnowledgeLoader("data/knowledge/")
print(f"✅ canonical/attacks/attack_families.json → {len(loader.families)} families")
print(f"✅ canonical/defense/signals.json → {len(loader.signals)} signals")
print(f"✅ canonical/lifecycle/lifecycle_stages.json → {len(loader.stages)} stages")

print("\n" + "=" * 60)
print("✅ All registries loaded successfully via KnowledgeLoader!")
print(f"   Attack Families: {len(loader.families)}")
print(f"   Signals: {len(loader.signals)}")
print(f"   Stages: {len(loader.stages)}")

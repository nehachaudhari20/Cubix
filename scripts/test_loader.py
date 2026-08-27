import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.backend.knowledge.loader import KnowledgeLoader

loader = KnowledgeLoader()

print("="*60)
print("TESTING KNOWLEDGE LOADER")
print("="*60)

print(f"✅ Loaded {len(loader.families)} families")
print(f"✅ Loaded {len(loader.signals)} signals")
print(f"✅ Loaded {len(loader.stages)} stages")

print("\n📊 Sample Family:")
family = loader.get_family("SIF-001")
if family:
    print(f"   ID: {family.get('attack_id')}")
    print(f"   Variants: {family.get('variants', [])[:3]}...")
    print(f"   Stage: {family.get('lifecycle_stage')}")

print("\n📊 Sample Signal:")
if loader.signals:
    s = loader.signals[0]
    print(f"   Name: {s.get('signal_name', s.get('name'))}")
    print(f"   Category: {s.get('category')}")

print("\n📊 Controls by Stage:")
controls = loader.get_all_controls()
for stage, ctrls in list(controls.items())[:3]:
    print(f"   {stage}: {ctrls[:2]}...")

print("\n✅ Knowledge Loader is ready!")
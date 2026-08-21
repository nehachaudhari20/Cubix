import json
import os

def validate_json(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)
    print(f"✅ {filepath}: {len(data)} items (or {len(data.get('attack_families', [])) if 'attack_families' in data else 'N/A'})")
    return data

print("="*60)
print("VALIDATING KNOWLEDGE BASE")
print("="*60)

families = validate_json("data/knowledge/attack_families.json")
signals = validate_json("data/knowledge/attack_signals.json")
stages = validate_json("data/knowledge/lifecycle_stages.json")

print("\n" + "="*60)
print("✅ All files loaded successfully!")
print(f"   Attack Families: {len(families.get('attack_families', []))}")
print(f"   Signals: {len(signals.get('signals', []))}")
print(f"   Stages: {len(stages.get('lifecycle_stages', []))}")
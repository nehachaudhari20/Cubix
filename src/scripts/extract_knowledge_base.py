"""
KNOWLEDGE BASE EXTRACTOR
Reads all PDF taxonomies, uses LLM to extract structured data,
and generates attack_families.json, attack_signals.json,
lifecycle_stages.json, and splits the master dataset.
"""

import os
import json
import re
from datetime import datetime
from typing import List, Dict, Any
import pandas as pd

# ============================================================
# STEP 1: Extract Text from PDFs
# ============================================================

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF file."""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
            return text
    except ImportError:
        # Fallback to pypdf
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text

def extract_all_pdfs(pdf_folder: str = "data/raw_pdfs/") -> Dict[str, str]:
    """Extract text from all PDFs in folder."""
    documents = {}
    for filename in os.listdir(pdf_folder):
        if filename.endswith(".pdf"):
            doc_key = filename.replace(".pdf", "").lower()
            pdf_path = os.path.join(pdf_folder, filename)
            print(f"  📄 Extracting: {filename}")
            documents[doc_key] = extract_text_from_pdf(pdf_path)
    return documents

# ============================================================
# STEP 2: LLM Extraction Function
# ============================================================

def extract_structured_data_with_llm(doc_text: str, doc_name: str) -> Dict[str, Any]:
    """
    Send the extracted PDF text to an LLM and get structured JSON back.
    You'll need an API key for Gemini/Claude/OpenAI.
    """
    import google.generativeai as genai  # or openai, or anthropic
    
    # Configure your LLM (example uses Gemini)
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    model = genai.GenerativeModel("gemini-2.0-flash")
    
    prompt = f"""
You are a fraud taxonomy extraction expert. Given the text of a payment fraud taxonomy document, extract ALL structured information into the following JSON schema.

DOCUMENT NAME: {doc_name}

TEXT CONTENT:
{doc_text[:50000]}  # Truncate to fit context window

Extract the following:

1. **attack_families**: For each attack family mentioned, extract:
   - attack_id (e.g., "SIF-001")
   - name (descriptive name)
   - variants (list of subtypes)
   - lifecycle_stage (Identity_KYC, Authentication, Payment_Initiation, etc.)
   - genai_classification (PASS, PARTIAL, or FAIL)
   - simulation_type (Algorithmic, Agentic, or Hybrid)
   - prerequisites (list of required conditions)
   - attack_flow (list of steps)
   - detection_signals (list of observable signals, each with name and detection_method)
   - controls_targeted (list of controls being exploited)
   - evidence_confidence (VERIFIED, REASONABLE_INFERENCE, etc.)

2. **signals**: For each detection signal mentioned, extract:
   - signal_name
   - category (Transaction, Network, Behavioral, Temporal, etc.)
   - description
   - detection_method (Rules, ML, Graph, etc.)
   - false_positive_risk (what legitimate activity looks similar)
   - cross_account_needed (true/false)

3. **lifecycle_stages**: For each stage mentioned, extract:
   - stage_name
   - controls (list of control mechanisms)

Return ONLY valid JSON with this structure:
{{
  "attack_families": [...],
  "signals": [...],
  "lifecycle_stages": [...]
}}
"""
    
    response = model.generate_content(prompt)
    # Parse the JSON from the response
    json_text = re.sub(r'```json\n?', '', response.text)
    json_text = re.sub(r'\n```', '', json_text)
    return json.loads(json_text)

# ============================================================
# STEP 3: Merge All Extractions
# ============================================================

def merge_extractions(extractions: List[Dict]) -> Dict[str, List]:
    """Merge multiple document extractions into one master JSON."""
    merged = {
        "attack_families": [],
        "signals": [],
        "lifecycle_stages": []
    }
    
    seen_families = set()
    seen_signals = set()
    seen_stages = set()
    
    for extraction in extractions:
        for family in extraction.get("attack_families", []):
            fid = family.get("attack_id")
            if fid not in seen_families:
                merged["attack_families"].append(family)
                seen_families.add(fid)
        
        for signal in extraction.get("signals", []):
            sid = signal.get("signal_name", signal.get("name"))
            if sid not in seen_signals:
                merged["signals"].append(signal)
                seen_signals.add(sid)
        
        for stage in extraction.get("lifecycle_stages", []):
            sname = stage.get("stage_name")
            if sname not in seen_stages:
                merged["lifecycle_stages"].append(stage)
                seen_stages.add(sname)
    
    return merged

# ============================================================
# STEP 4: Save the JSON Files
# ============================================================

def save_knowledge_base(merged: Dict[str, List], output_folder: str = "data/knowledge/"):
    """Save the merged data into separate JSON files."""
    os.makedirs(output_folder, exist_ok=True)
    
    # 1. attack_families.json
    with open(os.path.join(output_folder, "attack_families.json"), "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "total_families": len(merged["attack_families"]),
            "attack_families": merged["attack_families"]
        }, f, indent=2)
    
    # 2. attack_signals.json
    with open(os.path.join(output_folder, "attack_signals.json"), "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "total_signals": len(merged["signals"]),
            "signals": merged["signals"]
        }, f, indent=2)
    
    # 3. lifecycle_stages.json
    with open(os.path.join(output_folder, "lifecycle_stages.json"), "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "total_stages": len(merged["lifecycle_stages"]),
            "lifecycle_stages": merged["lifecycle_stages"]
        }, f, indent=2)
    
    print(f"\n✅ Knowledge Base saved to {output_folder}")
    print(f"   attack_families.json: {len(merged['attack_families'])} families")
    print(f"   attack_signals.json: {len(merged['signals'])} signals")
    print(f"   lifecycle_stages.json: {len(merged['lifecycle_stages'])} stages")

# ============================================================
# STEP 5: Split Master Dataset
# ============================================================

def split_master_dataset(master_json_path: str = "master_dataset.json"):
    """Split the master dataset into baseline and known_fraud."""
    with open(master_json_path, "r") as f:
        data = json.load(f)
    
    transactions = data["transactions"]
    
    legit = [t for t in transactions if t.get("is_fraud") == 0]
    fraud = [t for t in transactions if t.get("is_fraud") == 1]
    
    os.makedirs("data/baseline/", exist_ok=True)
    os.makedirs("data/known_fraud/", exist_ok=True)
    
    pd.DataFrame(legit).to_csv("data/baseline/baseline_transactions.csv", index=False)
    pd.DataFrame(fraud).to_csv("data/known_fraud/known_fraud.csv", index=False)
    
    print(f"\n✅ Dataset split:")
    print(f"   Baseline: {len(legit)} transactions")
    print(f"   Known Fraud: {len(fraud)} transactions")

# ============================================================
# MAIN EXECUTION
# ============================================================

if __name__ == "__main__":
    print("="*70)
    print("KNOWLEDGE BASE EXTRACTOR")
    print("="*70)
    
    # Step 1: Extract text from all PDFs
    print("\n📄 Step 1: Extracting text from PDFs...")
    documents = extract_all_pdfs("data/raw_pdfs/")
    print(f"   Extracted {len(documents)} documents")
    
    # Step 2: Send each document to LLM
    print("\n🤖 Step 2: Sending to LLM for extraction...")
    extractions = []
    for doc_key, doc_text in documents.items():
        print(f"   Processing: {doc_key}")
        try:
            result = extract_structured_data_with_llm(doc_text, doc_key)
            extractions.append(result)
            print(f"      ✅ Extracted {len(result.get('attack_families', []))} families")
        except Exception as e:
            print(f"      ❌ Error: {e}")
    
    # Step 3: Merge all extractions
    print("\n🔗 Step 3: Merging extractions...")
    merged = merge_extractions(extractions)
    
    # Step 4: Save JSON files
    print("\n💾 Step 4: Saving knowledge base...")
    save_knowledge_base(merged)
    
    # Step 5: Split master dataset
    print("\n📊 Step 5: Splitting master dataset...")
    split_master_dataset("master_dataset.json")
    
    print("\n" + "="*70)
    print("✅ KNOWLEDGE BASE GENERATION COMPLETE")
    print("="*70)
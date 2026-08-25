"""
Red Team Utilities
KB API client, baseline loader, and helpers.
"""

import os
import requests
import pandas as pd
from typing import Dict, Any, Optional, List
import numpy as np

KB_API_URL = os.environ.get("KB_API_URL", "http://localhost:8000")


class KnowledgeBaseClient:
    """Client for the Knowledge Base API."""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or KB_API_URL
    
    def get_families(self, stage: Optional[str] = None) -> List[Dict]:
        """Fetch all families, optionally filtered by stage."""
        url = f"{self.base_url}/families"
        if stage:
            url = f"{self.base_url}/families/stage/{stage}"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
            return []
        except Exception:
            return []
    
    def get_family(self, family_id: str) -> Optional[Dict]:
        """Fetch a single family by ID."""
        try:
            response = requests.get(f"{self.base_url}/families/{family_id}", timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None
    
    def get_stages(self) -> List[Dict]:
        """Fetch all lifecycle stages."""
        try:
            response = requests.get(f"{self.base_url}/stages", timeout=10)
            if response.status_code == 200:
                return response.json()
            return []
        except Exception:
            return []
    
    def get_controls(self, stage: str) -> Dict:
        """Fetch controls for a specific stage."""
        try:
            response = requests.get(f"{self.base_url}/stages/{stage}/controls", timeout=10)
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception:
            return {}


class BaselineLoader:
    """Load and sample from baseline transaction data."""
    
    def __init__(self, baseline_path: str = "data/baseline/baseline_transactions.csv"):
        self.baseline_path = baseline_path
        self.df = None
        self._load()
    
    def _load(self):
        if os.path.exists(self.baseline_path):
            try:
                self.df = pd.read_csv(self.baseline_path)
                print(f"Baseline loaded: {len(self.df)} transactions")
            except Exception as e:
                print(f"Baseline load failed: {e}")
        else:
            print(f"Baseline not found: {self.baseline_path}")
    
    def sample_amount(self) -> float:
        if self.df is not None and len(self.df) > 0:
            amount = np.random.choice(self.df["amount"].values)
            noise = np.random.normal(0, amount * 0.05)
            return max(1, round(amount + noise, 2))
        return round(np.random.lognormal(mean=7, sigma=1.5), 2)
    
    def sample_rail(self) -> str:
        if self.df is not None and len(self.df) > 0:
            return np.random.choice(self.df["payment_rail"].dropna().values)
        return np.random.choice(["upi", "card", "bank_transfer", "wallet"])
    
    def sample_merchant_risk(self) -> float:
        if self.df is not None and len(self.df) > 0:
            return float(np.random.choice(self.df["merchant_risk_score"].dropna().values))
        return np.random.uniform(0.1, 0.5)
    
    def sample_transaction_type(self) -> str:
        if self.df is not None and len(self.df) > 0:
            return np.random.choice(self.df["transaction_type"].dropna().values)
        return np.random.choice(["purchase", "transfer", "subscription", "refund"])
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class Flag(BaseModel):
    code: str
    severity: str
    evidence: Dict[str, Any]

class Summary(BaseModel):
    fundamentals_score: int
    label: str

class AnalyzerOutput(BaseModel):
    token: str
    chainId: int
    blockNumber: int
    summary: Summary
    flags: List[Flag]
    facts: Dict[str, Any]
    contract_analysis_thesis: Optional[str] = None   # <-- new

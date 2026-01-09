"""
EGB Components

六大核心元件：

1. TraceLinker（證據關聯器）
   - 把 intent_id/decision_id/playbook_id/run_id 綁到 trace_id/span_id

2. EvidenceReducer（證據收斂器）
   - 把 raw trace → 結構化證據（數字、diff、路徑序列、引用 ids）
   - 盡量不用 LLM，純計算處理

3. DriftScorer（漂移評分器）
   - 計算五種漂移分數：證據/路徑/約束/語義/成本

4. PolicyAttributor（政策歸因器）
   - 把漂移點對應到「哪個治理規則/哪個 lens 介入造成的」

5. LensExplainer（心智鏡解釋器）
   - LLM 輔助，把結構化證據翻譯成人話
   - 只在需要時觸發

6. GovernanceTuner（治理調參器）
   - 產生可執行的建議（strictness 升級、toolset 收斂、scope 鎖定等）
   - 回寫成 DecisionRecord
"""

from .trace_linker import TraceLinker
from .evidence_reducer import EvidenceReducer
from .drift_scorer import DriftScorer
from .policy_attributor import PolicyAttributor
from .lens_explainer import LensExplainer
from .governance_tuner import GovernanceTuner

__all__ = [
    "TraceLinker",
    "EvidenceReducer",
    "DriftScorer",
    "PolicyAttributor",
    "LensExplainer",
    "GovernanceTuner",
]


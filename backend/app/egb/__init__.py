"""
Evidence-Backed Governance Bridge (EGB)

EGB is the middleware connecting Intent Layer with Trace Layer (observability layer/Langfuse).
Core responsibility: Converge, align, quantify, and translate Trace observation evidence
into governance inputs and knob suggestions usable by Intent/Decision.

Architecture:
    Intent Layer
           │
           ▼
    EGB (Evidence-Backed Governance Bridge)
    ├── TraceLinker (Evidence linker)
    ├── EvidenceReducer (Evidence reducer)
    ├── DriftScorer (Drift scorer)
    ├── PolicyAttributor (Policy attributor)
    ├── LensExplainer (Mind lens explainer) - LLM only when needed
    └── GovernanceTuner (Governance tuner)
           │
           ▼
    Trace Layer (Langfuse)
"""

__version__ = "0.1.0"


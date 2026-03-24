from backend.app.services.governance.memory_packet_compiler import (
    MemoryPacketCompiler,
)


def test_memory_packet_compiler_builds_ordered_route_and_context():
    compiler = MemoryPacketCompiler()
    governance_packet = {
        "memory_packet": {
            "selection": {
                "workspace_mode": "research",
                "memory_scope": "extended",
                "episodic_limit": 3,
            },
            "layers": {
                "core": {
                    "brand_identity": {"name": "Mindscape"},
                    "voice_and_tone": {"tone": "calm"},
                    "style_constraints": ["precise", "inspectable"],
                    "learnings": ["Surface tradeoffs early."],
                },
                "knowledge": {
                    "verified": [
                        {
                            "knowledge_type": "principle",
                            "content": "Prefer explicit reasoning.",
                        }
                    ],
                    "candidates": [
                        {
                            "knowledge_type": "preference",
                            "content": "May prefer shorter summaries.",
                        }
                    ],
                },
                "goals": {
                    "active": [
                        {
                            "title": "Finish phase 1",
                            "description": "Close the memory loop",
                        }
                    ],
                    "pending": [{"title": "Revisit merge semantics"}],
                },
                "project": {
                    "decision_history": [
                        {
                            "decision": "Ship canonical writeback first",
                            "rationale": "Stabilize ownership before router work",
                        }
                    ],
                    "key_conversations": ["Defer merge lifecycle until later"],
                },
                "member": {
                    "skills": ["research", "editing"],
                    "preferences": {"tone": "direct"},
                    "learnings": ["Keep the architecture layered."],
                },
                "episodic": [
                    {"summary": "Closed meeting writeback loop."},
                    {"summary": "Added governance packet selection."},
                ],
            },
        }
    }

    route = compiler.build_route_plan(governance_packet, include_semantic_hits=True)
    assert route == [
        "core",
        "verified_knowledge",
        "active_goals",
        "project_memory",
        "member_memory",
        "candidate_knowledge",
        "pending_goals",
        "episodic_evidence",
        "semantic_hits",
    ]

    compiled = compiler.compile_for_context(governance_packet)
    assert "Routing mode: research / extended" in compiled
    assert compiled.index("Core directives:") < compiled.index("Guiding knowledge:")
    assert compiled.index("Guiding knowledge:") < compiled.index("Active goals:")
    assert compiled.index("Active goals:") < compiled.index("Project decisions:")
    assert compiled.index("Project decisions:") < compiled.index("Member strengths:")
    assert compiled.index("Member strengths:") < compiled.index("Emerging candidates:")
    assert compiled.index("Emerging candidates:") < compiled.index("Pending goals:")
    assert compiled.index("Pending goals:") < compiled.index("Recent episodes:")

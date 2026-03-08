"""
Conversation orchestration modules

Modular components for conversation orchestration:
- plan_builder: Execution plan generation and side_effect level determination
- task_manager: Task and TimelineItem lifecycle management
- cta_handler: CTA handling and external write operations
- intent_extractor: LLM-based intent extraction and timeline item creation
- llm_provider_factory: Centralized LLM provider construction
- project_detector_handler: Project detection and creation
- response_assembler: Event serialization and response building
- thread_stats_updater: Thread statistics update helper
"""

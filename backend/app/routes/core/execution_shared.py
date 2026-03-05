"""
Shared singleton instances for playbook execution.

Extracted from playbook_execution.py so that external consumers
(e.g. conversation_orchestrator, playbook queries) can import
these singletons without depending on the route module directly.
"""

from ...services.playbook_run_executor import PlaybookRunExecutor
from ...services.playbook_runner import PlaybookRunner

# Initialize unified executor (automatically selects PlaybookRunner or WorkflowOrchestrator)
playbook_executor = PlaybookRunExecutor()
# Keep PlaybookRunner for continue operations (conversation mode)
playbook_runner = PlaybookRunner()

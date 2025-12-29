"""
Lens Execution Injector.

Handles lens injection into playbook execution and receipt generation.
"""
import uuid
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from app.services.stores.graph_store import GraphStore
from app.services.lens.effective_lens_resolver import EffectiveLensResolver
from app.services.lens.session_override_store import InMemorySessionStore
from app.services.lens.graph_to_composition_compiler import GraphToCompositionCompiler
from app.services.lens.lens_snapshot_store import LensSnapshotStore
from app.services.lens.lens_receipt_store import LensReceiptStore
from app.models.lens_kernel import EffectiveLens
from app.models.lens_snapshot import LensSnapshot
from app.models.lens_receipt import LensReceipt, TriggeredNode
from app.core.feature_flags import FeatureFlags
import os

logger = logging.getLogger(__name__)


class LensExecutionInjector:
    """Inject lens into execution and generate receipts"""

    def __init__(self):
        if os.path.exists('/.dockerenv') or os.environ.get('PYTHONPATH') == '/app':
            db_path = '/app/data/mindscape.db'
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "mindscape.db")

        self.graph_store = GraphStore(db_path)
        self.session_store = InMemorySessionStore()
        self.resolver = EffectiveLensResolver(self.graph_store, self.session_store)
        self.compiler = GraphToCompositionCompiler()
        self.snapshot_store = LensSnapshotStore(db_path)
        self.receipt_store = LensReceiptStore(db_path)

    def prepare_lens_context(
        self,
        profile_id: str,
        workspace_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Prepare lens context for execution

        Returns:
            Compiled lens context dict or None if feature flag is off
        """
        if not FeatureFlags.USE_EFFECTIVE_LENS_RESOLVER:
            return None

        try:
            effective_lens = self.resolver.resolve(
                profile_id=profile_id,
                workspace_id=workspace_id,
                session_id=session_id
            )

            snapshot = LensSnapshot(
                id=str(uuid.uuid4()),
                effective_lens_hash=effective_lens.hash,
                profile_id=profile_id,
                workspace_id=workspace_id,
                session_id=session_id,
                nodes=effective_lens.nodes
            )
            self.snapshot_store.save_if_not_exists(snapshot)

            compiled_context = self.compiler.compile_to_prompt_context(effective_lens)

            return {
                "system_prompt_additions": compiled_context.system_prompt_additions,
                "anti_goals": compiled_context.anti_goals,
                "emphasized_values": compiled_context.emphasized_values,
                "style_rules": compiled_context.style_rules,
                "effective_lens_hash": effective_lens.hash,
                "effective_lens": effective_lens
            }
        except Exception as e:
            logger.error(f"Failed to prepare lens context: {e}", exc_info=True)
            return None

    def generate_receipt(
        self,
        execution_id: str,
        workspace_id: str,
        effective_lens: Optional[EffectiveLens],
        output: Optional[str] = None,
        base_output: Optional[str] = None
    ) -> Optional[LensReceipt]:
        """
        Generate lens receipt after execution

        Args:
            execution_id: Execution ID
            workspace_id: Workspace ID
            effective_lens: Effective lens used (if any)
            output: Final output
            base_output: Base output without lens (if available)

        Returns:
            LensReceipt or None
        """
        if not FeatureFlags.USE_EFFECTIVE_LENS_RESOLVER or not effective_lens:
            return None

        try:
            triggered_nodes = []
            for node in effective_lens.nodes:
                if node.state.value != "off":
                    triggered_nodes.append(TriggeredNode(
                        node_id=node.node_id,
                        node_label=node.node_label,
                        state=node.state,
                        effective_scope=node.effective_scope
                    ))

            receipt = LensReceipt(
                id=str(uuid.uuid4()),
                execution_id=execution_id,
                workspace_id=workspace_id,
                effective_lens_hash=effective_lens.hash,
                triggered_nodes=triggered_nodes,
                base_output=base_output,
                lens_output=output,
                diff_summary=None
            )

            self.receipt_store.save(receipt)
            return receipt
        except Exception as e:
            logger.error(f"Failed to generate receipt: {e}", exc_info=True)
            return None


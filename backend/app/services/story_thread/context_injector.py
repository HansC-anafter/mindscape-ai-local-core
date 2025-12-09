"""Story Thread context injector for Playbook execution."""
import logging
import os
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)


class StoryThreadContextInjector:
    """Inject Story Thread context into Playbook execution."""

    def __init__(self, cloud_api_url: Optional[str] = None):
        """
        Initialize Story Thread context injector.

        Args:
            cloud_api_url: Cloud API base URL (defaults to CLOUD_API_URL env var)
        """
        self.cloud_api_url = cloud_api_url or os.getenv("CLOUD_API_URL")
        if not self.cloud_api_url:
            logger.debug("CLOUD_API_URL not configured, Story Thread context injection disabled")

    async def inject_context(
        self,
        execution_id: str,
        thread_id: Optional[str],
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Inject Story Thread context into playbook inputs.

        Args:
            execution_id: Playbook execution ID
            thread_id: Optional Story Thread ID
            inputs: Original playbook inputs

        Returns:
            Enhanced inputs with Story Thread context
        """
        if not thread_id:
            return inputs

        if not self.cloud_api_url:
            logger.debug(f"Cloud API URL not configured, skipping context injection for thread {thread_id}")
            return inputs

        try:
            context = await self._fetch_thread_context(thread_id)
            if context:
                enhanced_inputs = self._merge_context(inputs, context)
                logger.info(f"Injected Story Thread context for thread {thread_id} into execution {execution_id}")
                return enhanced_inputs
            else:
                logger.warning(f"Story Thread {thread_id} not found or has no context")
                return inputs
        except Exception as e:
            logger.warning(f"Failed to inject Story Thread context: {e}", exc_info=True)
            return inputs

    async def extract_context_updates(
        self,
        execution_id: str,
        thread_id: Optional[str],
        execution_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Extract context updates from playbook execution result.

        Args:
            execution_id: Playbook execution ID
            thread_id: Optional Story Thread ID
            execution_result: Playbook execution result

        Returns:
            Context updates to write back to Story Thread
        """
        if not thread_id:
            return {}

        if not self.cloud_api_url:
            logger.debug(f"Cloud API URL not configured, skipping context extraction for thread {thread_id}")
            return {}

        try:
            updates = self._extract_updates(execution_result)
            if updates:
                await self._update_thread_context(thread_id, updates)
                logger.info(f"Extracted and updated Story Thread context for thread {thread_id} from execution {execution_id}")
            return updates
        except Exception as e:
            logger.warning(f"Failed to extract Story Thread context updates: {e}", exc_info=True)
            return {}

    async def _fetch_thread_context(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch Story Thread context from Cloud API.

        Args:
            thread_id: Story Thread ID

        Returns:
            Shared context dictionary or None if not found
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.cloud_api_url}/api/v1/story-threads/{thread_id}/context",
                )
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    logger.warning(f"Story Thread {thread_id} not found")
                    return None
                else:
                    logger.error(f"Failed to fetch Story Thread context: {response.status_code} - {response.text}")
                    return None
        except httpx.TimeoutException:
            logger.warning(f"Timeout fetching Story Thread context for {thread_id}")
            return None
        except Exception as e:
            logger.error(f"Error fetching Story Thread context: {e}", exc_info=True)
            return None

    async def _update_thread_context(
        self,
        thread_id: str,
        updates: Dict[str, Any],
        merge_strategy: str = "merge",
    ) -> bool:
        """
        Update Story Thread context via Cloud API.

        Args:
            thread_id: Story Thread ID
            updates: Context updates
            merge_strategy: Merge strategy ("merge" or "replace")

        Returns:
            True if updated successfully
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.put(
                    f"{self.cloud_api_url}/api/v1/story-threads/{thread_id}/context",
                    json={
                        "updates": updates,
                        "merge_strategy": merge_strategy,
                    },
                )
                if response.status_code == 200:
                    return True
                else:
                    logger.error(f"Failed to update Story Thread context: {response.status_code} - {response.text}")
                    return False
        except httpx.TimeoutException:
            logger.warning(f"Timeout updating Story Thread context for {thread_id}")
            return False
        except Exception as e:
            logger.error(f"Error updating Story Thread context: {e}", exc_info=True)
            return False

    def _merge_context(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge Story Thread context into playbook inputs.

        Args:
            inputs: Original playbook inputs
            context: Story Thread shared context

        Returns:
            Enhanced inputs with merged context
        """
        enhanced = inputs.copy()

        if "story_thread_context" not in enhanced:
            enhanced["story_thread_context"] = {}

        enhanced["story_thread_context"].update(context)

        return enhanced

    def _extract_updates(self, execution_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract context updates from playbook execution result.

        Args:
            execution_result: Playbook execution result

        Returns:
            Context updates dictionary
        """
        updates = {}

        if "artifacts" in execution_result:
            artifact_ids = [a.get("id") or a.get("artifact_id") for a in execution_result["artifacts"] if isinstance(a, dict)]
            if artifact_ids:
                updates["last_artifacts"] = artifact_ids

        if "output" in execution_result:
            output = execution_result["output"]
            if isinstance(output, dict):
                if "context_updates" in output:
                    updates.update(output["context_updates"])
                elif "summary" in output:
                    updates["last_execution_summary"] = output["summary"]

        if "metadata" in execution_result:
            metadata = execution_result["metadata"]
            if isinstance(metadata, dict):
                if "context_updates" in metadata:
                    updates.update(metadata["context_updates"])

        return updates


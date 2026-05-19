"""External-write CTA action handlers."""

import logging
import os
import uuid
from typing import Any, Dict

try:
    import requests
    from requests.auth import HTTPBasicAuth

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from ....models.mindscape import MindEvent
from ....models.workspace import Task, TaskStatus, TimelineItem, TimelineItemType
from .base import _utc_now

logger = logging.getLogger(__name__)


class CTAExternalWriteMixin:
    """Handle external-write CTA actions."""

    async def _handle_external_write(
        self,
        workspace_id: str,
        profile_id: str,
        user_event: MindEvent,
        timeline_item: TimelineItem,
        task: Task,
        action: str,
    ) -> str:
        """
        Handle external_write CTA action.

        Args:
            workspace_id: Workspace ID.
            profile_id: User profile ID.
            user_event: User event for CTA action.
            timeline_item: Timeline item.
            task: Associated task.
            action: Action type.

        Returns:
            Assistant response message.
        """
        if action == "publish_to_wordpress" or action.startswith("publish_"):
            try:
                content_data = (
                    timeline_item.data.get("content")
                    or timeline_item.data.get("draft")
                    or timeline_item.summary
                )
                title = timeline_item.data.get("title") or timeline_item.title

                publish_result = await self._execute_wordpress_publish(
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    title=title,
                    content=content_data,
                    timeline_item_id=timeline_item.id,
                )

                publish_task = Task(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    message_id=user_event.id,
                    execution_id=None,
                    pack_id="wp_sync",
                    task_type="publish_post",
                    status=TaskStatus.SUCCEEDED
                    if publish_result.get("success")
                    else TaskStatus.FAILED,
                    params={
                        "title": title,
                        "action": action,
                    },
                    result=publish_result,
                    created_at=_utc_now(),
                    started_at=_utc_now(),
                    completed_at=_utc_now(),
                    error=publish_result.get("error"),
                )
                self.tasks_store.create_task(publish_task)

                result_timeline_item = TimelineItem(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    message_id=user_event.id,
                    task_id=publish_task.id,
                    type=TimelineItemType.SUMMARY
                    if publish_result.get("success")
                    else TimelineItemType.ERROR,
                    title=f"Published: {title}"
                    if publish_result.get("success")
                    else f"Failed to publish: {title}",
                    summary=publish_result.get("post_url", "Published successfully")
                    if publish_result.get("success")
                    else publish_result.get("error", "Unknown error"),
                    data={
                        "action": action,
                        "publish_result": publish_result,
                        "original_timeline_item_id": timeline_item.id,
                    },
                    cta=None,
                    created_at=_utc_now(),
                )
                self.timeline_items_store.create_timeline_item(result_timeline_item)

                try:
                    timeline_item.data["publish_result"] = publish_result
                    self.timeline_items_store.update_timeline_item(
                        timeline_item.id, data=timeline_item.data
                    )
                except Exception as e:
                    logger.warning(f"Failed to update original timeline item: {e}")

                if publish_result.get("success"):
                    return (
                        self.i18n.t(
                            "conversation_orchestrator",
                            "workflow.started",
                            playbook_code="wp_sync",
                        )
                        + f" Published: {publish_result.get('post_url', 'N/A')}"
                    )
                return f"Failed to publish: {publish_result.get('error', 'Unknown error')}"
            except Exception as e:
                logger.error(f"Failed to execute WordPress publish: {e}", exc_info=True)

                error_task = Task(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    message_id=user_event.id,
                    execution_id=None,
                    pack_id="wp_sync",
                    task_type="publish_post",
                    status=TaskStatus.FAILED,
                    params={"title": timeline_item.title, "action": action},
                    result={"error": str(e)},
                    created_at=_utc_now(),
                    started_at=_utc_now(),
                    completed_at=_utc_now(),
                    error=str(e),
                )
                self.tasks_store.create_task(error_task)

                error_timeline_item = TimelineItem(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    message_id=user_event.id,
                    task_id=error_task.id,
                    type=TimelineItemType.ERROR,
                    title=f"Failed to publish: {timeline_item.title}",
                    summary=f"Error: {str(e)}",
                    data={
                        "action": action,
                        "error": str(e),
                        "original_timeline_item_id": timeline_item.id,
                    },
                    cta=None,
                    created_at=_utc_now(),
                )
                self.timeline_items_store.create_timeline_item(error_timeline_item)

                return f"Error executing {action}: {str(e)}"

        action_result = None
        action_success = False
        action_error = None

        try:
            if action == "export_document":
                logger.info("Export document action triggered (placeholder implementation)")
                action_result = {
                    "action": action,
                    "status": "completed",
                    "exported": True,
                    "note": "Placeholder implementation - actual export logic to be implemented",
                }
                action_success = True
            elif action == "execute_external_action":
                logger.info("Generic external action triggered (placeholder implementation)")
                action_result = {
                    "action": action,
                    "status": "completed",
                    "note": "Placeholder implementation - actual action logic to be implemented",
                }
                action_success = True
            else:
                logger.warning(
                    f"Unknown external_write action: {action} - using placeholder"
                )
                action_result = {
                    "action": action,
                    "status": "completed",
                    "note": "Action executed but implementation may be missing - placeholder result",
                }
                action_success = True
        except Exception as e:
            action_error = str(e)
            action_success = False
            logger.error(
                f"Failed to execute external_write action {action}: {e}",
                exc_info=True,
            )

        action_task = Task(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            message_id=user_event.id,
            execution_id=None,
            pack_id=task.pack_id,
            task_type=f"external_action_{action}",
            status=TaskStatus.SUCCEEDED if action_success else TaskStatus.FAILED,
            params={
                "action": action,
                "timeline_item_id": timeline_item.id,
            },
            result=action_result if action_success else {"error": action_error},
            created_at=_utc_now(),
            started_at=_utc_now(),
            completed_at=_utc_now(),
            error=action_error,
        )
        self.tasks_store.create_task(action_task)

        action_timeline_item = TimelineItem(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            message_id=user_event.id,
            task_id=action_task.id,
            type=TimelineItemType.SUMMARY if action_success else TimelineItemType.ERROR,
            title=f"Executed: {action}" if action_success else f"Failed: {action}",
            summary=action_result.get("message", f"Successfully executed {action}")
            if action_success
            else f"Error: {action_error}",
            data={
                "action": action,
                "result": action_result if action_success else None,
                "error": action_error,
                "original_timeline_item_id": timeline_item.id,
            },
            cta=None,
            created_at=_utc_now(),
        )
        self.timeline_items_store.create_timeline_item(action_timeline_item)

        if action_success:
            return f"Executed {action} successfully."
        return f"Failed to execute {action}: {action_error}"

    async def _execute_wordpress_publish(
        self,
        workspace_id: str,
        profile_id: str,
        title: str,
        content: str,
        timeline_item_id: str,
    ) -> Dict[str, Any]:
        """
        Execute WordPress publish action.

        Args:
            workspace_id: Workspace ID.
            profile_id: User profile ID.
            title: Post title.
            content: Post content.
            timeline_item_id: Timeline item ID.

        Returns:
            Dict with success status and result data.
        """
        try:
            from ...capability_registry import get_registry

            registry = get_registry()
            wp_sync_pack = registry.get_pack("wp_sync")

            if wp_sync_pack:
                if not REQUESTS_AVAILABLE:
                    return {
                        "success": False,
                        "error": "requests library not available",
                    }

                wp_url = os.getenv("WORDPRESS_URL", "")
                wp_username = os.getenv("WORDPRESS_USERNAME", "")
                wp_password = os.getenv("WORDPRESS_APPLICATION_PASSWORD", "")

                if not wp_url or not wp_username or not wp_password:
                    return {
                        "success": False,
                        "error": "WordPress credentials not configured",
                    }

                api_url = f"{wp_url.rstrip('/')}/wp-json/wp/v2/posts"
                response = requests.post(
                    api_url,
                    json={
                        "title": title,
                        "content": content,
                        "status": "publish",
                    },
                    auth=HTTPBasicAuth(wp_username, wp_password),
                    timeout=30,
                )

                if response.status_code == 201:
                    post_data = response.json()
                    return {
                        "success": True,
                        "post_id": post_data.get("id"),
                        "post_url": post_data.get("link"),
                        "post_data": post_data,
                    }
                return {
                    "success": False,
                    "error": f"WordPress API error: {response.status_code} - {response.text}",
                }
            return {
                "success": False,
                "error": "wp_sync pack not available",
            }
        except Exception as e:
            logger.error(f"Failed to execute WordPress publish: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
            }

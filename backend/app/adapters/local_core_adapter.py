"""
Local Core API Adapter

Python adapter for Local Core API, providing methods for Playbooks to interact
with Local Core services (Artifacts, IG Posts, OAuth).
"""

import requests
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class LocalCoreConfig:
    """Configuration for Local Core Adapter"""
    base_url: str
    api_key: Optional[str] = None
    timeout: int = 30


class LocalCoreAdapter:
    """
    Local-Core API adapter

    Provides methods to interact with Local Core API endpoints.
    Used by Playbooks and other backend services.
    """

    def __init__(self, config: LocalCoreConfig):
        self.base_url = config.base_url.rstrip('/')
        self.session = requests.Session()
        self.timeout = config.timeout

        if config.api_key:
            self.session.headers['Authorization'] = f'Bearer {config.api_key}'

        self.session.headers['Content-Type'] = 'application/json'

    def list_artifacts(
        self,
        workspace_id: str,
        playbook_code: Optional[str] = None,
        include_content: bool = False,
        include_preview: bool = True,
        platform: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        **filters
    ) -> Dict[str, Any]:
        """
        List artifacts for a workspace

        Args:
            workspace_id: Workspace ID
            playbook_code: Filter by playbook code
            include_content: Include full content in response
            include_preview: Include content preview
            platform: Filter by platform
            limit: Maximum number of artifacts
            offset: Offset for pagination
            **filters: Additional filter parameters

        Returns:
            Dictionary containing artifacts list and pagination info
        """
        params = {
            'include_content': include_content,
            'include_preview': include_preview,
            'limit': limit,
            'offset': offset,
        }

        if playbook_code:
            params['playbook_code'] = playbook_code
        if platform:
            params['platform'] = platform

        params.update(filters)

        try:
            response = self.session.get(
                f'{self.base_url}/api/v1/workspaces/{workspace_id}/artifacts',
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to list artifacts: {e}")
            raise

    def get_artifact(
        self,
        workspace_id: str,
        artifact_id: str
    ) -> Dict[str, Any]:
        """
        Get a single artifact by ID

        Args:
            workspace_id: Workspace ID
            artifact_id: Artifact ID

        Returns:
            Artifact dictionary
        """
        try:
            response = self.session.get(
                f'{self.base_url}/api/v1/workspaces/{workspace_id}/artifacts/{artifact_id}',
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get artifact: {e}")
            raise

    def list_ig_posts(
        self,
        workspace_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        List IG posts for a workspace

        Args:
            workspace_id: Workspace ID
            status: Filter by status (draft, scheduled, published, archived)
            limit: Maximum number of posts
            offset: Offset for pagination

        Returns:
            Dictionary containing posts list and pagination info
        """
        params = {
            'limit': limit,
            'offset': offset,
        }

        if status:
            params['status'] = status

        try:
            response = self.session.get(
                f'{self.base_url}/api/v1/workspaces/{workspace_id}/ig-posts',
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to list IG posts: {e}")
            raise

    def schedule_ig_post(
        self,
        workspace_id: str,
        post_id: str,
        scheduled_time: str
    ) -> Dict[str, Any]:
        """
        Schedule an IG post

        Args:
            workspace_id: Workspace ID
            post_id: Post ID (format: artifact_id-index)
            scheduled_time: Scheduled time in ISO format

        Returns:
            Updated post dictionary
        """
        try:
            response = self.session.patch(
                f'{self.base_url}/api/v1/workspaces/{workspace_id}/ig-posts/{post_id}/schedule',
                params={'scheduled_time': scheduled_time},
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to schedule IG post: {e}")
            raise


class LocalCorePlaybookTools:
    """
    High-level tools for Playbooks

    Provides convenient methods for Playbooks to interact with Local Core.
    """

    def __init__(self, adapter: LocalCoreAdapter):
        self.adapter = adapter

    async def get_ig_context_for_generation(
        self,
        workspace_id: str,
        n_recent: int = 20
    ) -> str:
        """
        Get IG context for post generation

        Retrieves recent IG posts and formats them as context for LLM prompts.

        Args:
            workspace_id: Workspace ID
            n_recent: Number of recent posts to retrieve

        Returns:
            Formatted context string
        """
        try:
            response = self.adapter.list_ig_posts(
                workspace_id=workspace_id,
                limit=n_recent
            )
            posts = response.get('posts', [])

            context = "# Recent Instagram Posts:\n\n"
            for i, post in enumerate(posts, 1):
                text = post.get('text', '')
                preview = text[:100] + '...' if len(text) > 100 else text
                context += f"{i}. {preview}\n"

            return context
        except Exception as e:
            logger.error(f"Failed to get IG context: {e}")
            return "# Recent Instagram Posts:\n\n(Unable to load recent posts)"







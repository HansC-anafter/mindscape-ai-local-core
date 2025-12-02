"""
Tool abstraction layer for my-agent-mindscape.

This module provides a unified interface for connecting to external services
like WordPress, Notion, Google Drive, etc.

Core design:
- WordPress tools are the primary focus (P0)
- Third-party SaaS tools use BYO (Bring Your Own) mode
- All tools implement the same base interface
- Support for both local and remote connection types
"""


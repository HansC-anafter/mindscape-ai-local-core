"""
Agent Registry

Auto-discovers and registers external agent adapters from the agents/ directory.
Each agent should have an AGENT.md manifest file.
"""

import importlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

# Optional yaml support - falls back to simple parsing if not available
try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from backend.app.services.external_agents.core.base_adapter import BaseAgentAdapter

logger = logging.getLogger(__name__)


@dataclass
class AgentManifest:
    """
    Parsed AGENT.md manifest for an external agent.

    Similar to SKILL.md for capability packs.
    """

    name: str
    """Agent name (e.g., 'openclaw', 'autogpt')."""

    version: str
    """Agent adapter version."""

    description: str
    """Human-readable description."""

    cli_command: Optional[str] = None
    """CLI command to invoke the agent."""

    min_version: Optional[str] = None
    """Minimum required agent version."""

    # Default configuration
    defaults: Dict[str, Any] = field(default_factory=dict)
    """Default configuration values."""

    # Dependencies
    dependencies: List[str] = field(default_factory=list)
    """Required pip packages or repos."""

    # Governance
    risk_level: str = "high"
    """Default risk level: low, medium, high, critical."""

    requires_sandbox: bool = True
    """Whether sandbox is required."""

    # File paths
    adapter_module: Optional[str] = None
    """Python module path for the adapter."""

    manifest_path: Optional[str] = None
    """Path to the AGENT.md file."""


class AgentRegistry:
    """
    Registry for external agent adapters.

    Auto-discovers agents from the agents/ directory and provides
    a unified interface for the Playbook engine.

    Usage:
        registry = get_agent_registry()
        openclaw = registry.get_adapter("openclaw")
        if await openclaw.is_available():
            response = await openclaw.execute(request)
    """

    _instance: Optional["AgentRegistry"] = None

    def __init__(self):
        """Initialize the registry."""
        self._adapters: Dict[str, BaseAgentAdapter] = {}
        self._manifests: Dict[str, AgentManifest] = {}
        self._agents_dir = Path(__file__).parent.parent / "agents"

    @classmethod
    def get_instance(cls) -> "AgentRegistry":
        """Get or create the singleton registry instance."""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.discover_agents()
        return cls._instance

    def discover_agents(self) -> None:
        """
        Discover and register all agents in the agents/ directory.

        Each agent directory should contain:
        - AGENT.md: Manifest with metadata (YAML frontmatter)
        - adapter.py: Implementation of BaseAgentAdapter
        """
        if not self._agents_dir.exists():
            logger.warning(f"Agents directory not found: {self._agents_dir}")
            return

        for agent_dir in self._agents_dir.iterdir():
            if not agent_dir.is_dir():
                continue

            if agent_dir.name.startswith("_") or agent_dir.name.startswith("."):
                continue

            try:
                self._load_agent(agent_dir)
            except Exception as e:
                logger.error(f"Failed to load agent {agent_dir.name}: {e}")

    def _load_agent(self, agent_dir: Path) -> None:
        """Load a single agent from its directory."""
        agent_name = agent_dir.name

        # Parse AGENT.md manifest
        manifest_path = agent_dir / "AGENT.md"
        if manifest_path.exists():
            manifest = self._parse_manifest(manifest_path)
            manifest.manifest_path = str(manifest_path)
        else:
            # Create default manifest
            manifest = AgentManifest(
                name=agent_name,
                version="0.0.0",
                description=f"Auto-discovered agent: {agent_name}",
            )

        # Load adapter module
        adapter_path = agent_dir / "adapter.py"
        if adapter_path.exists():
            try:
                adapter = self._load_adapter(agent_name, adapter_path)
                if adapter:
                    self._adapters[agent_name] = adapter
                    self._manifests[agent_name] = manifest
                    logger.info(f"Registered agent: {agent_name}")
            except Exception as e:
                logger.error(f"Failed to load adapter for {agent_name}: {e}")

    def _parse_manifest(self, manifest_path: Path) -> AgentManifest:
        """Parse AGENT.md file with YAML frontmatter."""
        content = manifest_path.read_text()

        # Extract YAML frontmatter
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not frontmatter_match:
            return AgentManifest(
                name=manifest_path.parent.name,
                version="0.0.0",
                description="No manifest found",
            )

        frontmatter_text = frontmatter_match.group(1)

        if HAS_YAML:
            try:
                frontmatter = yaml.safe_load(frontmatter_text)
            except yaml.YAMLError as e:
                logger.warning(f"Failed to parse YAML in {manifest_path}: {e}")
                frontmatter = {}
        else:
            # Simple fallback parsing without yaml
            frontmatter = self._simple_yaml_parse(frontmatter_text)

        # Extract governance settings
        governance = frontmatter.get("governance", {})

        return AgentManifest(
            name=frontmatter.get("name", manifest_path.parent.name),
            version=frontmatter.get("version", "0.0.0"),
            description=frontmatter.get("description", ""),
            cli_command=frontmatter.get("cli_command"),
            min_version=frontmatter.get("min_version"),
            defaults=frontmatter.get("defaults", {}),
            dependencies=frontmatter.get("dependencies", []),
            risk_level=governance.get("risk_level", "high"),
            requires_sandbox=governance.get("requires_sandbox", True),
        )

    def _simple_yaml_parse(self, text: str) -> Dict[str, Any]:
        """Simple YAML-like parsing for basic key: value pairs."""
        result: Dict[str, Any] = {}
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if value:
                    result[key] = value
        return result

    def _load_adapter(
        self, agent_name: str, adapter_path: Path
    ) -> Optional[BaseAgentAdapter]:
        """Dynamically load an adapter module."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            f"external_agents.agents.{agent_name}.adapter",
            adapter_path,
        )
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Find the adapter class
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseAgentAdapter)
                and obj is not BaseAgentAdapter
            ):
                return obj()

        return None

    def get_adapter(self, agent_name: str) -> Optional[BaseAgentAdapter]:
        """Get an adapter by name."""
        return self._adapters.get(agent_name)

    def get_manifest(self, agent_name: str) -> Optional[AgentManifest]:
        """Get a manifest by name."""
        return self._manifests.get(agent_name)

    def list_agents(self) -> List[str]:
        """List all registered agent names."""
        return list(self._adapters.keys())

    def get_all_manifests(self) -> Dict[str, AgentManifest]:
        """Get all registered manifests."""
        return self._manifests.copy()

    async def check_availability(self) -> Dict[str, bool]:
        """Check availability of all registered agents."""
        result = {}
        for name, adapter in self._adapters.items():
            try:
                result[name] = await adapter.is_available()
            except Exception:
                result[name] = False
        return result


# Singleton accessor
def get_agent_registry() -> AgentRegistry:
    """Get the global agent registry instance."""
    return AgentRegistry.get_instance()

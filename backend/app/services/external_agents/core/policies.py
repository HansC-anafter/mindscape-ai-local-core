"""
Doer Workspace Policies

Defines configurable policies for Doer Workspaces that govern
external agent execution.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class RetentionTier(Enum):
    """Pack retention tier."""

    EPHEMERAL = "ephemeral"  # Task duration only
    CACHED = "cached"  # 7 days or until evicted
    RESIDENT = "resident"  # Permanent (promoted to pack)


class RiskLevel(Enum):
    """Permission risk level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SandboxPolicy:
    """
    Sandbox filesystem policy for Doer Workspace.

    Defines what paths the agent can access and how.
    """

    # Base sandbox path
    sandbox_path: Path

    # Writable directories (relative to sandbox)
    writable_paths: List[str] = field(
        default_factory=lambda: [
            "workspace",
            ".quarantine",
            ".cache",
        ]
    )

    # Read-only directories
    readonly_paths: List[str] = field(
        default_factory=lambda: [
            ".mindscape",
        ]
    )

    # Never accessible (not mounted)
    forbidden_paths: List[str] = field(
        default_factory=lambda: [
            ".secrets",
        ]
    )

    def get_full_path(self, relative: str) -> Path:
        """Get full path within sandbox."""
        return self.sandbox_path / relative

    def is_writable(self, path: str) -> bool:
        """Check if a path is writable."""
        for writable in self.writable_paths:
            if path.startswith(writable):
                return True
        return False

    def is_accessible(self, path: str) -> bool:
        """Check if a path is accessible at all."""
        for forbidden in self.forbidden_paths:
            if path.startswith(forbidden):
                return False
        return self.is_writable(path) or any(
            path.startswith(ro) for ro in self.readonly_paths
        )

    def ensure_structure(self) -> None:
        """Create required directory structure."""
        for path in self.writable_paths + self.readonly_paths:
            (self.sandbox_path / path).mkdir(parents=True, exist_ok=True)

        # Create quarantine subdirectories
        (self.sandbox_path / ".quarantine" / "pending").mkdir(
            parents=True, exist_ok=True
        )
        (self.sandbox_path / ".quarantine" / "rejected").mkdir(
            parents=True, exist_ok=True
        )


@dataclass
class NetworkPolicy:
    """
    Network egress policy for Doer Workspace.

    Controls what external hosts the agent can access.
    """

    mode: str = "allowlist"  # "allowlist" or "denylist"

    # Default allowed hosts
    allowed_hosts: Set[str] = field(
        default_factory=lambda: {
            # Package registries
            "pypi.org",
            "files.pythonhosted.org",
            "registry.npmjs.org",
            "registry.yarnpkg.com",
            # Code repositories
            "github.com",
            "api.github.com",
            "raw.githubusercontent.com",
            "gitlab.com",
            # Container registries
            "docker.io",
            "ghcr.io",
            # Documentation
            "docs.python.org",
            "developer.mozilla.org",
        }
    )

    # Always denied hosts
    denied_hosts: Set[str] = field(
        default_factory=lambda: {
            "*.internal",
            "10.*",
            "192.168.*",
            "172.16.*",
            "localhost",
            "127.0.0.1",
        }
    )

    # Rate limiting
    requests_per_minute: int = 60
    bandwidth_mbps: int = 10

    def is_allowed(self, host: str) -> bool:
        """Check if a host is allowed."""
        # Check denied first
        for pattern in self.denied_hosts:
            if self._matches_pattern(host, pattern):
                return False

        # In allowlist mode, must be explicitly allowed
        if self.mode == "allowlist":
            return any(
                self._matches_pattern(host, pattern) for pattern in self.allowed_hosts
            )

        # In denylist mode, allowed by default
        return True

    def _matches_pattern(self, host: str, pattern: str) -> bool:
        """Check if host matches a pattern (supports wildcards)."""
        if pattern.startswith("*."):
            return host.endswith(pattern[1:]) or host == pattern[2:]
        if pattern.endswith(".*"):
            return host.startswith(pattern[:-1])
        return host == pattern

    def add_allowed_host(self, host: str) -> None:
        """Add a host to the allowed list."""
        self.allowed_hosts.add(host)

    def to_docker_config(self) -> Dict[str, Any]:
        """Generate Docker network configuration."""
        return {
            "network_mode": "bridge",
            "sysctls": {
                "net.ipv4.ip_forward": "0",
            },
            # Note: Actual firewall rules need iptables or network plugin
            "labels": {
                "mindscape.network.mode": self.mode,
                "mindscape.network.allowed": ",".join(sorted(self.allowed_hosts)),
            },
        }


@dataclass
class ToolAcquisitionPolicy:
    """
    Policy for agent tool/dependency acquisition.

    Defines the two-stage Acquire → Promote flow.
    """

    # Quarantine settings
    quarantine_path: str = ".quarantine/pending"
    rejected_path: str = ".quarantine/rejected"

    # Auto-approve settings
    trusted_publishers: Set[str] = field(
        default_factory=lambda: {
            "anthropic",
            "openai",
            "langchain",
            "huggingface",
        }
    )

    auto_approve_low_risk: bool = True
    auto_approve_trusted_publishers: bool = True

    # Verification requirements
    require_signature: bool = False  # True for production
    require_checksum: bool = True

    def should_auto_approve(
        self,
        publisher: Optional[str],
        risk_level: RiskLevel,
        has_signature: bool,
    ) -> bool:
        """Determine if a tool activation should auto-approve."""
        # Check publisher trust
        if publisher and publisher in self.trusted_publishers:
            if self.auto_approve_trusted_publishers:
                return True

        # Check risk level
        if risk_level == RiskLevel.LOW and self.auto_approve_low_risk:
            return True

        # High/critical risk always requires approval
        if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return False

        return False


@dataclass
class SecretsPolicy:
    """
    Policy for secrets/credentials handling.

    Secrets are NEVER mounted into agent environment.
    Works with ModelPolicy to control which APIs can receive credentials.
    """

    # Allowed API endpoints for secret injection (whitelist)
    # Only these APIs can receive credentials via governance layer
    allowed_apis: Set[str] = field(
        default_factory=lambda: {
            "api.anthropic.com",
            "api.openai.com",
        }
    )

    # Require explicit intent approval for each API
    require_intent_approval: bool = True

    # Audit all secret access
    audit_enabled: bool = True

    def can_access(self, api: str, intent_approved: bool = False) -> bool:
        """Check if secret access is allowed for an API."""
        if api not in self.allowed_apis:
            return False

        if self.require_intent_approval and not intent_approved:
            return False

        return True


@dataclass
class ModelPolicy:
    """
    Policy for controlling which model providers an agent can use.

    Uses whitelist approach - only explicitly allowed providers can be used.
    Works with SecretsPolicy to enforce local-only execution.
    """

    # Allowed model providers (whitelist)
    # Only these providers can be used by the agent
    allowed_providers: Set[str] = field(
        default_factory=lambda: {
            "ollama",  # Local Ollama
            "llama-cpp",  # Local GGUF models
        }
    )

    # Provider endpoints (for validation)
    provider_endpoints: Dict[str, str] = field(
        default_factory=lambda: {
            "ollama": "localhost:11434",
            "llama-cpp": "local",
            "openai": "api.openai.com",
            "anthropic": "api.anthropic.com",
            "vertex-ai": "*.googleapis.com",
        }
    )

    # Force all LLM calls through Mindscape proxy
    # When True, agent cannot directly call LLM APIs
    force_proxy: bool = True

    # Allow agent to specify model name within allowed providers
    allow_model_selection: bool = True

    # Default model for each provider
    default_models: Dict[str, str] = field(
        default_factory=lambda: {
            "ollama": "llama3",
            "llama-cpp": "default",
        }
    )

    def is_provider_allowed(self, provider: str) -> bool:
        """Check if a provider is in the whitelist."""
        return provider.lower() in {p.lower() for p in self.allowed_providers}

    def is_local_only(self) -> bool:
        """Check if policy restricts to local models only."""
        cloud_providers = {"openai", "anthropic", "vertex-ai", "azure-openai"}
        return not any(p in self.allowed_providers for p in cloud_providers)

    def get_allowed_providers(self) -> List[str]:
        """Get list of allowed providers."""
        return list(self.allowed_providers)

    def add_provider(self, provider: str) -> None:
        """Add a provider to the whitelist."""
        self.allowed_providers.add(provider)

    def remove_provider(self, provider: str) -> None:
        """Remove a provider from the whitelist."""
        self.allowed_providers.discard(provider)

    @classmethod
    def local_only(cls) -> "ModelPolicy":
        """Create a local-only policy (no cloud providers)."""
        return cls(
            allowed_providers={"ollama", "llama-cpp"},
            force_proxy=True,
        )

    @classmethod
    def cloud_allowed(cls, providers: Optional[Set[str]] = None) -> "ModelPolicy":
        """Create a policy that allows specific cloud providers."""
        default_cloud = {"ollama", "llama-cpp", "openai", "anthropic"}
        return cls(
            allowed_providers=providers or default_cloud,
            force_proxy=True,
        )


@dataclass
class RetentionPolicy:
    """
    Policy for installed tool/dependency retention.
    """

    default_tier: RetentionTier = RetentionTier.EPHEMERAL

    # Auto-upgrade to cached after N uses
    auto_cache_threshold: int = 3

    # Resident promotion requires approval
    resident_requires_approval: bool = True

    # Cache TTL in days
    cache_ttl_days: int = 7

    # Max cache size in MB
    max_cache_size_mb: int = 1024


@dataclass
class DoerWorkspaceConfig:
    """
    Complete configuration for a Doer Workspace.

    Combines all policies into a single configuration object.
    """

    workspace_id: str
    sandbox_path: Path

    sandbox: SandboxPolicy = field(default_factory=SandboxPolicy)
    network: NetworkPolicy = field(default_factory=NetworkPolicy)
    tool_acquisition: ToolAcquisitionPolicy = field(
        default_factory=ToolAcquisitionPolicy
    )
    secrets: SecretsPolicy = field(default_factory=SecretsPolicy)
    models: ModelPolicy = field(default_factory=ModelPolicy)  # NEW: Model restrictions
    retention: RetentionPolicy = field(default_factory=RetentionPolicy)

    @classmethod
    def from_workspace(
        cls, workspace_id: str, base_path: Path
    ) -> "DoerWorkspaceConfig":
        """Create default configuration for a workspace."""
        sandbox_path = base_path / workspace_id / "sandbox"

        return cls(
            workspace_id=workspace_id,
            sandbox_path=sandbox_path,
            sandbox=SandboxPolicy(sandbox_path=sandbox_path),
            network=NetworkPolicy(),
            tool_acquisition=ToolAcquisitionPolicy(),
            secrets=SecretsPolicy(),
            models=ModelPolicy(),  # Default: local-only
            retention=RetentionPolicy(),
        )

    @classmethod
    def local_only_workspace(
        cls, workspace_id: str, base_path: Path
    ) -> "DoerWorkspaceConfig":
        """Create a workspace config that restricts to local models only."""
        config = cls.from_workspace(workspace_id, base_path)
        config.models = ModelPolicy.local_only()
        # Also restrict secrets to prevent cloud API access
        config.secrets = SecretsPolicy(allowed_apis=set())  # No cloud APIs
        return config

    def apply_agent_overrides(self, agent_manifest: Dict[str, Any]) -> None:
        """Apply overrides from an agent's AGENT.md manifest."""
        overrides = agent_manifest.get("overrides", {})

        # Network overrides
        if "network" in overrides:
            additional = overrides["network"].get("additional_hosts", [])
            for host in additional:
                self.network.add_allowed_host(host)

        # Retention overrides
        if "retention" in overrides:
            tier = overrides["retention"].get("default_tier")
            if tier:
                self.retention.default_tier = RetentionTier(tier)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "workspace_id": self.workspace_id,
            "sandbox_path": str(self.sandbox_path),
            "network": {
                "mode": self.network.mode,
                "allowed_hosts": list(self.network.allowed_hosts),
            },
            "retention": {
                "default_tier": self.retention.default_tier.value,
            },
        }

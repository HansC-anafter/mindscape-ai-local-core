"""
Topology Validator

Validates topology routing against agent roster to ensure consistency.
"""

from typing import Dict, List, Optional
from backend.app.models.playbook import AgentDefinition
from backend.app.models.workspace_runtime_profile import TopologyRouting
import logging

logger = logging.getLogger(__name__)


class TopologyValidationError(Exception):
    """Topology validation error"""
    pass


class TopologyValidator:
    """
    Topology Validator - 驗證 topology 與 agent roster

    確保 topology routing 中引用的 agent_id 都在 playbook 的 agent roster 中存在。
    """

    def validate(
        self,
        topology: TopologyRouting,
        agent_roster: Optional[Dict[str, AgentDefinition]]
    ) -> bool:
        """
        Validate topology routing against agent roster

        Args:
            topology: TopologyRouting configuration
            agent_roster: Agent roster from playbook (dict of agent_id -> AgentDefinition)

        Returns:
            True if valid

        Raises:
            TopologyValidationError: If validation fails
        """
        if not agent_roster:
            # If no agent roster, topology should be empty or None
            if topology and topology.agent_routing_rules:
                raise TopologyValidationError(
                    "Topology routing defined but no agent roster provided"
                )
            return True

        # Validate all agent IDs in routing rules exist in roster
        for from_agent_id, to_agent_ids in topology.agent_routing_rules.items():
            # Validate from_agent_id
            if from_agent_id not in agent_roster:
                raise TopologyValidationError(
                    f"Agent '{from_agent_id}' in routing rules not found in agent roster. "
                    f"Available agents: {list(agent_roster.keys())}"
                )

            # Validate to_agent_ids
            for to_agent_id in to_agent_ids:
                if to_agent_id not in agent_roster:
                    raise TopologyValidationError(
                        f"Agent '{to_agent_id}' in routing rules not found in agent roster. "
                        f"Available agents: {list(agent_roster.keys())}"
                    )

        # Validate pattern configuration
        self._validate_pattern_config(topology)

        return True

    def _validate_pattern_config(self, topology: TopologyRouting):
        """
        Validate pattern-specific configuration

        Args:
            topology: TopologyRouting configuration

        Raises:
            TopologyValidationError: If pattern config is invalid
        """
        pattern = topology.default_pattern
        config = topology.pattern_config

        if pattern == "loop":
            # Loop pattern requires max_iterations
            if "max_iterations" not in config:
                logger.warning("Loop pattern should specify max_iterations in pattern_config")
        elif pattern == "parallel":
            # Parallel pattern may specify max_parallel_agents
            if "max_parallel_agents" in config:
                max_parallel = config["max_parallel_agents"]
                if not isinstance(max_parallel, int) or max_parallel < 1:
                    raise TopologyValidationError(
                        "pattern_config.max_parallel_agents must be a positive integer"
                    )
        elif pattern == "hierarchical":
            # Hierarchical pattern may specify root_agent
            if "root_agent" in config:
                root_agent = config["root_agent"]
                if not isinstance(root_agent, str):
                    raise TopologyValidationError(
                        "pattern_config.root_agent must be a string (agent_id)"
                    )

    def get_available_agents(
        self,
        agent_roster: Optional[Dict[str, AgentDefinition]]
    ) -> List[str]:
        """
        Get list of available agent IDs from roster

        Args:
            agent_roster: Agent roster from playbook

        Returns:
            List of agent IDs
        """
        if not agent_roster:
            return []
        return list(agent_roster.keys())

    def get_routing_paths(
        self,
        topology: TopologyRouting,
        start_agent_id: Optional[str] = None
    ) -> List[List[str]]:
        """
        Get all possible routing paths from topology

        Args:
            topology: TopologyRouting configuration
            start_agent_id: Optional starting agent ID

        Returns:
            List of routing paths (each path is a list of agent IDs)
        """
        if not topology.agent_routing_rules:
            return []

        paths = []

        if start_agent_id:
            # Start from specific agent
            self._find_paths_from_agent(
                topology.agent_routing_rules,
                start_agent_id,
                [start_agent_id],
                paths,
                visited=set()
            )
        else:
            # Find all paths from all starting agents
            for from_agent in topology.agent_routing_rules.keys():
                self._find_paths_from_agent(
                    topology.agent_routing_rules,
                    from_agent,
                    [from_agent],
                    paths,
                    visited=set()
                )

        return paths

    def _find_paths_from_agent(
        self,
        routing_rules: Dict[str, List[str]],
        current_agent: str,
        current_path: List[str],
        all_paths: List[List[str]],
        visited: set,
        max_depth: int = 10
    ):
        """
        Recursively find all paths from a starting agent

        Args:
            routing_rules: Agent routing rules
            current_agent: Current agent ID
            current_path: Current path (list of agent IDs)
            all_paths: List to collect all paths
            visited: Set of visited agents (to prevent cycles)
            max_depth: Maximum path depth
        """
        if len(current_path) > max_depth:
            return

        if current_agent in visited:
            # Cycle detected, save path and stop
            all_paths.append(current_path.copy())
            return

        visited.add(current_agent)

        # Get next agents
        next_agents = routing_rules.get(current_agent, [])
        if not next_agents:
            # End of path
            all_paths.append(current_path.copy())
        else:
            # Continue to next agents
            for next_agent in next_agents:
                new_path = current_path + [next_agent]
                self._find_paths_from_agent(
                    routing_rules,
                    next_agent,
                    new_path,
                    all_paths,
                    visited.copy(),
                    max_depth
                )

        visited.remove(current_agent)


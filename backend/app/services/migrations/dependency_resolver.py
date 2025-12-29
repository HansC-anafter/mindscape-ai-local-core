"""Resolves migration dependencies and performs topological sort."""

import logging
from typing import List, Dict, Set, Optional
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class DependencyResolver:
    """Resolves dependencies and sorts migrations topologically."""

    def __init__(self):
        self.graph = defaultdict(list)  # capability -> [dependencies]
        self.in_degree = defaultdict(int)

    def build_graph(self, metadata_list: List) -> None:
        """Build dependency graph from metadata list."""
        capability_map = {m.capability_code: m for m in metadata_list}

        for metadata in metadata_list:
            self.graph[metadata.capability_code] = []
            self.in_degree[metadata.capability_code] = 0

        for metadata in metadata_list:
            for dep in metadata.depends_on:
                # Parse dependency: "capability@version" or "capability"
                dep_code = dep.split('@')[0]
                if dep_code in capability_map:
                    self.graph[dep_code].append(metadata.capability_code)
                    self.in_degree[metadata.capability_code] += 1
                else:
                    logger.warning(f"Dependency {dep_code} not found for {metadata.capability_code}")

    def detect_cycles(self) -> List[List[str]]:
        """Detect cycles in dependency graph using DFS."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = defaultdict(lambda: WHITE)
        cycles = []

        def dfs(node: str, path: List[str]) -> None:
            if color[node] == GRAY:
                # Found a cycle
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return
            if color[node] == BLACK:
                return

            color[node] = GRAY
            path.append(node)

            for neighbor in self.graph[node]:
                dfs(neighbor, path)

            path.pop()
            color[node] = BLACK

        for node in list(self.graph.keys()):
            if color[node] == WHITE:
                dfs(node, [])

        return cycles

    def topological_sort(self, metadata_list: List) -> List:
        """Sort capabilities by dependency order."""
        cycles = self.detect_cycles()
        if cycles:
            raise ValueError(f"Circular dependencies detected: {cycles}")

        # Build graph
        self.build_graph(metadata_list)

        # Topological sort using Kahn's algorithm
        queue = deque([cap for cap, degree in self.in_degree.items() if degree == 0])
        result = []

        while queue:
            node = queue.popleft()
            result.append(node)

            for neighbor in self.graph[node]:
                self.in_degree[neighbor] -= 1
                if self.in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Check for remaining nodes (shouldn't happen if no cycles)
        if len(result) != len(metadata_list):
            remaining = set(m.capability_code for m in metadata_list) - set(result)
            raise ValueError(f"Could not resolve all dependencies. Remaining: {remaining}")

        # Map back to metadata objects
        capability_map = {m.capability_code: m for m in metadata_list}
        return [capability_map[cap] for cap in result]


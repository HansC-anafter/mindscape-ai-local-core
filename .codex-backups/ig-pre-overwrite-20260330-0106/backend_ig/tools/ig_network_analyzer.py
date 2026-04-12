"""
IG Network Analyzer Tool

Analyzes follow relationships across seeds to find common following patterns
and community clusters using graph algorithms.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _build_graph_from_edges(edges: List[Dict[str, Any]]):
    """Build a NetworkX graph from follow edges."""
    try:
        import networkx as nx
    except ImportError:
        logger.error("[IGNetworkAnalyzer] networkx not installed")
        return None

    G = nx.DiGraph()

    for edge in edges:
        source = edge.get("source_handle")
        target = edge.get("target_handle")
        if source and target:
            G.add_edge(source, target)

    return G


def _find_common_following(
    edges: List[Dict[str, Any]], seeds: List[str], min_overlap: int = 2
) -> List[Dict[str, Any]]:
    """
    Find accounts followed by multiple seeds.
    Returns accounts with their follower count across seeds.
    """
    # Build mapping: target -> set of seeds following them
    target_followers: Dict[str, set] = {}

    for edge in edges:
        source = edge.get("source_handle")
        target = edge.get("target_handle")
        if source in seeds and target:
            if target not in target_followers:
                target_followers[target] = set()
            target_followers[target].add(source)

    # Filter by min_overlap
    common = []
    for target, followers in target_followers.items():
        if len(followers) >= min_overlap:
            common.append(
                {
                    "handle": target,
                    "followed_by_count": len(followers),
                    "followed_by": list(followers),
                }
            )

    # Sort by followed_by_count descending
    common.sort(key=lambda x: x["followed_by_count"], reverse=True)

    return common


def _detect_communities(
    edges: List[Dict[str, Any]],
    resolution: float = 1.0,
) -> Dict[str, Any]:
    """
    Detect communities using Louvain algorithm.
    Returns community assignments and statistics.
    """
    try:
        import networkx as nx
        from community import community_louvain
    except ImportError as e:
        logger.error(f"[IGNetworkAnalyzer] Missing dependency: {e}")
        return {"error": "python-louvain not installed"}

    G = _build_graph_from_edges(edges)
    if not G or G.number_of_nodes() == 0:
        return {"error": "No graph data", "communities": []}

    # Convert to undirected for community detection
    G_undirected = G.to_undirected()

    # Run Louvain
    partition = community_louvain.best_partition(G_undirected, resolution=resolution)

    # Group by community
    communities: Dict[int, List[str]] = {}
    for node, comm_id in partition.items():
        if comm_id not in communities:
            communities[comm_id] = []
        communities[comm_id].append(node)

    # Build result
    result = {
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "num_communities": len(communities),
        "modularity": community_louvain.modularity(partition, G_undirected),
        "communities": [
            {
                "id": comm_id,
                "size": len(members),
                "members": members[:20],  # Limit for readability
            }
            for comm_id, members in sorted(
                communities.items(), key=lambda x: len(x[1]), reverse=True
            )
        ],
    }

    return result


async def ig_network_analyzer(
    workspace_id: str,
    seeds: List[str],
    analysis_type: str = "common_following",  # "common_following" | "community"
    min_overlap: int = 2,
    resolution: float = 1.0,
) -> Dict[str, Any]:
    """
    Analyze follow relationships across seeds.

    Analysis types:
    - common_following: Find accounts followed by multiple seeds
    - community: Detect communities using Louvain clustering

    Args:
        workspace_id: Workspace ID
        seeds: List of seed account handles to analyze
        analysis_type: Type of analysis to perform
        min_overlap: Minimum seeds following an account (for common_following)
        resolution: Louvain resolution parameter (for community)
    """
    logger.info(f"[IGNetworkAnalyzer] Starting network analysis")
    logger.info(f"  workspace_id: {workspace_id}")
    logger.info(f"  seeds: {seeds}")
    logger.info(f"  analysis_type: {analysis_type}")

    if not seeds or len(seeds) < 2:
        return {
            "status": "error",
            "error": "At least 2 seeds required for network analysis",
        }

    # Fetch edges from database
    edges: List[Dict[str, Any]] = []
    try:
        from sqlalchemy import create_engine, text

        try:
            from app.database.config import get_postgres_url_core

            engine = create_engine(get_postgres_url_core())
        except ImportError:
            from backend.app.core.database import get_db_engine

            engine = get_db_engine()
        with engine.connect() as conn:
            # Get all edges where source_handle is one of the seeds
            placeholders = ", ".join([f":seed_{i}" for i in range(len(seeds))])
            query = text(
                f"""
                SELECT source_handle, target_handle
                FROM ig_follow_edges
                WHERE workspace_id = :workspace_id
                AND source_handle IN ({placeholders})
            """
            )
            params = {"workspace_id": workspace_id}
            for i, seed in enumerate(seeds):
                params[f"seed_{i}"] = seed

            result = conn.execute(query, params)
            edges = [
                {"source_handle": row[0], "target_handle": row[1]}
                for row in result.fetchall()
            ]

    except Exception as e:
        logger.error(f"[IGNetworkAnalyzer] Database error: {e}")
        return {
            "status": "error",
            "error": str(e),
        }

    if not edges:
        return {
            "status": "error",
            "error": f"No follow edges found for seeds: {seeds}",
        }

    logger.info(f"[IGNetworkAnalyzer] Loaded {len(edges)} edges")

    # Perform analysis
    if analysis_type == "common_following":
        common = _find_common_following(edges, seeds, min_overlap)
        result = {
            "status": "success",
            "analysis_type": "common_following",
            "seeds": seeds,
            "min_overlap": min_overlap,
            "total_edges": len(edges),
            "common_following_count": len(common),
            "common_following": common[:50],
        }
    elif analysis_type == "community":
        communities = _detect_communities(edges, resolution)
        result = {
            "status": "success",
            "analysis_type": "community",
            "seeds": seeds,
            **communities,
        }
    else:
        result = {
            "status": "error",
            "error": f"Unknown analysis_type: {analysis_type}",
        }

    logger.info(f"[IGNetworkAnalyzer] Completed: {result.get('status')}")
    return result

#!/usr/bin/env python3
"""
Intent Layer v2 Metrics Monitoring Script

Monitors key metrics for Intent Layer v2 system health.

Metrics tracked:
- IntentSignal count per turn
- IntentCard auto-update success rate
- Cluster quality indicators
"""

import argparse
import sys
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.mindscape_store import MindscapeStore
from app.services.stores.intent_logs_store import IntentLogsStore
from app.services.stores.intent_clusters_store import IntentClustersStore


def parse_steward_logs(log_file: str, days: int = 7) -> Dict[str, Any]:
    """
    Parse IntentSteward logs from application log

    Args:
        log_file: Path to log file
        days: Number of days to analyze

    Returns:
        Dictionary with metrics
    """
    metrics = {
        "total_analyses": 0,
        "executed_analyses": 0,
        "observation_analyses": 0,
        "total_operations": 0,
        "create_operations": 0,
        "update_operations": 0,
        "ephemeral_tasks": 0
    }

    if not os.path.exists(log_file):
        return metrics

    cutoff_date = datetime.utcnow() - timedelta(days=days)
    pattern = re.compile(r'INTENT_STEWARD_LOG: (.+)')

    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            match = pattern.search(line)
            if match:
                params_str = match.group(1)
                params = {}
                for param in params_str.split(', '):
                    if '=' in param:
                        key, value = param.split('=', 1)
                        params[key] = value

                # Parse timestamp
                timestamp_str = params.get('timestamp', '')
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    if timestamp < cutoff_date:
                        continue
                except Exception:
                    continue

                metrics["total_analyses"] += 1

                # Check if executed
                planned_ops = int(params.get('planned_operations', 0))
                if planned_ops > 0:
                    # Likely executed (Phase 2)
                    metrics["executed_analyses"] += 1
                    metrics["total_operations"] += planned_ops
                else:
                    metrics["observation_analyses"] += 1

                ephemeral = int(params.get('ephemeral_tasks', 0))
                metrics["ephemeral_tasks"] += ephemeral

    return metrics


def analyze_intent_cards(db_path: str, profile_id: str, days: int = 7) -> Dict[str, Any]:
    """
    Analyze IntentCard metrics

    Args:
        db_path: Database path
        profile_id: Profile ID
        days: Number of days to analyze

    Returns:
        Dictionary with metrics
    """
    try:
        store = MindscapeStore(db_path=db_path)
        intents = store.list_intents(profile_id=profile_id)

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        total_intents = len(intents)
        steward_created = 0
        steward_updated = 0
        user_created = 0

        for intent in intents:
            if intent.metadata and intent.metadata.get("source") == "intent_steward_auto":
                if intent.created_at and intent.created_at >= cutoff_date:
                    steward_created += 1
                if intent.metadata.get("last_steward_update"):
                    steward_updated += 1
            else:
                if intent.created_at and intent.created_at >= cutoff_date:
                    user_created += 1

        return {
            "total_intents": total_intents,
            "steward_created": steward_created,
            "steward_updated": steward_updated,
            "user_created": user_created,
            "auto_update_rate": (steward_created + steward_updated) / max(total_intents, 1) * 100
        }
    except Exception as e:
        return {"error": str(e)}


def analyze_clusters(db_path: str, workspace_id: str, profile_id: str) -> Dict[str, Any]:
    """
    Analyze cluster quality metrics

    Args:
        db_path: Database path
        workspace_id: Workspace ID
        profile_id: Profile ID

    Returns:
        Dictionary with cluster metrics
    """
    try:
        clusters_store = IntentClustersStore(db_path=db_path)
        clusters = clusters_store.list_clusters(
            workspace_id=workspace_id,
            profile_id=profile_id
        )

        if not clusters:
            return {
                "total_clusters": 0,
                "avg_intents_per_cluster": 0,
                "clusters_with_labels": 0
            }

        total_intents = sum(len(c.intent_card_ids) for c in clusters)
        clusters_with_labels = sum(1 for c in clusters if c.label and c.label != "Unnamed Cluster")

        return {
            "total_clusters": len(clusters),
            "avg_intents_per_cluster": total_intents / len(clusters) if clusters else 0,
            "clusters_with_labels": clusters_with_labels,
            "label_quality_rate": clusters_with_labels / len(clusters) * 100 if clusters else 0
        }
    except Exception as e:
        return {"error": str(e)}


def print_monitoring_report(steward_metrics: Dict, intent_metrics: Dict, cluster_metrics: Dict):
    """Print formatted monitoring report"""
    print("=" * 80)
    print("Intent Layer v2 - Metrics Monitoring Report")
    print("=" * 80)
    print()

    print("1. IntentSteward Analysis Metrics")
    print("-" * 80)
    print(f"  Total analyses: {steward_metrics['total_analyses']}")
    print(f"  Executed analyses (Phase 2): {steward_metrics['executed_analyses']}")
    print(f"  Observation analyses (Phase 1): {steward_metrics['observation_analyses']}")
    print(f"  Total operations planned: {steward_metrics['total_operations']}")
    print(f"  Ephemeral tasks: {steward_metrics['ephemeral_tasks']}")
    if steward_metrics['total_analyses'] > 0:
        execution_rate = steward_metrics['executed_analyses'] / steward_metrics['total_analyses'] * 100
        print(f"  Execution rate: {execution_rate:.1f}%")
    print()

    print("2. IntentCard Metrics")
    print("-" * 80)
    if "error" in intent_metrics:
        print(f"  Error: {intent_metrics['error']}")
    else:
        print(f"  Total IntentCards: {intent_metrics['total_intents']}")
        print(f"  Steward-created (last 7 days): {intent_metrics['steward_created']}")
        print(f"  Steward-updated (last 7 days): {intent_metrics['steward_updated']}")
        print(f"  User-created (last 7 days): {intent_metrics['user_created']}")
        print(f"  Auto-update rate: {intent_metrics['auto_update_rate']:.1f}%")
    print()

    print("3. Cluster Quality Metrics")
    print("-" * 80)
    if "error" in cluster_metrics:
        print(f"  Error: {cluster_metrics['error']}")
    else:
        print(f"  Total clusters: {cluster_metrics['total_clusters']}")
        print(f"  Average intents per cluster: {cluster_metrics['avg_intents_per_cluster']:.1f}")
        print(f"  Clusters with labels: {cluster_metrics['clusters_with_labels']}")
        print(f"  Label quality rate: {cluster_metrics['label_quality_rate']:.1f}%")
    print()

    print("=" * 80)
    print(f"Report generated at: {datetime.utcnow().isoformat()}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description='Monitor Intent Layer v2 metrics')
    parser.add_argument('--db-path', type=str, default=None, help='Path to SQLite database')
    parser.add_argument('--log-file', type=str, default='logs/backend.log', help='Path to log file')
    parser.add_argument('--workspace-id', type=str, default=None, help='Filter by workspace ID')
    parser.add_argument('--profile-id', type=str, default='default-user', help='Profile ID')
    parser.add_argument('--days', type=int, default=7, help='Number of days to analyze')

    args = parser.parse_args()

    # Determine paths
    if args.db_path:
        db_path = args.db_path
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        db_path = os.path.join(data_dir, "mindscape.db")
        if not os.path.exists(db_path):
            db_path = '/app/data/mindscape.db'

    log_file = args.log_file
    if not os.path.isabs(log_file):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_file = os.path.join(base_dir, log_file)

    print(f"Analyzing metrics from:")
    print(f"  Database: {db_path}")
    print(f"  Log file: {log_file}")
    print()

    # Parse steward logs
    steward_metrics = parse_steward_logs(log_file, days=args.days)

    # Analyze intent cards
    intent_metrics = analyze_intent_cards(db_path, args.profile_id, days=args.days)

    # Analyze clusters
    cluster_metrics = analyze_clusters(db_path, args.workspace_id, args.profile_id)

    # Print report
    print_monitoring_report(steward_metrics, intent_metrics, cluster_metrics)


if __name__ == '__main__':
    main()


#!/usr/bin/env python3
"""
Intent Steward Analysis Comparison Tool

Compares IntentSteward's planned operations (from logs) with actual IntentCard state.

Phase 1: Observation mode comparison
- Shows what IntentSteward would have created/updated vs actual IntentCards
"""

import argparse
import sys
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.mindscape_store import MindscapeStore
from app.services.stores.intent_logs_store import IntentLogsStore


def load_steward_plans(db_path: str, workspace_id: Optional[str] = None,
                       profile_id: Optional[str] = None,
                       days: int = 7) -> List[Dict[str, Any]]:
    """
    Load IntentSteward plans from intent_logs

    Args:
        db_path: Database path
        workspace_id: Filter by workspace ID
        profile_id: Filter by profile ID
        days: Number of days to look back

    Returns:
        List of steward plans
    """
    try:
        store = MindscapeStore(db_path=db_path)
        intent_logs_store = IntentLogsStore(db_path=db_path)

        # Get logs from last N days
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        all_logs = intent_logs_store.list_intent_logs(
            profile_id=profile_id,
            workspace_id=workspace_id,
            limit=1000
        )

        # Filter by date and steward phase
        steward_logs = []
        for log in all_logs:
            if log.timestamp < cutoff_date:
                continue
            if log.metadata and log.metadata.get("steward_phase") == "phase1_observation":
                steward_logs.append(log)

        # Extract layout plans
        plans = []
        for log in steward_logs:
            if log.final_decision and "layout_plan" in log.final_decision:
                plan_data = log.final_decision["layout_plan"]
                plans.append({
                    "log_id": log.id,
                    "timestamp": log.timestamp.isoformat(),
                    "workspace_id": log.workspace_id,
                    "profile_id": log.profile_id,
                    "turn_id": log.metadata.get("turn_id"),
                    "layout_plan": plan_data
                })

        return plans
    except Exception as e:
        print(f"Error loading steward plans: {e}", file=sys.stderr)
        return []


def get_actual_intent_cards(db_path: str, profile_id: str) -> List[Dict[str, Any]]:
    """
    Get actual IntentCards from database

    Args:
        db_path: Database path
        profile_id: Profile ID

    Returns:
        List of IntentCards
    """
    try:
        store = MindscapeStore(db_path=db_path)
        intents = store.list_intents(profile_id=profile_id)

        return [
            {
                "id": intent.id,
                "title": intent.title,
                "description": intent.description,
                "status": intent.status.value,
                "priority": intent.priority.value,
                "created_at": intent.created_at.isoformat() if intent.created_at else None,
                "updated_at": intent.updated_at.isoformat() if intent.updated_at else None,
                "metadata": intent.metadata or {}
            }
            for intent in intents
        ]
    except Exception as e:
        print(f"Error loading intent cards: {e}", file=sys.stderr)
        return []


def compare_plans_vs_actual(plans: List[Dict], actual_cards: List[Dict]) -> Dict[str, Any]:
    """
    Compare steward plans with actual IntentCards

    Args:
        plans: List of steward plans
        actual_cards: List of actual IntentCards

    Returns:
        Comparison results
    """
    # Collect all planned operations
    planned_creates = []
    planned_updates = []
    planned_ephemeral = []

    for plan_data in plans:
        layout_plan = plan_data.get("layout_plan", {})
        long_term = layout_plan.get("long_term_intents", [])
        ephemeral = layout_plan.get("ephemeral_tasks", [])

        for op in long_term:
            if op.get("operation_type") == "CREATE_INTENT_CARD":
                planned_creates.append({
                    "title": op.get("intent_data", {}).get("title"),
                    "description": op.get("intent_data", {}).get("description"),
                    "priority": op.get("intent_data", {}).get("priority"),
                    "confidence": op.get("confidence"),
                    "reasoning": op.get("reasoning"),
                    "turn_id": plan_data.get("turn_id"),
                    "timestamp": plan_data.get("timestamp")
                })
            elif op.get("operation_type") == "UPDATE_INTENT_CARD":
                planned_updates.append({
                    "intent_id": op.get("intent_id"),
                    "intent_data": op.get("intent_data"),
                    "confidence": op.get("confidence"),
                    "reasoning": op.get("reasoning"),
                    "turn_id": plan_data.get("turn_id"),
                    "timestamp": plan_data.get("timestamp")
                })

        for task in ephemeral:
            planned_ephemeral.append({
                "title": task.get("title"),
                "reasoning": task.get("reasoning"),
                "turn_id": plan_data.get("turn_id"),
                "timestamp": plan_data.get("timestamp")
            })

    # Find matches
    matched_creates = []
    unmatched_creates = []
    matched_updates = []
    unmatched_updates = []

    # Check planned creates
    for planned in planned_creates:
        title = planned["title"]
        matched = False
        for actual in actual_cards:
            if actual["title"].lower().strip() == title.lower().strip():
                matched_creates.append({
                    "planned": planned,
                    "actual": actual
                })
                matched = True
                break
        if not matched:
            unmatched_creates.append(planned)

    # Check planned updates
    for planned in planned_updates:
        intent_id = planned["intent_id"]
        matched = False
        for actual in actual_cards:
            if actual["id"] == intent_id:
                matched_updates.append({
                    "planned": planned,
                    "actual": actual
                })
                matched = True
                break
        if not matched:
            unmatched_updates.append(planned)

    return {
        "summary": {
            "total_plans": len(plans),
            "planned_creates": len(planned_creates),
            "planned_updates": len(planned_updates),
            "planned_ephemeral": len(planned_ephemeral),
            "actual_cards": len(actual_cards),
            "matched_creates": len(matched_creates),
            "unmatched_creates": len(unmatched_creates),
            "matched_updates": len(matched_updates),
            "unmatched_updates": len(unmatched_updates)
        },
        "matched_creates": matched_creates,
        "unmatched_creates": unmatched_creates,
        "matched_updates": matched_updates,
        "unmatched_updates": unmatched_updates,
        "ephemeral_tasks": planned_ephemeral
    }


def print_comparison_report(comparison: Dict[str, Any]):
    """Print formatted comparison report"""
    print("=" * 80)
    print("Intent Steward Analysis Comparison Report")
    print("Phase 1: Observation Mode")
    print("=" * 80)
    print()

    summary = comparison["summary"]
    print("Summary")
    print("-" * 80)
    print(f"  Total steward plans analyzed: {summary['total_plans']}")
    print(f"  Planned CREATE operations: {summary['planned_creates']}")
    print(f"  Planned UPDATE operations: {summary['planned_updates']}")
    print(f"  Planned ephemeral tasks: {summary['planned_ephemeral']}")
    print(f"  Actual IntentCards in database: {summary['actual_cards']}")
    print()
    print(f"  Matched CREATE operations: {summary['matched_creates']}")
    print(f"  Unmatched CREATE operations: {summary['unmatched_creates']}")
    print(f"  Matched UPDATE operations: {summary['matched_updates']}")
    print(f"  Unmatched UPDATE operations: {summary['unmatched_updates']}")
    print()

    if comparison["unmatched_creates"]:
        print("Unmatched CREATE Operations (would have been created)")
        print("-" * 80)
        for i, op in enumerate(comparison["unmatched_creates"], 1):
            print(f"{i}. {op['title']}")
            print(f"   Confidence: {op['confidence']:.2f}")
            print(f"   Reasoning: {op['reasoning']}")
            print(f"   Turn ID: {op['turn_id']}")
            print(f"   Timestamp: {op['timestamp']}")
            print()
    else:
        print("No unmatched CREATE operations")
        print()

    if comparison["ephemeral_tasks"]:
        print("Ephemeral Tasks (logged but not upgraded)")
        print("-" * 80)
        for i, task in enumerate(comparison["ephemeral_tasks"][:10], 1):  # Show first 10
            print(f"{i}. {task['title']}")
            print(f"   Reasoning: {task['reasoning']}")
            print()
        if len(comparison["ephemeral_tasks"]) > 10:
            print(f"  ... and {len(comparison['ephemeral_tasks']) - 10} more")
        print()

    print("=" * 80)
    print(f"Report generated at: {datetime.utcnow().isoformat()}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description='Compare IntentSteward plans with actual IntentCards')
    parser.add_argument('--db-path', type=str, default=None, help='Path to SQLite database')
    parser.add_argument('--workspace-id', type=str, default=None, help='Filter by workspace ID')
    parser.add_argument('--profile-id', type=str, default='default-user', help='Profile ID')
    parser.add_argument('--days', type=int, default=7, help='Number of days to look back')
    parser.add_argument('--json', action='store_true', help='Output as JSON')

    args = parser.parse_args()

    # Determine database path
    if args.db_path:
        db_path = args.db_path
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        db_path = os.path.join(data_dir, "mindscape.db")
        if not os.path.exists(db_path):
            db_path = '/app/data/mindscape.db'

    print(f"Loading steward plans from: {db_path}")
    plans = load_steward_plans(
        db_path=db_path,
        workspace_id=args.workspace_id,
        profile_id=args.profile_id,
        days=args.days
    )

    print(f"Loading actual IntentCards from: {db_path}")
    actual_cards = get_actual_intent_cards(
        db_path=db_path,
        profile_id=args.profile_id
    )

    print(f"Comparing {len(plans)} plans with {len(actual_cards)} actual IntentCards...")
    comparison = compare_plans_vs_actual(plans, actual_cards)

    if args.json:
        print(json.dumps(comparison, indent=2, default=str))
    else:
        print_comparison_report(comparison)


if __name__ == '__main__':
    main()


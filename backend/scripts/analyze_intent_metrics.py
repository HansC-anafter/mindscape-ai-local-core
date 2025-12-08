#!/usr/bin/env python3
"""
Intent Metrics Analysis Script

Analyzes intent-related metrics from logs and database for Phase 0 monitoring.

Usage:
    python scripts/analyze_intent_metrics.py [--db-path <path>] [--log-file <path>]
"""

import argparse
import sys
import os
import re
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.stores.intent_tags_store import IntentTagsStore
from app.services.mindscape_store import MindscapeStore


def parse_log_metrics(log_file: str) -> Dict[str, List[Dict]]:
    """
    Parse INTENT_METRICS entries from log file

    Args:
        log_file: Path to log file

    Returns:
        Dictionary with metric types as keys and lists of metric entries as values
    """
    metrics = defaultdict(list)

    if not os.path.exists(log_file):
        print(f"Warning: Log file {log_file} not found")
        return dict(metrics)

    # Pattern to match INTENT_METRICS log entries
    # Format: INTENT_METRICS: <metric_type>, key1=value1, key2=value2, ...
    pattern = re.compile(r'INTENT_METRICS: ([^,]+), (.+)')

    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            match = pattern.search(line)
            if match:
                metric_type = match.group(1).strip()
                params_str = match.group(2)

                # Parse parameters
                params = {}
                for param in params_str.split(', '):
                    param = param.strip()
                    if '=' in param:
                        key, value = param.split('=', 1)
                        # Try to convert numeric values
                        try:
                            if '.' in value:
                                params[key] = float(value)
                            else:
                                params[key] = int(value)
                        except ValueError:
                            params[key] = value

                metrics[metric_type].append(params)

    return dict(metrics)


def analyze_intent_signals(metrics: Dict[str, List[Dict]]) -> Dict:
    """Analyze intent signal creation metrics"""
    # Look for metrics with turn_id (intent signal creation)
    signals = []
    for metric_type, entries in metrics.items():
        if 'turn_id' in str(entries[0].keys()) if entries else False:
            # Check if this entry has intent_signals_created
            for entry in entries:
                if 'intent_signals_created' in entry:
                    signals.append(entry)

    if not signals:
        return {
            'total_turns': 0,
            'total_signals': 0,
            'avg_signals_per_turn': 0.0
        }

    total_turns = len(signals)
    total_signals = sum(s.get('intent_signals_created', 0) for s in signals)
    avg_signals = total_signals / total_turns if total_turns > 0 else 0.0

    return {
        'total_turns': total_turns,
        'total_signals': total_signals,
        'avg_signals_per_turn': round(avg_signals, 2)
    }


def analyze_intent_cards(metrics: Dict[str, List[Dict]]) -> Dict:
    """Analyze intent card creation metrics"""
    cards = metrics.get('intent_card_created', [])

    if not cards:
        return {
            'total_cards': 0,
            'by_source': {}
        }

    by_source = defaultdict(int)
    for card in cards:
        source = card.get('source', 'unknown')
        by_source[source] += 1

    return {
        'total_cards': len(cards),
        'by_source': dict(by_source)
    }


def analyze_manual_confirmations(metrics: Dict[str, List[Dict]]) -> Dict:
    """Analyze manual confirmation metrics"""
    confirmations = metrics.get('manual_confirmation', [])

    if not confirmations:
        return {
            'total_confirmations': 0,
            'total_intents_added': 0
        }

    total_intents = sum(int(c.get('intents_added', 0)) for c in confirmations)

    return {
        'total_confirmations': len(confirmations),
        'total_intents_added': total_intents
    }


def analyze_candidate_duration(db_path: str, workspace_id: Optional[str] = None,
                               profile_id: Optional[str] = None) -> Dict:
    """Analyze average candidate duration from database"""
    try:
        store = IntentTagsStore(db_path)
        avg_seconds = store.calculate_avg_candidate_duration(
            workspace_id=workspace_id,
            profile_id=profile_id
        )

        if avg_seconds is None:
            return {
                'avg_duration_seconds': None,
                'avg_duration_hours': None,
                'avg_duration_days': None,
                'note': 'No data available'
            }

        avg_hours = avg_seconds / 3600
        avg_days = avg_hours / 24

        return {
            'avg_duration_seconds': round(avg_seconds, 2),
            'avg_duration_hours': round(avg_hours, 2),
            'avg_duration_days': round(avg_days, 2)
        }
    except Exception as e:
        return {
            'error': str(e)
        }


def print_report(metrics: Dict, db_metrics: Dict):
    """Print formatted metrics report"""
    print("=" * 80)
    print("Intent Layer v2 - Phase 0 Metrics Report")
    print("=" * 80)
    print()

    # Intent Signals
    print("1. Intent Signals (per conversation turn)")
    print("-" * 80)
    signal_stats = analyze_intent_signals(metrics)
    print(f"  Total conversation turns: {signal_stats['total_turns']}")
    print(f"  Total intent signals created: {signal_stats['total_signals']}")
    print(f"  Average signals per turn: {signal_stats['avg_signals_per_turn']}")
    print()

    # Intent Cards
    print("2. Intent Cards")
    print("-" * 80)
    card_stats = analyze_intent_cards(metrics)
    print(f"  Total intent cards created: {card_stats['total_cards']}")
    if card_stats['by_source']:
        print("  By source:")
        for source, count in card_stats['by_source'].items():
            print(f"    - {source}: {count}")
    print()

    # Manual Confirmations
    print("3. Manual Confirmations (Add to Mindscape)")
    print("-" * 80)
    conf_stats = analyze_manual_confirmations(metrics)
    print(f"  Total manual confirmations: {conf_stats['total_confirmations']}")
    print(f"  Total intents added via manual confirmation: {conf_stats['total_intents_added']}")
    print()

    # Candidate Duration
    print("4. IntentTag CANDIDATE Status Duration")
    print("-" * 80)
    if 'error' in db_metrics:
        print(f"  Error: {db_metrics['error']}")
    elif 'note' in db_metrics:
        print(f"  {db_metrics['note']}")
    else:
        print(f"  Average duration: {db_metrics['avg_duration_seconds']} seconds")
        print(f"                     {db_metrics['avg_duration_hours']} hours")
        print(f"                     {db_metrics['avg_duration_days']} days")
    print()

    print("=" * 80)
    print(f"Report generated at: {datetime.utcnow().isoformat()}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description='Analyze Intent Layer v2 metrics')
    parser.add_argument('--db-path', type=str,
                       default=None,
                       help='Path to SQLite database file')
    parser.add_argument('--log-file', type=str,
                       default='logs/backend.log',
                       help='Path to log file')
    parser.add_argument('--workspace-id', type=str,
                       default=None,
                       help='Filter by workspace ID')
    parser.add_argument('--profile-id', type=str,
                       default=None,
                       help='Filter by profile ID')

    args = parser.parse_args()

    # Determine database path
    if args.db_path:
        db_path = args.db_path
    else:
        # Try to find default database
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        db_path = os.path.join(data_dir, "mindscape.db")

        if not os.path.exists(db_path):
            # Try Docker path
            db_path = '/app/data/mindscape.db'

    # Parse log metrics
    log_file = args.log_file
    if not os.path.isabs(log_file):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_file = os.path.join(base_dir, log_file)

    print(f"Reading metrics from log file: {log_file}")
    metrics = parse_log_metrics(log_file)

    # Get database metrics
    print(f"Reading metrics from database: {db_path}")
    db_metrics = analyze_candidate_duration(
        db_path=db_path,
        workspace_id=args.workspace_id,
        profile_id=args.profile_id
    )

    # Print report
    print_report(metrics, db_metrics)


if __name__ == '__main__':
    main()


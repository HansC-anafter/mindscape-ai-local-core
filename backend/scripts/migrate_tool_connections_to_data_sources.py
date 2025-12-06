"""
ToolConnection to DataSource Migration Script

This script helps identify and optionally migrate ToolConnections to DataSource abstraction.

Note: This is primarily a reporting/analysis script, as the actual migration
is handled lazily by the DataSourceService (which uses ToolConnection as underlying storage).

The script can:
1. Identify ToolConnections that should be data sources (have data_source_type set)
2. Report on ToolConnections that could be data sources but aren't marked
3. Optionally set data_source_type for connections that should be data sources
"""

import logging
import json
from typing import List, Dict, Any, Optional
import argparse
from pathlib import Path

from backend.app.services.tool_connection_store import ToolConnectionStore
from backend.app.models.tool_connection import ToolConnection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def analyze_tool_connections(
    db_path: str = "data/my_agent_console.db"
) -> Dict[str, Any]:
    """
    Analyze ToolConnections and identify data sources

    Args:
        db_path: Path to database file

    Returns:
        Analysis report
    """
    store = ToolConnectionStore(db_path=db_path)

    # Get all connections
    all_connections = []
    # Note: ToolConnectionStore doesn't have a list_all method,
    # so we'll need to iterate through profiles or use a different approach
    # For now, we'll focus on connections that are already marked as data sources

    # This is a placeholder - actual implementation would need to
    # query all connections from the database
    logger.info("Analyzing ToolConnections...")

    # Common data source types
    data_source_types = [
        "wordpress",
        "notion",
        "google_drive",
        "local_filesystem",
        "github",
        "slack",
        "airtable",
        "google_sheets",
    ]

    report = {
        "total_connections": 0,
        "data_sources": [],
        "potential_data_sources": [],
        "non_data_sources": []
    }

    # Note: This is a simplified analysis
    # In a real implementation, we would:
    # 1. Query all connections from the database
    # 2. Check which ones have data_source_type set
    # 3. Identify which ones should be data sources based on tool_type

    logger.warning(
        "This script is a placeholder. Actual implementation would require "
        "querying all ToolConnections from the database."
    )

    return report


def mark_as_data_source(
    connection_id: str,
    profile_id: str,
    data_source_type: str,
    db_path: str = "data/my_agent_console.db",
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Mark a ToolConnection as a data source

    Args:
        connection_id: Connection ID
        profile_id: Profile ID
        data_source_type: Data source type (e.g., 'wordpress', 'notion')
        db_path: Path to database file
        dry_run: If True, only report what would be changed without actually changing

    Returns:
        Operation result
    """
    store = ToolConnectionStore(db_path=db_path)

    connection = store.get_connection(connection_id, profile_id)
    if not connection:
        return {
            "status": "error",
            "error": f"Connection {connection_id} not found"
        }

    if connection.data_source_type:
        return {
            "status": "already_marked",
            "message": f"Connection {connection_id} is already marked as data source type: {connection.data_source_type}",
            "current_type": connection.data_source_type
        }

    if dry_run:
        return {
            "status": "would_mark",
            "connection_id": connection_id,
            "data_source_type": data_source_type,
            "message": f"Would mark connection {connection_id} as data source type: {data_source_type}"
        }

    # Update connection
    connection.data_source_type = data_source_type
    store.save_connection(connection)

    return {
        "status": "success",
        "connection_id": connection_id,
        "data_source_type": data_source_type,
        "message": f"Marked connection {connection_id} as data source type: {data_source_type}"
    }


def main():
    """Main entry point for migration script"""
    parser = argparse.ArgumentParser(
        description="Analyze and migrate ToolConnections to DataSource abstraction"
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze ToolConnections and generate report"
    )
    parser.add_argument(
        "--mark",
        type=str,
        help="Mark a connection as data source: --mark connection_id:profile_id:data_source_type"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode: report what would be changed without actually changing"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/my_agent_console.db",
        help="Path to database file"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path for analysis report (JSON)"
    )

    args = parser.parse_args()

    if args.analyze:
        logger.info("Analyzing ToolConnections...")
        report = analyze_tool_connections(db_path=args.db_path)

        print("\n" + "=" * 80)
        print("ToolConnection Analysis Report")
        print("=" * 80)
        print(json.dumps(report, indent=2))

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"\nReport saved to: {args.output}")

    elif args.mark:
        parts = args.mark.split(":")
        if len(parts) != 3:
            logger.error("Invalid format. Use: --mark connection_id:profile_id:data_source_type")
            return

        connection_id, profile_id, data_source_type = parts
        result = mark_as_data_source(
            connection_id=connection_id,
            profile_id=profile_id,
            data_source_type=data_source_type,
            db_path=args.db_path,
            dry_run=args.dry_run
        )

        print("\n" + "=" * 80)
        print("Mark Data Source Result")
        print("=" * 80)
        print(json.dumps(result, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()


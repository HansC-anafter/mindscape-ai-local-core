#!/usr/bin/env python3
"""
Analyze projects in database to verify categorization and listing
"""

import sqlite3
import json
import sys
from pathlib import Path
from collections import Counter
from datetime import datetime

# Find database file
workspace_root = Path(__file__).parent.parent
db_paths = [
    workspace_root / "backend" / "data" / "mindscape.db",
    workspace_root / "data" / "mindscape.db",
]

db_path = None
for path in db_paths:
    if path.exists():
        db_path = path
        break

if not db_path:
    print("❌ Database file not found")
    sys.exit(1)

print(f"📊 Analyzing projects from: {db_path}\n")

try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all projects
    cursor.execute('''
        SELECT
            id,
            type,
            title,
            home_workspace_id,
            flow_id,
            state,
            created_at,
            updated_at,
            metadata
        FROM projects
        ORDER BY updated_at DESC
    ''')

    projects = cursor.fetchall()

    print(f"📋 Total projects: {len(projects)}\n")

    if len(projects) == 0:
        print("⚠️  No projects found in database")
        sys.exit(0)

    # Group by workspace
    projects_by_workspace = {}
    for project in projects:
        workspace_id = project['home_workspace_id']
        if workspace_id not in projects_by_workspace:
            projects_by_workspace[workspace_id] = []
        projects_by_workspace[workspace_id].append(project)

    print(f"📁 Projects by workspace:\n")
    for workspace_id, ws_projects in projects_by_workspace.items():
        print(f"  Workspace: {workspace_id}")
        print(f"    Projects: {len(ws_projects)}\n")

        # Group by type
        type_counts = Counter(p['type'] for p in ws_projects)
        print(f"  📊 Project types:")
        for ptype, count in sorted(type_counts.items()):
            print(f"    - {ptype}: {count}")
        print()

        # Show all projects
        print(f"  📝 All projects:")
        for project in ws_projects:
            metadata = json.loads(project['metadata']) if project['metadata'] else {}
            created_from = metadata.get('created_from', 'unknown')
            print(f"    - ID: {project['id']}")
            print(f"      Title: {project['title']}")
            print(f"      Type: {project['type']}")
            print(f"      State: {project['state']}")
            print(f"      Flow ID: {project['flow_id'] or '❌ None'}")
            print(f"      Created: {project['created_at']}")
            print(f"      Created from: {created_from}")
            print()

    # Check for duplicate titles
    title_counts = Counter(p['title'] for p in projects)
    duplicates = {title: count for title, count in title_counts.items() if count > 1}
    if duplicates:
        print(f"⚠️  Duplicate project titles found:")
        for title, count in duplicates.items():
            print(f"    - '{title}': {count} projects")
            # Show details
            for project in projects:
                if project['title'] == title:
                    print(f"        ID: {project['id']}, Type: {project['type']}, State: {project['state']}")
        print()

    # Check for projects without flow_id
    no_flow = [p for p in projects if not p['flow_id']]
    if no_flow:
        print(f"⚠️  Projects without flow_id: {len(no_flow)}")
        for project in no_flow:
            print(f"    - {project['id']}: {project['title']} (type: {project['type']})")
        print()

    # Check workspace primary_project_id
    cursor.execute('''
        SELECT
            id,
            title,
            primary_project_id
        FROM workspaces
        WHERE primary_project_id IS NOT NULL
    ''')
    workspaces_with_project = cursor.fetchall()

    if workspaces_with_project:
        print(f"📌 Workspaces with primary_project_id:")
        for workspace in workspaces_with_project:
            print(f"    Workspace: {workspace['id']} ({workspace['title']})")
            print(f"      primary_project_id: {workspace['primary_project_id']}")
            # Check if project exists
            cursor.execute('SELECT id, title, type FROM projects WHERE id = ?', (workspace['primary_project_id'],))
            project = cursor.fetchone()
            if project:
                print(f"      ✅ Project exists: {project['title']} (type: {project['type']})")
            else:
                print(f"      ❌ Project NOT FOUND in database!")
            print()

    conn.close()

except Exception as e:
    print(f"❌ Error analyzing projects: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


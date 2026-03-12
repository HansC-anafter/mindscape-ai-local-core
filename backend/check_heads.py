import os
import sys
from alembic.config import Config
from alembic.script import ScriptDirectory

def main():
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    print("All revisions:")
    for rev in script.walk_revisions():
        print(f"Revision: {rev.revision}, Down rev: {rev.down_revision}, Branch: {rev.branch_labels}")
    
    print("\nHeads:")
    for head in script.get_heads():
        print(head)

if __name__ == "__main__":
    main()

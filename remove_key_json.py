#!/usr/bin/env python3
"""
TINY-HUB — Remove key.json credential lines from all Python files.

Run this from your project root on the VM:
    python3 remove_key_json.py

What it does:
  - Finds every .py file that references key.json
  - Removes the os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "key.json" line
  - Removes any now-redundant `import os` if os is no longer used elsewhere
  - Prints a diff-style summary of every change made

GCP client libraries automatically use Application Default Credentials (ADC)
on Compute Engine — no environment variable needed.
"""

import os
import re
import sys
from pathlib import Path

# The exact line to remove (handles minor whitespace variants)
KEY_JSON_PATTERN = re.compile(
    r'^\s*os\.environ\s*\[\s*["\']GOOGLE_APPLICATION_CREDENTIALS["\']\s*\]\s*=\s*["\']key\.json["\']\s*\n',
    re.MULTILINE
)

def os_still_used(source: str) -> bool:
    """Return True if `os` is still referenced after stripping the credential line."""
    # Remove import line and the credential line, then check for remaining os. usage
    stripped = re.sub(r'^\s*import os\s*\n', '', source, flags=re.MULTILINE)
    stripped = KEY_JSON_PATTERN.sub('', stripped)
    return bool(re.search(r'\bos\.', stripped))

def process_file(path: Path, dry_run: bool = False) -> bool:
    original = path.read_text(encoding='utf-8')

    if 'key.json' not in original:
        return False

    modified = KEY_JSON_PATTERN.sub('', original)

    # If os is no longer used anywhere else, also remove `import os`
    if not os_still_used(modified):
        modified = re.sub(r'^\s*import os\s*\n', '', modified, flags=re.MULTILINE)
        os_removed = True
    else:
        os_removed = False

    if modified == original:
        print(f"  ⚠️  {path.name}: 'key.json' found but no matching line to remove — check manually")
        return False

    print(f"  ✅  {path.name}")
    print(f"        - Removed: os.environ[\"GOOGLE_APPLICATION_CREDENTIALS\"] = \"key.json\"")
    if os_removed:
        print(f"        - Removed: import os  (no longer used)")

    if not dry_run:
        path.write_text(modified, encoding='utf-8')

    return True

def main():
    dry_run = '--dry-run' in sys.argv
    root = Path('.')

    if dry_run:
        print("\n  [DRY RUN — no files will be modified]\n")

    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║  TINY-HUB — Strip key.json credentials from source      ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()

    py_files = sorted(root.rglob('*.py'))
    # Skip node_modules, venv, __pycache__
    py_files = [
        f for f in py_files
        if not any(skip in f.parts for skip in ('node_modules', 'venv', '__pycache__', '.git'))
    ]

    changed = 0
    for f in py_files:
        if process_file(f, dry_run=dry_run):
            changed += 1

    print()
    if changed == 0:
        print("  Nothing to change — no key.json credential lines found.")
    else:
        verb = "Would modify" if dry_run else "Modified"
        print(f"  {verb} {changed} file(s).")
        if dry_run:
            print("  Run without --dry-run to apply changes.")

    print()
    print("  Next: delete key.json from disk and invalidate the old GCP key.")
    print("  See setup_workload_identity.sh for those steps.")
    print()

if __name__ == '__main__':
    main()

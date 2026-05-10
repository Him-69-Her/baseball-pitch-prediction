#!/usr/bin/env python3
"""Prepend gevent.monkey.patch_all() to app.py as the first executable code."""
from pathlib import Path

p = Path("app.py")
src = p.read_text()

marker = "from gevent import monkey"
if marker in src:
    print("[SKIP] app.py already has gevent.monkey import")
else:
    # Preserve shebang / encoding line / module docstring
    lines = src.splitlines(keepends=True)
    insert_at = 0
    # Skip shebang
    if lines and lines[0].startswith("#!"):
        insert_at = 1
    # Skip encoding declaration
    if insert_at < len(lines) and "coding" in lines[insert_at] and lines[insert_at].startswith("#"):
        insert_at += 1
    # Skip module docstring (triple-quoted)
    if insert_at < len(lines):
        stripped = lines[insert_at].lstrip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = stripped[:3]
            # Single-line docstring
            if stripped.count(quote) >= 2 and len(stripped) > 3:
                insert_at += 1
            else:
                # Multi-line docstring — find closing
                insert_at += 1
                while insert_at < len(lines) and quote not in lines[insert_at]:
                    insert_at += 1
                if insert_at < len(lines):
                    insert_at += 1  # past the closing line

    patch = "from gevent import monkey\nmonkey.patch_all()\n\n"
    lines.insert(insert_at, patch)
    p.write_text("".join(lines))
    print(f"[OK] Inserted gevent monkey patch at line {insert_at + 1} of app.py")

# Show the first 10 lines for verification
print("\n--- app.py (first 10 lines) ---")
for i, line in enumerate(Path("app.py").read_text().splitlines()[:10], 1):
    print(f"{i:3d}  {line}")

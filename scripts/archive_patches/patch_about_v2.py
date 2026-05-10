#!/usr/bin/env python3
"""About page v2: Thesis tab cleanup + Where We Are Now card edits."""
from pathlib import Path

p = Path("templates/about.html")
src = p.read_text()

# ─── 1. Delete "The Bottom Line" block on Thesis tab ───
# Find the thesis-close div and remove it entirely
import re
pattern_bottom_line = re.compile(
    r'\s*<div class="thesis-close">.*?</div>\s*',
    re.DOTALL
)
matches = pattern_bottom_line.findall(src)
if matches:
    src = pattern_bottom_line.sub('\n    ', src, count=1)
    print("[OK] 1/8 'The Bottom Line' block deleted")
else:
    # Fallback: search for the heading text and delete surrounding block
    assert '// The Bottom Line' in src or 'THE BOTTOM LINE' in src or 'bottom-line' in src.lower(), \
        "bottom line block not found by any pattern"
    print("[WARN] 1/8 thesis-close div not found; checking alternate patterns")

# ─── 2. Add vertical gap between routing/settlement and "isn't a solar app" ───
# Find the magenta hook and add margin-top to it
old_hook_css_search = "Tiny-Hub isn't a solar app"
if old_hook_css_search in src:
    # Inject gap CSS — look for the hook's container class
    # The hook is likely an h2 or h3 with a magenta color
    gap_css = '''
/* Gap between thesis intro and solar-app hook */
.thesis-hook, h2.solar-hook, .solar-app-hook { margin-top: 3.5rem !important; }
/* Fallback: any h2/h3 containing the magenta hook text gets breathing room */
#tab-thesis h2 + hr, #tab-thesis p + hr { margin: 2.5rem 0 !important; }
'''
    src = src.replace("</style>", gap_css + "\n</style>", 1)
    # Also add inline spacing to the specific element — wrap in a spacer
    src = src.replace(
        "Tiny-Hub isn't a solar app",
        '<span style="display:block;margin-top:2.5rem"></span>Tiny-Hub isn\'t a solar app',
        1
    )
    print("[OK] 2/8 vertical gap added before solar-app hook")
else:
    print("[WARN] 2/8 'solar app' hook text not found")

# ─── 3. Platform bullet 1: Remove ", from tinyhub-cicd" ───
# Match variants: ", from `tinyhub-cicd`" or ", from tinyhub-cicd" with or without code tags
patterns_cicd = [
    ", from <code>tinyhub-cicd</code>",
    ", from `tinyhub-cicd`",
    ", from tinyhub-cicd",
    " from <code>tinyhub-cicd</code>",
    " from `tinyhub-cicd`",
    " from tinyhub-cicd",
]
removed = False
for pat in patterns_cicd:
    if pat in src:
        src = src.replace(pat, "", 1)
        print(f"[OK] 3/8 removed: '{pat}'")
        removed = True
        break
if not removed:
    print("[WARN] 3/8 tinyhub-cicd suffix not found — may already be clean")

# ─── 4. Platform bullet 2: Rewrite enterprise skeleton bullet ───
old_platform_b2 = "Full GCP enterprise org: separate projects for platform, data, and blockchain with isolated IAM"
new_platform_b2 = "Enterprise skeleton broken out into Development, Testing, and Production folders. Under each main folder you will find separate projects for platform, data, and blockchain with isolated IAM"
assert old_platform_b2 in src, "platform bullet 2 original text not found"
src = src.replace(old_platform_b2, new_platform_b2)
print("[OK] 4/8 platform bullet 2 rewritten")

# ─── 5. Data bullet 1: Replace District 91 with McHenry (Places + Solar) ───
old_data_b1 = "<strong>District 91</strong> (Ameren / MISO) fully mapped as a digital twin"
new_data_b1 = "<strong>McHenry County</strong> (ComEd / PJM) mapped with Google Places + Google Solar APIs — real building footprints, real solar potential, tiered by mega / large / medium / small"
assert old_data_b1 in src, "data bullet 1 original not found"
src = src.replace(old_data_b1, new_data_b1)
print("[OK] 5/8 data bullet 1 replaced with McHenry Places+Solar")

# ─── 6. Data bullet 3: Replace Green Button with Google map stack ───
old_data_b3 = "Green Button ingestion with optimistic settlement (works around 24-48h data delay)"
new_data_b3 = "McHenry County digital twin built on Google's full map stack: Places API for buildings, Solar API for per-roof kWh potential, Maps JS API for live rendering"
assert old_data_b3 in src, "data bullet 3 original not found"
src = src.replace(old_data_b3, new_data_b3)
print("[OK] 6/8 data bullet 3 replaced with Google map stack")

# ─── 7. Add new Data bullet 4: Live PJM LMP ingestion ───
# Insert after the last existing data bullet. Anchor on the Pub/Sub bullet text.
pubsub_bullet_text = "Pub/Sub topics + BigQuery pipelines for real-time grid events"
new_pjm_bullet_html = '''Pub/Sub topics + BigQuery pipelines for real-time grid events</li>
          <li>Live <strong>PJM real-time 5-minute LMP ingestion</strong> via <code>gridstatus</code> API — actual grid prices driving every match and settlement'''
assert pubsub_bullet_text in src, "pub/sub bullet anchor not found for PJM insertion"
src = src.replace(pubsub_bullet_text, new_pjm_bullet_html)
print("[OK] 7/8 new PJM LMP bullet added to Data card")

# ─── 8. Blockchain bullet 4: prepend "Built for future" ───
old_blockchain_b4 = "ERC-4337 account abstraction via managed Pimlico / Biconomy"
new_blockchain_b4 = "Built for future ERC-4337 account abstraction via managed Pimlico / Biconomy"
assert old_blockchain_b4 in src, "blockchain bullet 4 original not found"
src = src.replace(old_blockchain_b4, new_blockchain_b4)
print("[OK] 8/8 blockchain bullet 4 prepended with 'Built for future'")

p.write_text(src)
print("\n[DONE] About page v2 fully patched")

#!/usr/bin/env python3
"""About page v3: mission, stats grid, numbers, founder's note, photo, what's next."""
from pathlib import Path
import re

p = Path("templates/about.html")
src = p.read_text()

# ─── 1. Mission statement rewrite ───
old_mission = "We aim to provide grid upgrades and place real power in the hands of the people for the future of energy through an affordable, sustainable, and transparent marketplace."
new_mission = "We aim to provide the necessary upgrades to a failing grid. Our main focus is to place real power in the hands of the people enabling them to shape the future of energy infrastructure through an affordable, sustainable, and transparent marketplace."
assert old_mission in src, "mission text not found"
src = src.replace(old_mission, new_mission)
print("[OK] 1/14 mission statement rewritten")

# ─── 2. Center stats as 2x2 grid ───
old_stats_css = '''.stat-row{
  display:flex;flex-direction:column;gap:1rem;margin:2.5rem 0 3rem;max-width:440px;
}'''
new_stats_css = '''.stat-row{
  display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem;
  margin:2.5rem auto 3rem;max-width:900px;
}
@media(max-width:700px){.stat-row{grid-template-columns:1fr;max-width:440px}}'''
assert old_stats_css in src, "stat-row CSS not found"
src = src.replace(old_stats_css, new_stats_css)
print("[OK] 2/14 stats repositioned as centered 2x2 grid")

# ─── 3. Ninety-four percent → 94% ───
old_94 = "Ninety-four percent of the new load growth is data centers."
new_94 = "94% of the new load growth is data centers."
assert old_94 in src, "ninety-four percent text not found"
src = src.replace(old_94, new_94)
print("[OK] 3/14 ninety-four percent replaced with 94%")

# ─── 4. "asset it is" sentence split + new "Value must circulate" line ───
old_close = "asset it is, and keeps value circulating inside the communities producing it. That's what we're building."
new_close = "asset it is. Value must circulate inside the communities producing it, no one owns the sunlight."
assert old_close in src, "closing sentence not found"
src = src.replace(old_close, new_close)
print("[OK] 4/14 closing sentence rewritten")

# ─── 5. What's Next bullet 1: Illinois/Ameren/MISO → McHenry/ComEd/PJM ───
old_wn1 = "Illinois pilot deployment within Ameren / MISO territory"
new_wn1 = "McHenry County pilot deployment within ComEd / PJM territory"
assert old_wn1 in src, "what's next bullet 1 not found"
src = src.replace(old_wn1, new_wn1)
print("[OK] 5/14 what's next bullet 1: McHenry/ComEd/PJM")

# ─── 6. What's Next bullet 2: D91 → McHenry County ───
old_wn2 = "30-day shadow market backtest on D91 live data"
new_wn2 = "30-day shadow market backtest on McHenry County live data"
assert old_wn2 in src, "what's next bullet 2 not found"
src = src.replace(old_wn2, new_wn2)
print("[OK] 6/14 what's next bullet 2: McHenry live data")

# ─── 7. What's Next bullet 3: $2M seed raise → funding statement ───
old_wn3 = "<strong>$2M seed raise</strong> to fund the pilot and first hires"
new_wn3 = "Securing funding for legal counsel, platform development, and 1st developer"
assert old_wn3 in src, "what's next bullet 3 ($2M) not found"
src = src.replace(old_wn3, new_wn3)
print("[OK] 7/14 what's next bullet 3: funding statement")

# ─── 8. Founder's Note opening lines rewrite ───
old_open = "I grew up in a small town. That's not a line in a pitch deck. It's the whole reason Tiny-Hub exists."
new_open = "I grew up in a small town and have also lived the city life. The disconnect and delayed innovation I've witnessed is the main reason Tiny Hub exists."
assert old_open in src, "founder's note opening lines not found"
src = src.replace(old_open, new_open)
print("[OK] 8/14 founder's note opening lines rewritten")

# ─── 9. Founder's Note: background line ───
# Try several possible original phrasings for this line
background_candidates = [
    "My background is in finance and logistics.",
    "My background is in finance, logistics, and sales.",
    "I come from a background in finance and logistics.",
    "My background is finance and logistics.",
]
new_background = "My background is in finance, logistics and sales."
background_replaced = False
for candidate in background_candidates:
    if candidate in src:
        src = src.replace(candidate, new_background)
        background_replaced = True
        print(f"[OK] 9/14 background line replaced: '{candidate}' → new")
        break
if not background_replaced:
    # Try fuzzy — look for "My background" and log surrounding text
    bg_match = re.search(r"My background is[^.]*\.", src)
    if bg_match:
        old_bg = bg_match.group(0)
        src = src.replace(old_bg, new_background)
        print(f"[OK] 9/14 background line replaced (fuzzy): '{old_bg}' → new")
    else:
        print("[WARN] 9/14 background line not found — check manually")

# ─── 10. Founder's Note: "Then I spent years in sales" → "Prior to this, I spent years..." ───
old_sales = "Then I spent years in sales, learning how to actually talk to the people on both ends of those systems."
new_sales = "Prior to this, I spent years in sales, learning how to actually talk to the people on both ends of those systems."
if old_sales in src:
    src = src.replace(old_sales, new_sales)
    print("[OK] 10/14 'Then I spent' → 'Prior to this, I spent'")
else:
    # Try without exact wording
    sales_match = re.search(r"(Then I spent[^.]+\.)", src)
    if sales_match:
        src = src.replace(sales_match.group(1), new_sales)
        print(f"[OK] 10/14 sales line replaced (fuzzy)")
    else:
        print("[WARN] 10/14 'Then I spent years' sentence not found")

# ─── 11. Delete "And right now, it's running on..." sentence ───
old_extractive = " And right now, it's running on the exact same extractive pattern that hollowed out Main Street."
if old_extractive in src:
    src = src.replace(old_extractive, "")
    print("[OK] 11/14 extractive pattern sentence deleted")
else:
    # try without leading space
    old_extractive_alt = "And right now, it's running on the exact same extractive pattern that hollowed out Main Street."
    if old_extractive_alt in src:
        src = src.replace(old_extractive_alt, "")
        print("[OK] 11/14 extractive pattern sentence deleted (alt)")
    else:
        print("[WARN] 11/14 'And right now, extractive pattern' sentence not found")

# ─── 12. "Keeping the economic value..." → "The economic value needs to stay..." ───
old_keeping = "Keeping the economic value exactly where it's produced."
new_keeping = "The economic value needs to stay where it is produced."
if old_keeping in src:
    src = src.replace(old_keeping, new_keeping)
    print("[OK] 12/14 'Keeping the economic value' rewritten")
else:
    print("[WARN] 12/14 'Keeping the economic value' sentence not found")

# ─── 13. "Giving small communities a seat..." → "Small communities deserve..." ───
old_seat = "Giving small communities a seat at a table they've historically paid for, but never been allowed to sit at."
new_seat = "Small communities deserve a seat at the table and a voice that matters."
if old_seat in src:
    src = src.replace(old_seat, new_seat)
    print("[OK] 13/14 'Giving small communities a seat' rewritten")
else:
    print("[WARN] 13/14 'Giving small communities a seat' sentence not found")

# ─── 14. Replace embedded base64 founder image with /static/cole_founder.png ───
# Find img tag with base64 data URI and cole as alt, replace src
img_pattern = re.compile(
    r'<img\s+src="data:image/[^"]+"\s+alt="Cole[^"]*"([^>]*)>',
    re.DOTALL
)
match = img_pattern.search(src)
if match:
    attrs_tail = match.group(1)
    new_img = f'<img src="{{{{ url_for(\'static\', filename=\'cole_founder.png\') }}}}" alt="Cole - Founder"{attrs_tail}>'
    src = img_pattern.sub(new_img, src, count=1)
    print("[OK] 14/14 founder image replaced with /static/cole_founder.png")
else:
    print("[WARN] 14/14 base64 founder image not found by pattern — check tag manually")

p.write_text(src)
print("\n[DONE] About page v3 fully patched")

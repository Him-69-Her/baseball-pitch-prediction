#!/usr/bin/env python3
"""About page v3b: resume from edit 4 onward (1-3 already applied)."""
from pathlib import Path
import re

p = Path("templates/about.html")
src = p.read_text()

# ─── 4. Closing sentence rewrite ───
old_close = "treats local generation as the asset it is, and keeps value circulating inside the communities producing it. <strong>That's what we're building.</strong>"
new_close = "treats local generation as the asset it is. <strong>Value must circulate inside the communities producing it, no one owns the sunlight.</strong>"
assert old_close in src, "closing sentence not found"
src = src.replace(old_close, new_close)
print("[OK] 4/14 closing sentence rewritten")

# ─── 5. What's Next bullet 1 ───
old_wn1 = "Illinois pilot deployment within Ameren / MISO territory"
new_wn1 = "McHenry County pilot deployment within ComEd / PJM territory"
assert old_wn1 in src, "what's next bullet 1 not found"
src = src.replace(old_wn1, new_wn1)
print("[OK] 5/14 what's next bullet 1: McHenry/ComEd/PJM")

# ─── 6. What's Next bullet 2 ───
old_wn2 = "30-day shadow market backtest on D91 live data"
new_wn2 = "30-day shadow market backtest on McHenry County live data"
assert old_wn2 in src, "what's next bullet 2 not found"
src = src.replace(old_wn2, new_wn2)
print("[OK] 6/14 what's next bullet 2: McHenry live data")

# ─── 7. What's Next bullet 3: $2M → funding statement ───
old_wn3 = "<strong>$2M seed raise</strong> to fund the pilot and first hires"
new_wn3 = "Securing funding for legal counsel, platform development, and 1st developer"
assert old_wn3 in src, "what's next bullet 3 ($2M) not found"
src = src.replace(old_wn3, new_wn3)
print("[OK] 7/14 what's next bullet 3: funding statement")

# ─── 8. Founder's Note opening lines ───
old_open = "I grew up in a small town. That's not a line in a pitch deck. It's the whole reason Tiny-Hub exists."
new_open = "I grew up in a small town and have also lived the city life. The disconnect and delayed innovation I've witnessed is the main reason Tiny Hub exists."
assert old_open in src, "founder's note opening lines not found"
src = src.replace(old_open, new_open)
print("[OK] 8/14 founder's note opening lines rewritten")

# ─── 9. Founder's Note: background line ───
bg_candidates = [
    "My background is in finance and logistics.",
    "My background is in finance, logistics, and sales.",
    "I come from a background in finance and logistics.",
    "My background is finance and logistics.",
]
new_background = "My background is in finance, logistics and sales."
bg_done = False
for cand in bg_candidates:
    if cand in src:
        src = src.replace(cand, new_background)
        bg_done = True
        print(f"[OK] 9/14 background line: '{cand}' → new")
        break
if not bg_done:
    m = re.search(r"My background is[^.]*\.", src)
    if m:
        old_bg = m.group(0)
        src = src.replace(old_bg, new_background)
        print(f"[OK] 9/14 background line (fuzzy): '{old_bg}' → new")
    else:
        print("[WARN] 9/14 background line not found")

# ─── 10. "Then I spent years in sales..." → "Prior to this, I spent..." ───
old_sales = "Then I spent years in sales, learning how to actually talk to the people on both ends of those systems."
new_sales = "Prior to this, I spent years in sales, learning how to actually talk to the people on both ends of those systems."
if old_sales in src:
    src = src.replace(old_sales, new_sales)
    print("[OK] 10/14 'Then I spent' → 'Prior to this, I spent'")
else:
    m = re.search(r"(Then I spent[^.]+\.)", src)
    if m:
        src = src.replace(m.group(1), new_sales)
        print("[OK] 10/14 sales line replaced (fuzzy)")
    else:
        print("[WARN] 10/14 'Then I spent years' sentence not found")

# ─── 11. Delete "And right now, it's running on the exact same extractive pattern..." ───
for variant in [
    " And right now, it's running on the exact same extractive pattern that hollowed out Main Street.",
    "And right now, it's running on the exact same extractive pattern that hollowed out Main Street.",
    " And right now, it&#39;s running on the exact same extractive pattern that hollowed out Main Street.",
]:
    if variant in src:
        src = src.replace(variant, "")
        print(f"[OK] 11/14 extractive pattern sentence deleted")
        break
else:
    m = re.search(r"\s*And right now[^.]+extractive[^.]+\.", src)
    if m:
        src = src.replace(m.group(0), "")
        print("[OK] 11/14 extractive sentence deleted (fuzzy)")
    else:
        print("[WARN] 11/14 extractive sentence not found")

# ─── 12. "Keeping the economic value..." → "The economic value needs to stay..." ───
old_keeping = "Keeping the economic value exactly where it's produced."
new_keeping = "The economic value needs to stay where it is produced."
if old_keeping in src:
    src = src.replace(old_keeping, new_keeping)
    print("[OK] 12/14 'Keeping the economic value' rewritten")
else:
    m = re.search(r"Keeping the economic value[^.]*\.", src)
    if m:
        src = src.replace(m.group(0), new_keeping)
        print("[OK] 12/14 'Keeping the economic value' (fuzzy)")
    else:
        print("[WARN] 12/14 'Keeping the economic value' not found")

# ─── 13. "Giving small communities a seat..." → "Small communities deserve..." ───
old_seat = "Giving small communities a seat at a table they've historically paid for, but never been allowed to sit at."
new_seat = "Small communities deserve a seat at the table and a voice that matters."
if old_seat in src:
    src = src.replace(old_seat, new_seat)
    print("[OK] 13/14 'Giving small communities' rewritten")
else:
    m = re.search(r"Giving small communities a seat[^.]*\.", src)
    if m:
        src = src.replace(m.group(0), new_seat)
        print("[OK] 13/14 'Giving small communities' (fuzzy)")
    else:
        print("[WARN] 13/14 'Giving small communities' not found")

# ─── 14. Replace base64 founder image with /static/cole_founder.png ───
img_pattern = re.compile(
    r'<img\s+src="data:image/[^"]+"\s+alt="Cole[^"]*"([^>]*)>',
    re.DOTALL
)
m = img_pattern.search(src)
if m:
    attrs_tail = m.group(1)
    new_img = f'<img src="{{{{ url_for(\'static\', filename=\'cole_founder.png\') }}}}" alt="Cole - Founder"{attrs_tail}>'
    src = img_pattern.sub(new_img, src, count=1)
    print("[OK] 14/14 founder image → /static/cole_founder.png")
else:
    print("[WARN] 14/14 base64 founder image not found by pattern")

p.write_text(src)
print("\n[DONE] About page v3b patched")

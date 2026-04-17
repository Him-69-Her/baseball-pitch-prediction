#!/usr/bin/env python3
"""
1. Fix Connect Pub/Sub button to push trades to BOTH map feed and live feeds tab
2. Add SQL write path to shadow_simulator.py
"""
from pathlib import Path

# ================================================================
# 1. FIX DASHBOARD
# ================================================================
dash = Path("templates/dashboard.html")
src = dash.read_text()
orig = src

# Find the push function - search for the unique pattern
old = "var feed=document.getElementById('d91-map-feed');"
assert old in src, "d91-map-feed reference not found"

# Replace single feed push with dual feed push
new = "['d91-map-feed','d91-feed'].forEach(function(fid){ var feed=document.getElementById(fid);"

src = src.replace(old, new)

# Find the closing of the feed block and add the forEach closing
old_close = "feed.prepend(d);if(feed.children.length>50)feed.removeChild(feed.lastChild);"
new_close = "feed.prepend(d);if(feed.children.length>50)feed.removeChild(feed.lastChild);}});"

# Only replace the one inside connectPubSub (there might be others)
# Find it by context - it's near d91-map-feed
idx = src.find("['d91-map-feed','d91-feed']")
if idx > 0:
    close_idx = src.find(old_close, idx)
    if close_idx > 0:
        src = src[:close_idx] + new_close + src[close_idx + len(old_close):]

# Add live feeds tab stat updates after the existing stat updates
old_stats_end = "if(c)c.textContent=(parseFloat(c.textContent||0)+t.co2_tons).toFixed(2)+' t';"
# Find the one inside connectPubSub
idx2 = src.find("['d91-map-feed','d91-feed']")
if idx2 > 0:
    stats_idx = src.find(old_stats_end, idx2)
    if stats_idx > 0:
        feed_stats = old_stats_end + """
            var fs=document.getElementById('f-d91-settled');if(fs)fs.textContent=parseInt(fs.textContent||0)+1;
            var fm=document.getElementById('f-d91-mwh');if(fm)fm.textContent=(parseFloat(fm.textContent||0)+t.mwh*1000).toFixed(0);
            var fp=document.getElementById('f-d91-profit');if(fp)fp.textContent='$'+(parseFloat((fp.textContent||'$0').replace('$',''))+t.net_profit).toFixed(2);"""
        src = src[:stats_idx] + feed_stats + src[stats_idx + len(old_stats_end):]

assert src != orig, "No changes to dashboard"
dash.write_text(src)
print("[OK] dashboard.html - trades now push to both feeds + live stats")

# ================================================================
# 2. ADD SQL WRITES TO SHADOW SIMULATOR
# ================================================================
sim = Path("shadow_simulator.py")
s = sim.read_text()
s_orig = s

# Add SQL imports after pubsub import
sql_code = '''

# SQL persistence (optional - skips gracefully if unavailable)
DB_HOST = os.environ.get("DB_HOST", "")
DB_USER = os.environ.get("DB_USER", "tinyhub_app")
DB_PASS = os.environ.get("DB_PASS", "TinyHub2026Dev")
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_PORT = os.environ.get("DB_PORT", "5432")
_db_conn = None

def get_db():
    global _db_conn
    if not DB_HOST:
        return None
    try:
        if _db_conn is None or _db_conn.closed:
            import psycopg2
            _db_conn = psycopg2.connect(
                host=DB_HOST, port=DB_PORT,
                user=DB_USER, password=DB_PASS, dbname=DB_NAME
            )
            _db_conn.autocommit = True
            print(f"  DB connected: {DB_HOST}")
        return _db_conn
    except Exception as e:
        print(f"  DB connection failed: {e}")
        return None

def write_trades_to_db(trades):
    conn = get_db()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        count = 0
        for t in trades:
            try:
                cur.execute(
                    "INSERT INTO trades (trade_id, timestamp, district, seller_id, seller_label, seller_town,"
                    " seller_lat, seller_lng, buyer_id, buyer_label, buyer_town, buyer_lat, buyer_lng,"
                    " mwh, effective_mwh, distance_km, line_loss_pct, price_per_kwh,"
                    " gross_revenue, toll_cost, net_profit, co2_tons, trade_status,"
                    " settlement, matching_mode, dni_wm2, source)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                    " ON CONFLICT (trade_id) DO NOTHING",
                    (
                        t['trade_id'], t['timestamp'], t.get('district', 'D91'),
                        t.get('seller_id'), t.get('seller_label'), t.get('seller_town'),
                        t.get('seller_lat'), t.get('seller_lng'),
                        t.get('buyer_id'), t.get('buyer_label'), t.get('buyer_town'),
                        t.get('buyer_lat'), t.get('buyer_lng'),
                        t['mwh'], t.get('effective_mwh'), t.get('distance_km'),
                        t.get('line_loss_pct'), t.get('price_per_kwh'),
                        t.get('gross_revenue'), t.get('toll_cost'), t.get('net_profit'),
                        t.get('co2_tons'), t.get('trade_status'),
                        t.get('settlement'), t.get('matching_mode'),
                        t.get('dni_wm2'), t.get('source')
                    )
                )
                count += 1
            except Exception as e:
                print(f"  DB insert error: {e}")
        print(f"  DB: {count} trades written")
        return count
    except Exception as e:
        print(f"  DB write error: {e}")
        return 0
'''

# Insert after the pubsub import line
s = s.replace(
    "from google.cloud import pubsub_v1\n",
    "from google.cloud import pubsub_v1\n" + sql_code
)

# Add SQL write call before the summary print
s = s.replace(
    '    total_mwh = sum(t["mwh"] for t in trades)',
    '    # Write to SQL if configured\n    write_trades_to_db(trades)\n\n    total_mwh = sum(t["mwh"] for t in trades)'
)

assert s != s_orig, "No changes to simulator"
sim.write_text(s)
print("[OK] shadow_simulator.py - SQL write path added (env-var driven)")
print("     Set DB_HOST env var to enable (e.g. DB_HOST=34.136.186.49)")

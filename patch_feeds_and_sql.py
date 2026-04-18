#!/usr/bin/env python3
"""
1. Fix Connect Pub/Sub button to push trades to BOTH map feed and live feeds tab
2. Add SQL write path to shadow_simulator.py
"""
from pathlib import Path

# ════════════════════════════════════════════════════════════
# 1. FIX DASHBOARD — push trades to both feeds
# ════════════════════════════════════════════════════════════
dash = Path("templates/dashboard.html")
src = dash.read_text()
orig = src

# Replace the push function in connectPubSub to update both feeds + both stat panels
old_push = """        function push(){
            var t=gen();
            var feed=document.getElementById('d91-map-feed');
            if(feed){
                var d=document.createElement('div');d.className='trade-item';
                d.innerHTML='<div class=\\"trade-top\\"><span class=\\"trade-icon\\">\\u26a1</span><span class=\\"trade-pair\\"><strong>'+t.seller_label+'</strong> \\u2192 '+t.buyer_label+'</span><span class=\\"trade-status settled\\">SETTLED</span></div><div class=\\"trade-bottom\\"><span><span class=\\"val\\">'+(t.mwh*1000).toFixed(1)+' kWh</span></span><span>Grid <span class=\\"val amber\\">$'+t.grid_price.toFixed(4)+'</span></span><span>Settled <span class=\\"val\\">$'+t.settled_price.toFixed(4)+'</span></span></div>';
                feed.prepend(d);if(feed.children.length>50)feed.removeChild(feed.lastChild);
            }
            var s=document.getElementById('d91-settled');if(s)s.textContent=parseInt(s.textContent||0)+1;
            var m=document.getElementById('d91-mwh');if(m)m.textContent=(parseFloat(m.textContent||0)+t.mwh).toFixed(3);
            var p=document.getElementById('d91-profit');if(p)p.textContent='$'+(parseFloat((p.textContent||'$0').replace('$',''))+t.net_profit).toFixed(2);
            var c=document.getElementById('d91-co2');if(c)c.textContent=(parseFloat(c.textContent||0)+t.co2_tons).toFixed(2)+' t';
        }"""

new_push = """        function push(){
            var t=gen();
            var html='<div class=\\"trade-top\\"><span class=\\"trade-icon\\">\\u26a1</span><span class=\\"trade-pair\\"><strong>'+t.seller_label+'</strong> \\u2192 '+t.buyer_label+'</span><span class=\\"trade-status settled\\">SETTLED</span></div><div class=\\"trade-bottom\\"><span><span class=\\"val\\">'+(t.mwh*1000).toFixed(1)+' kWh</span></span><span>Grid <span class=\\"val amber\\">$'+t.grid_price.toFixed(4)+'</span></span><span>Settled <span class=\\"val\\">$'+t.settled_price.toFixed(4)+'</span></span></div>';
            ['d91-map-feed','d91-feed'].forEach(function(id){
                var feed=document.getElementById(id);
                if(feed){var d=document.createElement('div');d.className='trade-item';d.innerHTML=html;feed.prepend(d);if(feed.children.length>50)feed.removeChild(feed.lastChild);}
            });
            var s=document.getElementById('d91-settled');if(s)s.textContent=parseInt(s.textContent||0)+1;
            var m=document.getElementById('d91-mwh');if(m)m.textContent=(parseFloat(m.textContent||0)+t.mwh).toFixed(3);
            var p=document.getElementById('d91-profit');if(p)p.textContent='$'+(parseFloat((p.textContent||'$0').replace('$',''))+t.net_profit).toFixed(2);
            var c=document.getElementById('d91-co2');if(c)c.textContent=(parseFloat(c.textContent||0)+t.co2_tons).toFixed(2)+' t';
            var fs=document.getElementById('f-d91-settled');if(fs)fs.textContent=parseInt(fs.textContent||0)+1;
            var fm=document.getElementById('f-d91-mwh');if(fm)fm.textContent=(parseFloat(fm.textContent||0)+t.mwh*1000).toFixed(0);
            var fp=document.getElementById('f-d91-profit');if(fp)fp.textContent='$'+(parseFloat((fp.textContent||'$0').replace('$',''))+t.net_profit).toFixed(2);
        }"""

assert old_push in src, "push function not found in dashboard"
src = src.replace(old_push, new_push)

assert src != orig, "No changes to dashboard"
dash.write_text(src)
print("[OK] dashboard.html — trades now push to both feeds + stats")

# ════════════════════════════════════════════════════════════
# 2. ADD SQL WRITES TO SHADOW SIMULATOR
# ════════════════════════════════════════════════════════════
sim = Path("shadow_simulator.py")
s = sim.read_text()
s_orig = s

# Add SQL imports and connection at the top, after the pubsub import
s = s.replace(
    "from google.cloud import pubsub_v1",
    """from google.cloud import pubsub_v1

# SQL persistence (optional — skips gracefully if unavailable)
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
            _db_conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, dbname=DB_NAME)
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
                cur.execute(\"\"\"
                    INSERT INTO trades (trade_id, timestamp, district, seller_id, seller_label, seller_town,
                        seller_lat, seller_lng, buyer_id, buyer_label, buyer_town, buyer_lat, buyer_lng,
                        mwh, effective_mwh, distance_km, line_loss_pct, price_per_kwh,
                        gross_revenue, toll_cost, net_profit, co2_tons, trade_status,
                        settlement, matching_mode, dni_wm2, source)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (trade_id) DO NOTHING
                \"\"\", (
                    t['trade_id'], t['timestamp'], t.get('district','D91'),
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
                ))
                count += 1
            except Exception as e:
                print(f"  DB insert error: {e}")
        print(f"  DB: {count} trades written")
        return count
    except Exception as e:
        print(f"  DB write error: {e}")
        return 0"""
)

# Add SQL write call after publishing trades, before the summary print
s = s.replace(
    "    total_mwh = sum(t[\"mwh\"] for t in trades)",
    "    # Write to SQL if configured\n    write_trades_to_db(trades)\n\n    total_mwh = sum(t[\"mwh\"] for t in trades)"
)

assert s != s_orig, "No changes to simulator"
sim.write_text(s)
print("[OK] shadow_simulator.py — SQL write path added (env-var driven)")

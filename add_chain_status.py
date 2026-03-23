#!/usr/bin/env python3
"""
TINY-HUB — Add blockchain status to dashboard

1. Creates chain_api.py (connects to Hardhat via Docker network)
2. Wires it into app.py
3. Adds IDs to chain section in dashboard.html
4. Adds fetchChain() JS to poll every 5 seconds
5. Moves town bar to top center

Run from project root:
    python3 add_chain_status.py
"""

from pathlib import Path

# ══════════════════════════════════════════════════════════════
# STEP 1: Create chain_api.py
# ══════════════════════════════════════════════════════════════
CHAIN = Path("chain_api.py")
CHAIN.write_text('''"""Chain status API — connects to Hardhat node for on-chain stats."""
import os
from flask import jsonify

RPC_URL = os.environ.get("RPC_URL", "http://hardhat:8545")

def register_chain_routes(app):
    @app.route("/api/chain")
    def api_chain():
        try:
            from web3 import Web3
            import json
            w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 3}))
            if not w3.is_connected():
                return jsonify({"connected": False})

            result = {
                "connected": True,
                "chain_id": w3.eth.chain_id,
                "block": w3.eth.block_number,
            }

            dep_path = "/shared/deployment.json" if os.path.exists("/shared/deployment.json") else "deployment.json"
            if os.path.exists(dep_path):
                with open(dep_path) as f:
                    dep = json.load(f)
                contract_addr = dep.get("TinyHubMarketV2")
                token_addr = dep.get("TinyHubToken")
                if not token_addr and "contracts" in dep:
                    token_addr = dep["contracts"].get("TinyHubToken", {}).get("address")

                if contract_addr:
                    abi = [{"inputs":[],"name":"tradeCount","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"}]
                    c = w3.eth.contract(address=contract_addr, abi=abi)
                    result["trade_count"] = c.functions.tradeCount().call()

                if token_addr:
                    tabi = [{"inputs":[],"name":"totalSupply","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"}]
                    t = w3.eth.contract(address=token_addr, abi=tabi)
                    raw = t.functions.totalSupply().call()
                    result["token_supply"] = float(w3.from_wei(raw, "ether"))

            return jsonify(result)
        except Exception as e:
            return jsonify({"connected": False, "error": str(e)[:100]})
''', encoding="utf-8")
print("  ✅ chain_api.py created")


# ══════════════════════════════════════════════════════════════
# STEP 2: Wire into app.py
# ══════════════════════════════════════════════════════════════
APP = Path("app.py")
src = APP.read_text(encoding="utf-8")

if "chain_api" not in src:
    # Add import
    OLD = "from cloudsql_api import register_postgis_routes"
    NEW = "from cloudsql_api import register_postgis_routes\nfrom chain_api import register_chain_routes"
    if OLD in src:
        src = src.replace(OLD, NEW, 1)
        print("  ✅ app.py: chain_api import added")

    # Register routes
    OLD2 = "register_postgis_routes(app)"
    NEW2 = "register_postgis_routes(app)\nregister_chain_routes(app)"
    if OLD2 in src:
        src = src.replace(OLD2, NEW2, 1)
        print("  ✅ app.py: chain routes registered")

    APP.write_text(src, encoding="utf-8")
else:
    print("  ⏭️  app.py: chain_api already wired")


# ══════════════════════════════════════════════════════════════
# STEP 3: Add IDs to chain section in dashboard.html
# ══════════════════════════════════════════════════════════════
DASH = Path("templates/dashboard.html")
dash = DASH.read_text(encoding="utf-8")

# D91 chain section — add IDs
OLD_D91_CHAIN = '''<div class="chain-section">
                        <div class="chain-title">\u26D3 Blockchain</div>
                        <div class="srow"><span class="slabel">On-Chain Trades</span><span class="sval purple">\u2014</span></div>
                        <div class="srow"><span class="slabel">THN Supply</span><span class="sval purple">\u2014</span></div>
                        <div class="srow"><span class="slabel">Chain Status</span><span class="sval" style="color:var(--text-dim)">OFFLINE</span></div>
                    </div>'''

# Try multiple patterns since formatting might differ
patterns_d91 = [
    OLD_D91_CHAIN,
    '<div class="chain-section">\n                        <div class="chain-title">⛓ Blockchain</div>\n                        <div class="srow"><span class="slabel">On-Chain Trades</span><span class="sval purple">—</span></div>\n                        <div class="srow"><span class="slabel">THN Supply</span><span class="sval purple">—</span></div>\n                        <div class="srow"><span class="slabel">Chain Status</span><span class="sval" style="color:var(--text-dim)">OFFLINE</span></div>\n                    </div>',
]

NEW_D91_CHAIN = '''<div class="chain-section">
                        <div class="chain-title">\u26D3 Blockchain</div>
                        <div class="srow"><span class="slabel">On-Chain Trades</span><span class="sval purple" id="d91-chain-trades">\u2014</span></div>
                        <div class="srow"><span class="slabel">THN Supply</span><span class="sval purple" id="d91-token-supply">\u2014</span></div>
                        <div class="srow"><span class="slabel">Chain Status</span><span class="sval" id="d91-chain-status" style="color:var(--text-dim)">OFFLINE</span></div>
                    </div>'''

replaced = False
if "d91-chain-trades" not in dash:
    for pat in patterns_d91:
        if pat in dash:
            dash = dash.replace(pat, NEW_D91_CHAIN, 1)
            print("  ✅ Dashboard: D91 chain section IDs added")
            replaced = True
            break
    if not replaced:
        # Brute force: find and replace by unique strings
        dash = dash.replace(
            '<span class="sval purple">—</span></div>\n                        <div class="srow"><span class="slabel">THN Supply</span><span class="sval purple">—</span></div>\n                        <div class="srow"><span class="slabel">Chain Status</span><span class="sval" style="color:var(--text-dim)">OFFLINE</span></div>',
            '<span class="sval purple" id="d91-chain-trades">—</span></div>\n                        <div class="srow"><span class="slabel">THN Supply</span><span class="sval purple" id="d91-token-supply">—</span></div>\n                        <div class="srow"><span class="slabel">Chain Status</span><span class="sval" id="d91-chain-status" style="color:var(--text-dim)">OFFLINE</span></div>',
            1
        )
        if "d91-chain-trades" in dash:
            print("  ✅ Dashboard: D91 chain IDs added (fallback)")
        else:
            print("  ⚠️  Dashboard: Could not add D91 chain IDs — add manually")
else:
    print("  ⏭️  Dashboard: chain IDs already present")


# ══════════════════════════════════════════════════════════════
# STEP 4: Add fetchChain() JS
# ══════════════════════════════════════════════════════════════
if "fetchChain" not in dash:
    OLD_POLL = "setInterval(pollStats, 3000);"
    CHAIN_JS = """setInterval(pollStats, 3000);
    async function fetchChain() {
        try {
            const d = await (await fetch('/api/chain')).json();
            const ct = document.getElementById('d91-chain-trades');
            const ts = document.getElementById('d91-token-supply');
            const cs = document.getElementById('d91-chain-status');
            if (d.connected) {
                if (ct) ct.textContent = d.trade_count !== undefined ? d.trade_count.toLocaleString() : '—';
                if (ts) ts.textContent = d.token_supply !== undefined ? d.token_supply.toFixed(3) + ' THN' : '—';
                if (cs) { cs.textContent = 'CONNECTED'; cs.style.color = 'var(--green)'; }
            } else {
                if (cs) { cs.textContent = 'OFFLINE'; cs.style.color = 'var(--red)'; }
            }
        } catch (e) {}
    }
    fetchChain(); setInterval(fetchChain, 5000);"""

    if OLD_POLL in dash:
        dash = dash.replace(OLD_POLL, CHAIN_JS, 1)
        print("  ✅ Dashboard: fetchChain() JS added (polls every 5s)")
    else:
        print("  ⚠️  Dashboard: pollStats interval not found — add fetchChain manually")
else:
    print("  ⏭️  Dashboard: fetchChain already exists")


# ══════════════════════════════════════════════════════════════
# STEP 5: Move town bar to top center
# ══════════════════════════════════════════════════════════════
OLD_TOWN = ".town-card { position: absolute; top: 14px; left: 50%; transform: translateX(-50%); padding: 10px 14px; z-index: 500; }"
OLD_TOWN2 = ".town-card { position: absolute; bottom: 250px; left: 14px; padding: 10px 14px; }"

if OLD_TOWN in dash:
    print("  ⏭️  Dashboard: town bar already centered")
elif OLD_TOWN2 in dash:
    dash = dash.replace(OLD_TOWN2, ".town-card { position: absolute; top: 14px; left: 50%; transform: translateX(-50%); padding: 10px 14px; z-index: 500; }", 1)
    print("  ✅ Dashboard: town bar moved to top center")
else:
    print("  ⚠️  Dashboard: town-card CSS not found — may already be patched")


DASH.write_text(dash, encoding="utf-8")

print()
print("  ✅ Blockchain status + town bar fix complete.")
print()
print("  Rebuild: sudo docker-compose up -d --build")
print()

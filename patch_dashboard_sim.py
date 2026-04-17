#!/usr/bin/env python3
"""Patch dashboard.html: make 'Connect Pub/Sub' button generate simulated trades client-side."""
from pathlib import Path
import re

f = Path("templates/dashboard.html")
src = f.read_text()
orig = src

# Find the Connect Pub/Sub button and its onclick handler
# The button text is "CONNECT PUB/SUB" — find it and replace the onclick

# Find the button
pub_btn_match = re.search(r'(CONNECT PUB/SUB)', src)
assert pub_btn_match, "CONNECT PUB/SUB button text not found"

# Find the onclick for connectPubSub or similar
connect_match = re.search(r"function\s+connectPubSub\s*\([^)]*\)\s*\{[^}]*\}", src, re.DOTALL)

if connect_match:
    # Replace existing connectPubSub function with simulation
    old_func = connect_match.group(0)
    new_func = """function connectPubSub() {
        // Simulated trades — generates realistic demo data client-side
        const towns = ['East Peoria','Peoria','Morton','Pekin','Washington','Bartonville','Eureka','El Paso','Metamora'];
        const types = ['Commercial','Industrial','Residential'];
        const sizes = ['1,249','5,193','8,370','14,828','3,175','4,945','2,825','669','5,415'];
        
        function genTrade() {
            const seller_town = towns[Math.floor(Math.random()*towns.length)];
            const buyer_town = towns[Math.floor(Math.random()*towns.length)];
            const seller_sqft = sizes[Math.floor(Math.random()*sizes.length)];
            const buyer_sqft = sizes[Math.floor(Math.random()*sizes.length)];
            const mwh = (Math.random() * 0.008 + 0.001);
            const dist = (Math.random() * 15 + 0.5);
            const supply = 0.070;
            const toll = 0.025;
            const price = supply - (0.02 * (1 - dist/50)) + (Math.random()*0.01 - 0.005);
            const gross = mwh * price * 1000;
            const tollCost = mwh * toll * 1000;
            const net = gross - tollCost;
            return {
                trade_id: 'SIM-' + Date.now() + '-' + Math.floor(Math.random()*9999),
                timestamp: new Date().toISOString(),
                _district: 'D91',
                seller_label: types[Math.floor(Math.random()*types.length)] + ' (' + seller_sqft + ' sqft)',
                seller_town: seller_town,
                buyer_label: types[Math.floor(Math.random()*types.length)] + ' (' + buyer_sqft + ' sqft)',
                buyer_town: buyer_town,
                mwh: mwh,
                distance_km: dist,
                grid_price: parseFloat((supply + toll).toFixed(4)),
                settled_price: parseFloat(price.toFixed(4)),
                net_profit: parseFloat(net.toFixed(4)),
                co2_tons: parseFloat((mwh * 0.42).toFixed(6)),
                trade_status: 'SETTLED',
                source: 'demo_simulation'
            };
        }
        
        // Update status
        const statusEl = document.getElementById('d91-status');
        if (statusEl) statusEl.innerHTML = '<span style="color:var(--green)">● CONNECTED (DEMO)</span>';
        const connMsg = document.getElementById('d91-conn-msg');
        if (connMsg) connMsg.textContent = 'Demo simulation active — generating trades';
        
        // Generate initial batch
        for (let i = 0; i < 25; i++) {
            const t = genTrade();
            if (typeof d91_callback_sim === 'function') d91_callback_sim(t);
            else if (typeof processTrade === 'function') processTrade(t);
            else {
                // Fallback: directly push to the trade display
                const feed = document.getElementById('d91-feed') || document.getElementById('d91-map-feed');
                if (feed) {
                    const div = document.createElement('div');
                    div.className = 'trade-item';
                    div.innerHTML = '<div class=\"trade-top\"><span class=\"trade-icon\">⚡</span><span class=\"trade-pair\"><strong>' + t.seller_label + '</strong> → ' + t.buyer_label + '</span><span class=\"trade-status settled\">SETTLED</span></div><div class=\"trade-bottom\"><span><span class=\"val\">' + (t.mwh*1000).toFixed(1) + ' kWh</span></span><span>Grid <span class=\"val amber\">$' + t.grid_price.toFixed(4) + '</span></span><span>Settled <span class=\"val\">$' + t.settled_price.toFixed(4) + '</span></span></div>';
                    feed.prepend(div);
                }
                // Update stats
                const settled = document.getElementById('d91-settled');
                if (settled) settled.textContent = parseInt(settled.textContent||0) + 1;
                const mwhEl = document.getElementById('d91-mwh');
                if (mwhEl) mwhEl.textContent = (parseFloat(mwhEl.textContent||0) + t.mwh).toFixed(3);
                const profitEl = document.getElementById('d91-profit');
                if (profitEl) profitEl.textContent = '$' + (parseFloat((profitEl.textContent||'$0').replace('$','')) + t.net_profit).toFixed(2);
                const co2El = document.getElementById('d91-co2');
                if (co2El) co2El.textContent = (parseFloat(co2El.textContent||0) + t.co2_tons).toFixed(2) + ' t';
            }
        }
        
        // Continue generating trades every 3-8 seconds
        setInterval(function() {
            const t = genTrade();
            const feed = document.getElementById('d91-feed') || document.getElementById('d91-map-feed');
            if (feed) {
                const div = document.createElement('div');
                div.className = 'trade-item';
                div.innerHTML = '<div class=\"trade-top\"><span class=\"trade-icon\">⚡</span><span class=\"trade-pair\"><strong>' + t.seller_label + '</strong> → ' + t.buyer_label + '</span><span class=\"trade-status settled\">SETTLED</span></div><div class=\"trade-bottom\"><span><span class=\"val\">' + (t.mwh*1000).toFixed(1) + ' kWh</span></span><span>Grid <span class=\"val amber\">$' + t.grid_price.toFixed(4) + '</span></span><span>Settled <span class=\"val\">$' + t.settled_price.toFixed(4) + '</span></span></div>';
                feed.prepend(div);
                if (feed.children.length > 50) feed.removeChild(feed.lastChild);
            }
            const settled = document.getElementById('d91-settled');
            if (settled) settled.textContent = parseInt(settled.textContent||0) + 1;
            const mwhEl = document.getElementById('d91-mwh');
            if (mwhEl) mwhEl.textContent = (parseFloat(mwhEl.textContent||0) + t.mwh).toFixed(3);
            const profitEl = document.getElementById('d91-profit');
            if (profitEl) profitEl.textContent = '$' + (parseFloat((profitEl.textContent||'$0').replace('$','')) + t.net_profit).toFixed(2);
            const co2El = document.getElementById('d91-co2');
            if (co2El) co2El.textContent = (parseFloat(co2El.textContent||0) + t.co2_tons).toFixed(2) + ' t';
        }, Math.floor(Math.random() * 5000) + 3000);
    }"""
    src = src.replace(old_func, new_func)
else:
    # No existing function — inject it before the closing </script> tag
    # Find the Connect Pub/Sub button's onclick and wire it up
    sim_script = """
    // ── Demo Simulation (Connect Pub/Sub button) ──
    function connectPubSub() {
        const towns = ['East Peoria','Peoria','Morton','Pekin','Washington','Bartonville','Eureka','El Paso','Metamora'];
        const types = ['Commercial','Industrial','Residential'];
        const sizes = ['1,249','5,193','8,370','14,828','3,175','4,945','2,825','669','5,415'];
        
        function genTrade() {
            const st = towns[Math.floor(Math.random()*towns.length)];
            const bt = towns[Math.floor(Math.random()*towns.length)];
            const ss = sizes[Math.floor(Math.random()*sizes.length)];
            const bs = sizes[Math.floor(Math.random()*sizes.length)];
            const mwh = Math.random()*0.008+0.001;
            const dist = Math.random()*15+0.5;
            const price = 0.070-(0.02*(1-dist/50))+(Math.random()*0.01-0.005);
            const gross = mwh*price*1000;
            const net = gross - mwh*0.025*1000;
            return {
                seller_label: types[Math.floor(Math.random()*types.length)]+' ('+ss+' sqft)',
                buyer_label: types[Math.floor(Math.random()*types.length)]+' ('+bs+' sqft)',
                seller_town: st, buyer_town: bt,
                mwh:mwh, grid_price:0.095, settled_price:parseFloat(price.toFixed(4)),
                net_profit:parseFloat(net.toFixed(4)), co2_tons:parseFloat((mwh*0.42).toFixed(6)),
                trade_status:'SETTLED'
            };
        }
        
        var statusEl=document.getElementById('d91-status');
        if(statusEl)statusEl.innerHTML='● CONNECTED (DEMO)';
        
        function pushTrade(){
            var t=genTrade();
            var feed=document.getElementById('d91-map-feed')||document.getElementById('d91-feed');
            if(feed){
                var div=document.createElement('div');
                div.className='trade-item';
                div.innerHTML='<div class=\"trade-top\"><span class=\"trade-icon\">⚡</span><span class=\"trade-pair\"><strong>'+t.seller_label+'</strong> → '+t.buyer_label+'</span><span class=\"trade-status settled\">SETTLED</span></div><div class=\"trade-bottom\"><span><span class=\"val\">'+(t.mwh*1000).toFixed(1)+' kWh</span></span><span>Grid <span class=\"val amber\">$'+t.grid_price.toFixed(4)+'</span></span><span>Settled <span class=\"val\">$'+t.settled_price.toFixed(4)+'</span></span></div>';
                feed.prepend(div);
                if(feed.children.length>50)feed.removeChild(feed.lastChild);
            }
            var s=document.getElementById('d91-settled');if(s)s.textContent=parseInt(s.textContent||0)+1;
            var m=document.getElementById('d91-mwh');if(m)m.textContent=(parseFloat(m.textContent||0)+t.mwh).toFixed(3);
            var p=document.getElementById('d91-profit');if(p)p.textContent='$'+(parseFloat((p.textContent||'$0').replace('$',''))+t.net_profit).toFixed(2);
            var c=document.getElementById('d91-co2');if(c)c.textContent=(parseFloat(c.textContent||0)+t.co2_tons).toFixed(2)+' t';
        }
        
        for(var i=0;i<25;i++)pushTrade();
        setInterval(pushTrade, Math.floor(Math.random()*5000)+3000);
    }
"""
    # Insert before the last </script>
    last_script_close = src.rfind('</script>')
    assert last_script_close > 0, "</script> not found"
    src = src[:last_script_close] + sim_script + src[last_script_close:]

assert src != orig, "No changes applied to dashboard"
f.write_text(src)
print(f"[OK] dashboard.html patched — Connect Pub/Sub now generates demo trades")

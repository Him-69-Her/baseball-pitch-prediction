#!/usr/bin/env python3
"""Replace the empty connectPubSub function with a client-side trade simulator."""
from pathlib import Path

f = Path("templates/dashboard.html")
src = f.read_text()

old = """    function connectPubSub() {
        document.querySelectorAll('.action-status').forEach(el => el.textContent = 'SSE connected — streaming trades');
    }"""

new = """    function connectPubSub() {
        var towns=['East Peoria','Peoria','Morton','Pekin','Washington','Bartonville','Eureka','El Paso','Metamora'];
        var types=['Commercial','Industrial','Residential'];
        var sizes=['1,249','5,193','8,370','14,828','3,175','4,945','2,825','669','5,415'];
        function gen(){
            var st=towns[Math.floor(Math.random()*towns.length)];
            var bt=towns[Math.floor(Math.random()*towns.length)];
            var ss=sizes[Math.floor(Math.random()*sizes.length)];
            var bs=sizes[Math.floor(Math.random()*sizes.length)];
            var mwh=Math.random()*0.008+0.001;
            var dist=Math.random()*15+0.5;
            var price=0.070-(0.02*(1-dist/50))+(Math.random()*0.01-0.005);
            var net=mwh*price*1000-mwh*0.025*1000;
            return{
                _district:'D91',seller_label:types[Math.floor(Math.random()*types.length)]+' ('+ss+' sqft)',
                buyer_label:types[Math.floor(Math.random()*types.length)]+' ('+bs+' sqft)',
                seller_town:st,buyer_town:bt,mwh:mwh,
                grid_price:0.095,settled_price:parseFloat(price.toFixed(4)),
                net_profit:parseFloat(net.toFixed(4)),co2_tons:parseFloat((mwh*0.42).toFixed(6)),
                trade_status:'SETTLED'
            };
        }
        var el=document.getElementById('d91-status');
        if(el)el.innerHTML='<span style=\"color:var(--green)\">\\u25cf CONNECTED (DEMO)</span>';
        document.querySelectorAll('.action-status').forEach(function(e){e.textContent='Demo simulation active';});
        function push(){
            var t=gen();
            var feed=document.getElementById('d91-map-feed');
            if(feed){
                var d=document.createElement('div');d.className='trade-item';
                d.innerHTML='<div class=\"trade-top\"><span class=\"trade-icon\">\\u26a1</span><span class=\"trade-pair\"><strong>'+t.seller_label+'</strong> \\u2192 '+t.buyer_label+'</span><span class=\"trade-status settled\">SETTLED</span></div><div class=\"trade-bottom\"><span><span class=\"val\">'+(t.mwh*1000).toFixed(1)+' kWh</span></span><span>Grid <span class=\"val amber\">$'+t.grid_price.toFixed(4)+'</span></span><span>Settled <span class=\"val\">$'+t.settled_price.toFixed(4)+'</span></span></div>';
                feed.prepend(d);if(feed.children.length>50)feed.removeChild(feed.lastChild);
            }
            var s=document.getElementById('d91-settled');if(s)s.textContent=parseInt(s.textContent||0)+1;
            var m=document.getElementById('d91-mwh');if(m)m.textContent=(parseFloat(m.textContent||0)+t.mwh).toFixed(3);
            var p=document.getElementById('d91-profit');if(p)p.textContent='$'+(parseFloat((p.textContent||'$0').replace('$',''))+t.net_profit).toFixed(2);
            var c=document.getElementById('d91-co2');if(c)c.textContent=(parseFloat(c.textContent||0)+t.co2_tons).toFixed(2)+' t';
        }
        for(var i=0;i<25;i++)push();
        setInterval(push,Math.floor(Math.random()*5000)+3000);
    }"""

assert old in src, "connectPubSub function not found"
src = src.replace(old, new)
f.write_text(src)
print("[OK] Connect Pub/Sub button now generates demo trades")

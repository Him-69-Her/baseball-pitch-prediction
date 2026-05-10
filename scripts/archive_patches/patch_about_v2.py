#!/usr/bin/env python3
"""Rebuild /about with editorial multi-column layout + numbered sections."""
from pathlib import Path

about_html = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TINY-HUB ENERGY // About</title>
<meta name="description" content="Upgrading the grid for the future of energy. A peer-to-peer marketplace where communities generate, share, and profit from their own power.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Monoton&family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#000;--cyan:#00f0ff;--cyan-dim:#00b8c7;--magenta:#ff2d95;
    --sun-1:#ffcc00;--sun-2:#ff9500;--sun-3:#ff5500;--sun-4:#c72c00;
    --ink:#e6f8ff;--ink-dim:#7ba9b3;--ink-body:#cdd8db;
  }
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{background:var(--bg);color:var(--ink);font-family:'Inter',sans-serif;overflow-x:hidden}
  body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:999;
    background:repeating-linear-gradient(to bottom,rgba(0,0,0,0) 0,rgba(0,0,0,0) 2px,rgba(0,0,0,0.15) 3px,rgba(0,0,0,0) 4px);mix-blend-mode:multiply}

  nav{position:fixed;top:0;left:0;right:0;z-index:50;display:flex;justify-content:space-between;align-items:center;padding:1.2rem 2rem;background:linear-gradient(to bottom,rgba(0,0,0,0.95) 0%,rgba(0,0,0,0.75) 70%,transparent);border-bottom:1px solid rgba(0,240,255,0.15);backdrop-filter:blur(6px)}
  .logo{font-family:'Monoton',cursive;font-size:1.6rem;letter-spacing:.15em;color:var(--sun-1);text-decoration:none;text-shadow:0 0 8px var(--sun-2),0 0 24px var(--sun-3)}
  .nav-links{display:flex;gap:1.4rem;list-style:none;flex-wrap:wrap;justify-content:flex-end}
  .nav-links a{color:var(--cyan);text-decoration:none;font-size:.7rem;letter-spacing:.18em;text-transform:uppercase;transition:all .2s;text-shadow:0 0 4px var(--cyan-dim);white-space:nowrap;font-family:'JetBrains Mono',monospace}
  .nav-links a:hover{color:var(--magenta);text-shadow:0 0 8px var(--magenta)}
  .nav-links a.active{color:var(--sun-1);text-shadow:0 0 8px var(--sun-2)}

  .page-hero{position:relative;height:42vh;min-height:300px;overflow:hidden}
  .atmosphere{position:absolute;left:0;right:0;bottom:50%;height:50%;z-index:1;pointer-events:none;
    background:radial-gradient(ellipse 50% 70% at 50% 100%,rgba(255,204,0,0.35) 0%,rgba(255,149,0,0.22) 20%,rgba(255,85,0,0.12) 45%,transparent 70%),linear-gradient(to top,rgba(255,149,0,0.25) 0%,rgba(255,85,0,0.14) 25%,rgba(199,44,0,0.08) 50%,transparent 100%);filter:blur(4px);animation:atmos-breathe 8s ease-in-out infinite}
  @keyframes atmos-breathe{0%,100%{opacity:.85}50%{opacity:1}}
  .sun-wrap{position:absolute;bottom:50%;left:50%;width:min(380px,38vw);aspect-ratio:2/1;z-index:3;pointer-events:none;transform:translateX(-50%);animation:sun-breathe 5s ease-in-out infinite}
  .sun-wrap svg{width:100%;height:100%;display:block;overflow:visible;filter:drop-shadow(0 0 10px rgba(255,149,0,0.55))}
  @keyframes sun-breathe{0%,100%{transform:translateX(-50%) scale(1)}50%{transform:translateX(-50%) scale(1.02)}}
  .horizon{position:absolute;bottom:50%;left:0;right:0;height:2px;z-index:4;background:linear-gradient(to right,transparent,var(--cyan) 15%,var(--cyan) 85%,transparent);box-shadow:0 0 12px var(--cyan),0 0 32px var(--cyan),0 0 60px rgba(0,240,255,0.5)}
  .grid-wrap{position:absolute;bottom:0;left:0;right:0;height:50%;perspective:400px;perspective-origin:50% 0%;z-index:2;pointer-events:none;overflow:hidden}
  .grid-floor{position:absolute;bottom:0;left:-50%;width:200%;height:100%;background-image:linear-gradient(to right,var(--cyan) 2px,transparent 2px),linear-gradient(to bottom,var(--cyan) 2px,transparent 2px);background-size:80px 80px;transform:rotateX(70deg);transform-origin:50% 100%;animation:grid-scroll 6s linear infinite;filter:drop-shadow(0 0 6px var(--cyan));opacity:.85}
  @keyframes grid-scroll{0%{background-position:0 0}100%{background-position:0 80px}}
  .grid-mask{position:absolute;bottom:0;left:0;right:0;height:50%;pointer-events:none;z-index:3;background:linear-gradient(to top,transparent 0%,transparent 40%,rgba(0,0,0,0.6) 80%,#000 100%)}

  main{max-width:1280px;margin:0 auto;padding:4rem 2rem 6rem;position:relative;z-index:2}
  main::before{content:"";position:absolute;top:0;bottom:0;left:2rem;width:1px;background:linear-gradient(to bottom,transparent,var(--cyan) 8%,var(--cyan) 92%,transparent);opacity:.35;box-shadow:0 0 8px var(--cyan-dim);z-index:-1}
  @media(max-width:900px){main::before{display:none}}

  section.block{position:relative;margin-bottom:7rem;padding-left:clamp(3rem,7vw,7rem)}
  section.block:last-child{margin-bottom:0}

  .chapter-marker{position:absolute;left:0;top:-.5rem;font-family:'Monoton',cursive;font-size:clamp(3rem,6vw,5.5rem);color:transparent;-webkit-text-stroke:1.5px var(--cyan-dim);letter-spacing:.05em;line-height:1;opacity:.5;pointer-events:none;z-index:0}
  @media(max-width:700px){.chapter-marker{position:relative;left:auto;top:auto;margin-bottom:.5rem;font-size:2.2rem;opacity:.6}}

  .section-title{font-family:'Monoton',cursive;font-size:clamp(1.4rem,2.5vw,2rem);letter-spacing:.08em;color:var(--sun-1);text-shadow:0 0 10px var(--sun-2),0 0 24px var(--sun-3);margin-bottom:2rem;position:relative;z-index:2;line-height:1.1}

  /* MISSION */
  .mission-banner{display:grid;grid-template-columns:1.2fr 1fr;gap:3rem;align-items:center}
  @media(max-width:800px){.mission-banner{grid-template-columns:1fr}}
  .mission-words{font-family:'Monoton',cursive;line-height:.95;letter-spacing:.04em}
  .mission-words .w{display:block;font-size:clamp(2.2rem,6vw,4.2rem)}
  .mission-words .w1{color:var(--sun-1);text-shadow:0 0 12px var(--sun-2),0 0 28px var(--sun-3)}
  .mission-words .w2{color:var(--cyan);text-shadow:0 0 10px var(--cyan-dim);padding-left:clamp(1rem,3vw,2.5rem)}
  .mission-words .w3{color:var(--magenta);text-shadow:0 0 10px var(--magenta);padding-left:clamp(2rem,6vw,5rem)}
  .mission-statement-block{border-left:2px solid var(--sun-2);padding:1.2rem 0 1.2rem 1.5rem;background:linear-gradient(90deg,rgba(255,149,0,0.08),transparent 80%)}
  .mission-statement-block p{font-size:clamp(1rem,1.3vw,1.15rem);line-height:1.65;color:var(--ink);font-weight:400}

  /* PROBLEM */
  .problem-intro{font-size:clamp(1.1rem,1.6vw,1.3rem);line-height:1.6;color:var(--ink);font-weight:300;max-width:58ch;margin-bottom:1rem}
  .problem-intro strong{color:var(--sun-1);font-weight:500;text-shadow:0 0 6px var(--sun-2)}
  .stat-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1.5rem;margin:2.5rem 0 3rem;border-top:1px solid rgba(0,240,255,0.18);border-bottom:1px solid rgba(0,240,255,0.18);padding:1.8rem 0}
  .stat{text-align:center;padding:0 .5rem}
  .stat-num{font-family:'Monoton',cursive;font-size:clamp(2rem,3.6vw,2.8rem);color:var(--sun-1);text-shadow:0 0 8px var(--sun-2);letter-spacing:.02em;line-height:1;margin-bottom:.4rem}
  .stat-label{font-family:'JetBrains Mono',monospace;font-size:.62rem;letter-spacing:.28em;text-transform:uppercase;color:var(--cyan-dim);line-height:1.5}
  .problem-sub{margin-bottom:2.2rem}
  .problem-sub h3{font-family:'JetBrains Mono',monospace;font-size:.9rem;letter-spacing:.15em;text-transform:uppercase;color:var(--sun-1);text-shadow:0 0 6px var(--sun-2);margin-bottom:.8rem;font-weight:700;display:flex;align-items:center;gap:.8rem}
  .problem-sub h3::before{content:"\25B8";color:var(--cyan);font-size:.95rem}
  .problem-sub h3::after{content:"";flex:1;height:1px;background:linear-gradient(to right,rgba(255,149,0,0.4),transparent)}
  .problem-sub p{font-size:1rem;line-height:1.7;color:var(--ink-body);margin-bottom:.9rem;font-weight:300;max-width:68ch}
  .problem-sub p strong{color:var(--ink);font-weight:500}
  .problem-close{margin-top:2rem;padding:1.4rem 1.6rem;border:1px solid var(--cyan);background:linear-gradient(90deg,rgba(0,240,255,0.06),transparent);font-size:1.05rem;line-height:1.6;color:var(--ink);font-weight:400;position:relative}
  .problem-close::before{content:"";position:absolute;top:-1px;left:-1px;width:18px;height:18px;border-top:2px solid var(--sun-1);border-left:2px solid var(--sun-1)}
  .problem-close::after{content:"";position:absolute;bottom:-1px;right:-1px;width:18px;height:18px;border-bottom:2px solid var(--sun-1);border-right:2px solid var(--sun-1)}
  .problem-close strong{color:var(--sun-1);text-shadow:0 0 6px var(--sun-2)}

  /* THESIS */
  .thesis-intro{max-width:64ch;margin-bottom:2rem}
  .thesis-intro p{font-size:1.05rem;line-height:1.7;color:var(--ink-body);margin-bottom:1rem;font-weight:300}
  .thesis-intro p strong{color:var(--cyan);font-weight:500;text-shadow:0 0 4px var(--cyan-dim)}
  .thesis-hook{font-family:'Monoton',cursive;font-size:clamp(1.4rem,2.8vw,2.2rem);color:var(--magenta);text-shadow:0 0 10px var(--magenta);letter-spacing:.05em;line-height:1.15;padding:1.5rem 0;margin:1.5rem 0;border-top:1px solid rgba(255,45,149,0.3);border-bottom:1px solid rgba(255,45,149,0.3)}
  .thesis-grid{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin-top:2rem}
  @media(max-width:800px){.thesis-grid{grid-template-columns:1fr}}
  .thesis-card{border:1px solid rgba(0,240,255,0.2);padding:1.5rem;background:linear-gradient(135deg,rgba(0,240,255,0.03),transparent);position:relative;transition:all .3s}
  .thesis-card::before{content:"";position:absolute;top:0;left:0;width:3px;height:40px;background:var(--magenta);box-shadow:0 0 8px var(--magenta)}
  .thesis-card:hover{border-color:var(--cyan);box-shadow:0 0 16px rgba(0,240,255,0.18)}
  .thesis-card-num{font-family:'Monoton',cursive;font-size:1.6rem;color:var(--magenta);text-shadow:0 0 8px var(--magenta);letter-spacing:.05em;margin-bottom:.4rem;line-height:1}
  .thesis-card-title{font-family:'JetBrains Mono',monospace;font-size:.95rem;font-weight:700;letter-spacing:.08em;color:var(--sun-1);text-shadow:0 0 6px var(--sun-2);margin-bottom:.9rem;line-height:1.3}
  .thesis-card-body{font-size:.92rem;line-height:1.6;color:var(--ink-body);margin-bottom:.9rem;font-weight:300}
  .thesis-take{padding:.75rem .9rem;background:rgba(0,240,255,0.06);border-left:2px solid var(--cyan);font-size:.88rem;line-height:1.55;color:var(--ink-body)}
  .thesis-take strong{color:var(--cyan);font-weight:600}
  .thesis-close{margin-top:2.5rem;padding-top:2rem;border-top:1px solid rgba(0,240,255,0.2)}
  .thesis-close h4{font-family:'JetBrains Mono',monospace;font-size:.85rem;letter-spacing:.2em;text-transform:uppercase;color:var(--magenta);text-shadow:0 0 6px var(--magenta);margin-bottom:1rem}
  .thesis-close p{font-size:1rem;line-height:1.7;color:var(--ink-body);margin-bottom:.9rem;font-weight:300;max-width:68ch}
  .thesis-close p strong{color:var(--ink);font-weight:500}

  /* STATUS */
  .status-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1.2rem}
  .status-card{border:1px solid rgba(0,240,255,0.22);padding:1.3rem;background:linear-gradient(135deg,rgba(0,240,255,0.04),rgba(0,0,0,0) 80%);position:relative;transition:all .25s}
  .status-card:hover{border-color:var(--cyan);transform:translateY(-2px);box-shadow:0 4px 20px rgba(0,240,255,0.12)}
  .status-card-head{display:flex;align-items:center;justify-content:space-between;padding-bottom:.8rem;margin-bottom:.9rem;border-bottom:1px solid rgba(0,240,255,0.15)}
  .status-card-title{font-family:'Monoton',cursive;font-size:1.05rem;letter-spacing:.06em;color:var(--sun-1);text-shadow:0 0 6px var(--sun-2)}
  .status-dot{display:inline-flex;align-items:center;gap:.4rem;font-family:'JetBrains Mono',monospace;font-size:.55rem;letter-spacing:.18em;text-transform:uppercase;color:var(--cyan-dim)}
  .status-dot::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--cyan);box-shadow:0 0 6px var(--cyan);animation:blink 2s ease-in-out infinite}
  .status-dot.next::before{background:var(--magenta);box-shadow:0 0 6px var(--magenta)}
  @keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}
  .status-items{list-style:none;padding:0}
  .status-items li{position:relative;padding:.4rem 0 .4rem 1.1rem;font-size:.87rem;line-height:1.55;color:var(--ink-body);font-weight:300}
  .status-items li::before{content:"\25B8";position:absolute;left:0;top:.4rem;color:var(--cyan-dim);font-size:.75rem}
  .status-items li strong{color:var(--ink);font-weight:500}
  .status-items li code{font-family:'JetBrains Mono',monospace;font-size:.78rem;background:rgba(0,240,255,0.08);padding:.05rem .3rem;color:var(--cyan);border-radius:2px}

  /* FOUNDER */
  .founder-letter{max-width:64ch;margin:0 auto;padding:2rem 0}
  .founder-letter p{font-size:1.05rem;line-height:1.85;color:var(--ink-body);margin-bottom:1.3rem;font-weight:300}
  .founder-letter p strong{color:var(--sun-1);font-weight:500;text-shadow:0 0 5px var(--sun-2)}
  .founder-pullquote{font-family:'Monoton',cursive;font-size:clamp(1.2rem,2.2vw,1.7rem);color:var(--cyan);text-shadow:0 0 10px var(--cyan-dim);letter-spacing:.04em;line-height:1.2;padding:1.5rem 0 1.5rem 1.5rem;margin:2rem -1.5rem 2rem -1.5rem;border-left:3px solid var(--magenta);background:linear-gradient(90deg,rgba(255,45,149,0.06),transparent 70%)}
  .signature{margin-top:2.5rem;font-family:'Monoton',cursive;font-size:2rem;letter-spacing:.1em;color:var(--sun-1);text-shadow:0 0 12px var(--sun-2);text-align:right}

  footer{padding:3rem 2rem 2rem;border-top:1px solid rgba(0,240,255,0.15);display:grid;grid-template-columns:1fr auto;gap:1rem;align-items:center;font-family:'JetBrains Mono',monospace;font-size:.7rem;letter-spacing:.15em;color:var(--ink-dim);text-transform:uppercase}
  footer .brand{color:var(--sun-2)}
  @media(max-width:600px){footer{grid-template-columns:1fr;text-align:center}}

  .reveal{opacity:0;transform:translateY(20px);transition:opacity .7s ease,transform .7s ease}
  .reveal.in{opacity:1;transform:translateY(0)}
</style>
</head>
<body>

<nav>
  <a href="/" class="logo">TINY\u00B7HUB</a>
  <ul class="nav-links">
    <li><a href="/about" class="active">About</a></li>
    <li><a href="/how-it-works">How It Works</a></li>
    <li><a href="/suppliers">Suppliers</a></li>
    <li><a href="/consumers">Consumers</a></li>
    <li><a href="/investors">Investors</a></li>
    <li><a href="/dashboard">Live Demo \u2192</a></li>
  </ul>
</nav>

<section class="page-hero">
  <div class="atmosphere"></div>
  <div class="sun-wrap">
    <svg viewBox="0 0 200 100" preserveAspectRatio="xMidYMax meet" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs>
        <linearGradient id="sunBands" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#fff07a"/>
          <stop offset="15%" stop-color="#ffe54a"/>
          <stop offset="35%" stop-color="#ffcc00"/>
          <stop offset="60%" stop-color="#ff9500"/>
          <stop offset="82%" stop-color="#ff5500"/>
          <stop offset="100%" stop-color="#c72c00"/>
        </linearGradient>
        <clipPath id="domeClip"><path d="M 0,100 A 100,100 0 0 1 200,100 Z"/></clipPath>
      </defs>
      <g clip-path="url(#domeClip)">
        <rect x="0" y="0" width="200" height="100" fill="url(#sunBands)"/>
        <rect x="0" y="16" width="200" height="2" fill="#000"/>
        <rect x="0" y="32" width="200" height="2.5" fill="#000"/>
        <rect x="0" y="48" width="200" height="3" fill="#000"/>
        <rect x="0" y="64" width="200" height="3.5" fill="#000"/>
        <rect x="0" y="80" width="200" height="4.5" fill="#000"/>
        <rect x="0" y="93" width="200" height="3" fill="#000"/>
      </g>
    </svg>
  </div>
  <div class="horizon"></div>
  <div class="grid-wrap"><div class="grid-floor"></div></div>
  <div class="grid-mask"></div>
</section>

<main>

  <section class="block reveal">
    <div class="chapter-marker">01</div>
    <h2 class="section-title">01. Mission</h2>
    <div class="mission-banner">
      <div class="mission-words">
        <span class="w w1">GENERATE</span>
        <span class="w w2">SHARE</span>
        <span class="w w3">PROFIT</span>
      </div>
      <div class="mission-statement-block">
        <p>Providing grid upgrades for the future of energy through an affordable, sustainable, and transparent marketplace where communities generate, share, and profit from their own power.</p>
      </div>
    </div>
  </section>

  <section class="block reveal">
    <div class="chapter-marker">02</div>
    <h2 class="section-title">02. The Problem</h2>
    <p class="problem-intro">The grid was built to move power one way, from centralized plants to passive customers. <strong>That model is breaking down.</strong> Data centers are driving record load growth, old generation is retiring, and severe weather is straining infrastructure that was never designed for any of it. To cover the gap, utilities are raising rates faster than their customers can absorb them.</p>

    <div class="stat-row">
      <div class="stat"><div class="stat-num">\u22482x</div><div class="stat-label">Ameren Rate<br>5-Year Rise</div></div>
      <div class="stat"><div class="stat-num">$606M</div><div class="stat-label">ComEd Delivery<br>Rate Hike</div></div>
      <div class="stat"><div class="stat-num">1,000%+</div><div class="stat-label">PJM Capacity<br>Price Surge</div></div>
      <div class="stat"><div class="stat-num">22x</div><div class="stat-label">MISO Auction<br>Price Spike</div></div>
    </div>

    <div class="problem-sub">
      <h3>Ratepayers are financing a grid they barely use</h3>
      <p>Illinois rates have climbed sharply. Ameren residential rates have nearly doubled over five years, reaching around 15.5\u00A2/kWh. ComEd just secured a $606M delivery rate increase. On a typical bill, nearly half the charges cover delivery. That's the cost of moving electrons across aging wire, not producing them.</p>
      <p>If your neighbor's rooftop solar powers your EV 500 feet away, you still pay the utility a toll for the trip. ComEd charges about $0.02/kWh for this. Ameren charges $0.025/kWh. Neighborhoods are subsidizing a long-distance grid they aren't using.</p>
    </div>

    <div class="problem-sub">
      <h3>The grid is running out of capacity</h3>
      <p>PJM's most recent capacity auction cleared at a record $333.44/MW-day, up from $28.92. That's more than a 1,000% increase against a 6,625 MW reliability shortfall. Ninety-four percent of the new load growth is data centers. MISO's auction followed a similar path. Prices jumped from $30 to $666.50/MW-day, a 22x spike. State agencies are warning that parts of Illinois could face mandated load shedding, meaning rolling blackouts, as early as 2031.</p>
    </div>

    <div class="problem-sub">
      <h3>Local capital is leaving the neighborhood</h3>
      <p>A typical Illinois community with a few thousand homes consumes hundreds of thousands of megawatt-hours per year. At current delivery tolls, millions of dollars flow out of that community annually in wheeling fees alone. That's capital that could be circulating between local producers and local buyers. Instead, it's extracted to pay corporate dividends several states away.</p>
    </div>

    <div class="problem-sub">
      <h3>The hardware that could fix this is already installed</h3>
      <p>Most neighborhoods are already sitting on thousands of EV batteries capable of acting as a virtual power plant. They're mostly idle. Inverter manufacturers like Enphase, SolarEdge, and Tesla treat the hardware their customers own as proprietary. High-frequency polling triggers rate limits or outright bans. A single policy change from a manufacturer can shut down an entire distributed sensor network overnight.</p>
      <p>Utility data infrastructure has the same problem in reverse. Grid prices update every five minutes. The standard Green Button API delivers 15-minute interval data in trailing 24 to 48 hour batches. You can't balance a real-time grid with two-day-old data, and you can't optimize a home battery without knowing what it costs to discharge it.</p>
    </div>

    <div class="problem-close">
      The grid needs a coordination layer that's open, real-time, and hardware-agnostic. One that routes power by physics and economics rather than by monopoly, treats local generation as the asset it is, and keeps value circulating inside the communities producing it. <strong>That's what we're building.</strong>
    </div>
  </section>

  <section class="block reveal">
    <div class="chapter-marker">03</div>
    <h2 class="section-title">03. Thesis</h2>

    <div class="thesis-intro">
      <p>The energy conversation for the last decade has mostly been about generation. How do we make more clean power? Solar, wind, batteries, nuclear, all of it.</p>
      <p>That's not actually the hard part anymore. We're already putting solar panels on roofs and batteries in garages faster than the grid knows what to do with them. The assets that could stabilize the grid are already here. They're just sitting idle. <strong>The real problem is routing and settlement.</strong></p>
    </div>

    <div class="thesis-hook">Tiny-Hub isn't a solar app.<br>It's a routing engine.</div>

    <div class="thesis-intro">
      <p>We don't look at the grid like a public utility. We look at it like the worst logistics network in the country. Power gets hauled long distances, tolled at every junction, and priced by rules that were written before anyone had solar on their roof. We're rebuilding the routing from the ground up around four things the incumbents are ignoring.</p>
    </div>

    <div class="thesis-grid">
      <div class="thesis-card">
        <div class="thesis-card-num">01</div>
        <div class="thesis-card-title">Short trips beat long trips</div>
        <div class="thesis-card-body">If your roof makes an extra kilowatt, the most efficient place for it to go is the neighbor three doors down. ComEd takes your surplus for pennies, sells it to your neighbor at a premium, and slaps a delivery toll on both of you for power that never left the block.</div>
        <div class="thesis-take"><strong>Our take:</strong> Distance is an economic penalty. Peer-to-peer spatial matching inside tight zones (under 5 km). Money stays in the neighborhood.</div>
      </div>
      <div class="thesis-card">
        <div class="thesis-card-num">02</div>
        <div class="thesis-card-title">Real-time grid needs real-time settlement</div>
        <div class="thesis-card-body">Grid prices update every 5 minutes. Green Button delivers 15-minute data on a 24 to 48 hour delay. You can't balance a fast-moving grid with a spreadsheet that shows up two days late.</div>
        <div class="thesis-take"><strong>Our take:</strong> We pull live inverter data, match as it happens, settle in 5-minute batches. Utility data becomes a backup check, not the system of record.</div>
      </div>
      <div class="thesis-card">
        <div class="thesis-card-num">03</div>
        <div class="thesis-card-title">The sensor layer has to be uncensorable</div>
        <div class="thesis-card-body">Hardware companies like Tesla, Enphase, and SolarEdge want to be the next utility monopolies. They lock data inside proprietary clouds. A grid that needs permission from three corporations to balance a street is built to fail.</div>
        <div class="thesis-take"><strong>Our take:</strong> $35 CT clamps in the breaker box as a first-class path. Hardware backdoor around every walled garden. Data belongs to the homeowner.</div>
      </div>
      <div class="thesis-card">
        <div class="thesis-card-num">04</div>
        <div class="thesis-card-title">Stop wearing out batteries for free</div>
        <div class="thesis-card-body">Standard demand-response drains home batteries upstream without accounting for wear. Every discharge costs the owner about $15/MWh in hardware degradation. Utility programs quietly take that from the homeowner.</div>
        <div class="thesis-take"><strong>Our take:</strong> Our dispatch never discharges unless profit beats wear cost. We don't burn up your hardware to save the utility.</div>
      </div>
    </div>

    <div class="thesis-close">
      <h4>// The Bottom Line</h4>
      <p>The legacy grid is a one-way street: power flows down, and local capital flows out. We have zero interest in building polite software for incumbent monopolies, and we aren't asking for their permission.</p>
      <p>Using federal preemption (FERC Order 2222) as our legal shield, we've built an invisible, parallel routing layer that simply goes right under them. It renders their local tollbooths structurally and mathematically obsolete.</p>
      <p><strong>The infrastructure is live and the grid math is solved. Now we go.</strong></p>
    </div>
  </section>

  <section class="block reveal">
    <div class="chapter-marker">04</div>
    <h2 class="section-title">04. Where We Are Now</h2>

    <div class="status-grid">
      <div class="status-card">
        <div class="status-card-head"><div class="status-card-title">Platform</div><div class="status-dot">LIVE</div></div>
        <ul class="status-items">
          <li>Public site at <strong>tinyhub.energy</strong>, deployed on Google Cloud Run with CI/CD from <code>tinyhub-cicd</code></li>
          <li>Full GCP enterprise org: separate projects for platform, data, and blockchain with isolated IAM</li>
          <li>Real-time dashboard with WebSocket/SSE, matching engine, REST API live</li>
        </ul>
      </div>
      <div class="status-card">
        <div class="status-card-head"><div class="status-card-title">Data</div><div class="status-dot">LIVE</div></div>
        <ul class="status-items">
          <li><strong>District 91</strong> (Ameren / MISO) fully mapped as a digital twin</li>
          <li>PostGIS spatial proximity matching + Open-Meteo DNI + MISO LMP</li>
          <li>Green Button ingestion with optimistic settlement (works around 24-48h data delay)</li>
          <li>Pub/Sub topics + BigQuery pipelines for real-time grid events</li>
        </ul>
      </div>
      <div class="status-card">
        <div class="status-card-head"><div class="status-card-title">Blockchain</div><div class="status-dot">LIVE</div></div>
        <ul class="status-items">
          <li>Smart contracts deployed on <strong>Arbitrum Sepolia</strong> (L2): TinyHubMarket + TinyHubToken</li>
          <li>Batch settler with optimistic aggregation, ~95% gas savings vs per-trade</li>
          <li>Cloud KMS wallets, Firestore identity, Firebase Auth</li>
          <li>ERC-4337 account abstraction via managed Pimlico / Biconomy</li>
        </ul>
      </div>
      <div class="status-card">
        <div class="status-card-head"><div class="status-card-title">Hardware</div><div class="status-dot">LIVE</div></div>
        <ul class="status-items">
          <li>Open-standard CT clamp path ($35 Shelly EM / Emporia Vue via MQTT)</li>
          <li>Tesla Fleet API integration scoped for V2H and Powershare</li>
          <li>Hardware-agnostic by design: bypasses OEM walled gardens</li>
        </ul>
      </div>
      <div class="status-card">
        <div class="status-card-head"><div class="status-card-title">Legal</div><div class="status-dot">LIVE</div></div>
        <ul class="status-items">
          <li>FERC Order 2222 as federal preemption shield over state ARES classification</li>
          <li>Deferred-fee counsel strategy with target firms (Cooley, Fenwick)</li>
          <li>Shadow market backtest architected as primary investor proof-of-economics</li>
        </ul>
      </div>
      <div class="status-card">
        <div class="status-card-head"><div class="status-card-title">What's Next</div><div class="status-dot next">UPCOMING</div></div>
        <ul class="status-items">
          <li>Illinois pilot deployment within Ameren / MISO territory</li>
          <li>30-day shadow market backtest on D91 live data</li>
          <li><strong>$2M seed raise</strong> to fund the pilot and first hires</li>
        </ul>
      </div>
    </div>
  </section>

  <section class="block reveal">
    <div class="chapter-marker">05</div>
    <h2 class="section-title">05. Founder Note</h2>

    <div class="founder-letter">
      <p>I grew up in a small town. That's not a line in a pitch deck. It's the whole reason Tiny-Hub exists.</p>

      <p>When Walmart came to small towns in the 80s and 90s, the local hardware stores, pharmacies, and grocers closed one by one. Amazon came for retail after that and finished the job. Every time, the pattern was the same: a larger player operated at a scale the local businesses couldn't match, captured the value that used to circulate locally, and permanently extracted it to somewhere else. The communities that lost the most had the least say in the decision.</p>

      <div class="founder-pullquote">The electrical grid is the next version of this story, and it's already underway.</div>

      <p>My background is in logistics and sales. I spent years inside trucking and rail, which is really just the business of moving valuable things long distances through rigid systems that demand their cut at every stage. Then I spent years in sales, learning how to actually talk to the people on both ends of those systems. The ones writing the checks and the ones absorbing the cost. Somewhere in between, I got hooked on data. Not dashboards for the sake of dashboards, but finding the real story hiding inside a messy spreadsheet and engineering a way to fix it.</p>

      <div class="founder-pullquote">The electrical grid is the largest logistics system in the country.</div>

      <p>And right now, it's running on the exact same extractive pattern that hollowed out Main Street. Long distances, opaque pricing, monopoly tolls at every junction, and almost no way for a local community to participate in the value it produces. Illinois ratepayers are financing a macro-grid they barely use. Rooftops and home batteries worth billions sit idle because the hardware is locked down by corporate gatekeepers and the utility data is two days late.</p>

      <p>I started building Tiny-Hub because the tools finally caught up to the problem. Google Cloud, Arbitrum, modern AI. Stack them right, and a single person can build the infrastructure that would have required a team of fifty just five years ago. That's not a flex; it's the point. If a small team can build grid-scale coordination, then the grid doesn't have to belong to the monopolies anymore. It can belong to the communities it serves.</p>

      <p>That's what I'm doing here. Building the coordination layer that lets neighbors generate, share, and profit from their own power. Keeping the economic value exactly where it's produced. Giving small communities a seat at a table they've historically paid for, but never been allowed to sit at.</p>

      <p><strong>Great moments are born from great opportunity. I'd rather spend the next decade of my life trying to get this right so that the communities I grew up in benefit from innovation for once.</strong></p>

      <div class="signature">\u2014 Cole</div>
    </div>
  </section>

</main>

<footer>
  <div><span class="brand">TINY\u00B7HUB ENERGY</span> \u00A0//\u00A0 Upgrading the grid, one neighborhood at a time.</div>
  <div>\u00A9 2026 // tinyhub.energy</div>
</footer>

<script>
  const io = new IntersectionObserver(
    es => es.forEach(e => e.isIntersecting && e.target.classList.add('in')),
    {threshold:0.08}
  );
  document.querySelectorAll('.reveal').forEach(el => io.observe(el));
</script>
</body>
</html>
'''

Path("templates/about.html").write_text(about_html)
print(f"[OK] templates/about.html rewritten ({len(about_html)} bytes)")

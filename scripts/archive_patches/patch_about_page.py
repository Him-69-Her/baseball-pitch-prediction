#!/usr/bin/env python3
"""Build /about page with all 5 sections locked in."""
from pathlib import Path

# ────────────────────────────────────────────────────────────
# 1) Create templates/about.html
# ────────────────────────────────────────────────────────────
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
    --bg:#000;
    --cyan:#00f0ff;
    --cyan-dim:#00b8c7;
    --magenta:#ff2d95;
    --sun-1:#ffcc00;
    --sun-2:#ff9500;
    --sun-3:#ff5500;
    --sun-4:#c72c00;
    --ink:#e6f8ff;
    --ink-dim:#7ba9b3;
    --ink-body:#cdd8db;
  }
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{background:var(--bg);color:var(--ink);font-family:'Inter',sans-serif;overflow-x:hidden}

  /* CRT scanlines overlay */
  body::before{
    content:"";position:fixed;inset:0;pointer-events:none;z-index:999;
    background:repeating-linear-gradient(to bottom,
      rgba(0,0,0,0) 0,
      rgba(0,0,0,0) 2px,
      rgba(0,0,0,0.15) 3px,
      rgba(0,0,0,0) 4px);
    mix-blend-mode:multiply;
  }

  /* ─── NAV ──────────────────────────────── */
  nav{
    position:fixed;top:0;left:0;right:0;z-index:50;
    display:flex;justify-content:space-between;align-items:center;
    padding:1.2rem 2rem;
    background:linear-gradient(to bottom, rgba(0,0,0,0.95) 0%, rgba(0,0,0,0.75) 70%, transparent);
    border-bottom:1px solid rgba(0,240,255,0.15);
    backdrop-filter:blur(6px);
  }
  .logo{
    font-family:'Monoton',cursive;font-size:1.6rem;letter-spacing:.15em;
    color:var(--sun-1);text-decoration:none;
    text-shadow:0 0 8px var(--sun-2),0 0 24px var(--sun-3);
  }
  .nav-links{display:flex;gap:1.4rem;list-style:none;flex-wrap:wrap;justify-content:flex-end}
  .nav-links a{
    color:var(--cyan);text-decoration:none;font-size:.7rem;letter-spacing:.18em;
    text-transform:uppercase;transition:all .2s;
    text-shadow:0 0 4px var(--cyan-dim);white-space:nowrap;
    font-family:'JetBrains Mono',monospace;
  }
  .nav-links a:hover{color:var(--magenta);text-shadow:0 0 8px var(--magenta)}
  .nav-links a.active{color:var(--sun-1);text-shadow:0 0 8px var(--sun-2)}

  /* ─── HERO (compact) ──────────────────── */
  .page-hero{
    position:relative;height:48vh;min-height:340px;overflow:hidden;
    display:flex;flex-direction:column;justify-content:flex-end;align-items:center;
    padding-bottom:4rem;
  }
  .atmosphere{
    position:absolute;left:0;right:0;bottom:50%;height:50%;
    z-index:1;pointer-events:none;
    background:
      radial-gradient(ellipse 50% 70% at 50% 100%,
        rgba(255,204,0,0.35) 0%,
        rgba(255,149,0,0.22) 20%,
        rgba(255,85,0,0.12) 45%,
        transparent 70%),
      linear-gradient(to top,
        rgba(255,149,0,0.25) 0%,
        rgba(255,85,0,0.14) 25%,
        rgba(199,44,0,0.08) 50%,
        transparent 100%);
    filter:blur(4px);
    animation:atmos-breathe 8s ease-in-out infinite;
  }
  @keyframes atmos-breathe{0%,100%{opacity:.85}50%{opacity:1}}

  .sun-wrap{
    position:absolute;bottom:50%;left:50%;
    width:min(400px,40vw);aspect-ratio:2/1;
    z-index:3;pointer-events:none;
    transform:translateX(-50%);
    animation:sun-breathe 5s ease-in-out infinite;
  }
  .sun-wrap svg{width:100%;height:100%;display:block;overflow:visible;
    filter:drop-shadow(0 0 10px rgba(255,149,0,0.55));}
  @keyframes sun-breathe{
    0%,100%{transform:translateX(-50%) scale(1)}
    50%{transform:translateX(-50%) scale(1.02)}
  }

  .horizon{
    position:absolute;bottom:50%;left:0;right:0;height:2px;z-index:4;
    background:linear-gradient(to right, transparent, var(--cyan) 15%, var(--cyan) 85%, transparent);
    box-shadow:0 0 12px var(--cyan), 0 0 32px var(--cyan), 0 0 60px rgba(0,240,255,0.5);
  }

  .grid-wrap{
    position:absolute;bottom:0;left:0;right:0;height:50%;
    perspective:400px;perspective-origin:50% 0%;
    z-index:2;pointer-events:none;overflow:hidden;
  }
  .grid-floor{
    position:absolute;bottom:0;left:-50%;width:200%;height:100%;
    background-image:
      linear-gradient(to right, var(--cyan) 2px, transparent 2px),
      linear-gradient(to bottom, var(--cyan) 2px, transparent 2px);
    background-size:80px 80px;
    transform:rotateX(70deg);transform-origin:50% 100%;
    animation:grid-scroll 6s linear infinite;
    filter:drop-shadow(0 0 6px var(--cyan));
    opacity:.85;
  }
  @keyframes grid-scroll{
    0%{background-position:0 0}
    100%{background-position:0 80px}
  }
  .grid-mask{
    position:absolute;bottom:0;left:0;right:0;height:50%;pointer-events:none;z-index:3;
    background:linear-gradient(to top, transparent 0%, transparent 40%, rgba(0,0,0,0.6) 80%, #000 100%);
  }

  .page-title-wrap{
    position:relative;z-index:6;text-align:center;
  }
  .page-eyebrow{
    font-family:'JetBrains Mono',monospace;
    font-size:.72rem;letter-spacing:.4em;color:var(--cyan);
    text-transform:uppercase;text-shadow:0 0 6px var(--cyan-dim);
    margin-bottom:.8rem;
  }
  .page-title{
    font-family:'Monoton',cursive;
    font-size:clamp(2.2rem,6vw,4.8rem);
    letter-spacing:.08em;color:var(--sun-1);
    text-shadow:0 0 12px var(--sun-2),0 0 28px var(--sun-3);
  }

  /* ─── CONTENT ─────────────────────────── */
  main{max-width:820px;margin:0 auto;padding:5rem 1.5rem 6rem;position:relative;z-index:2}

  section.block{margin-bottom:5rem;position:relative}
  section.block:last-child{margin-bottom:0}

  /* Section divider: corner-cut neon box */
  .section-head{
    border-left:2px solid var(--cyan);
    padding:.2rem 0 .2rem 1.2rem;
    margin-bottom:2rem;
    position:relative;
  }
  .section-head::before{
    content:"";position:absolute;left:-2px;top:-6px;width:12px;height:2px;background:var(--cyan);
    box-shadow:0 0 6px var(--cyan);
  }
  .section-head::after{
    content:"";position:absolute;left:-2px;bottom:-6px;width:12px;height:2px;background:var(--cyan);
    box-shadow:0 0 6px var(--cyan);
  }
  .section-num{
    font-family:'JetBrains Mono',monospace;
    font-size:.7rem;letter-spacing:.35em;color:var(--magenta);
    text-shadow:0 0 6px var(--magenta);
    text-transform:uppercase;display:block;margin-bottom:.3rem;
  }
  .section-title{
    font-family:'Monoton',cursive;
    font-size:clamp(1.8rem,3.8vw,2.6rem);
    color:var(--cyan);letter-spacing:.04em;
    text-shadow:0 0 10px var(--cyan-dim);
  }

  .prose p{
    font-size:1.05rem;line-height:1.75;color:var(--ink-body);
    margin-bottom:1.2rem;font-weight:300;
  }
  .prose p strong{color:var(--ink);font-weight:500}
  .prose h3{
    font-family:'JetBrains Mono',monospace;
    font-size:.95rem;letter-spacing:.12em;text-transform:uppercase;
    color:var(--sun-1);text-shadow:0 0 6px var(--sun-2);
    margin:2.2rem 0 .9rem;font-weight:700;
  }

  /* Mission callout */
  .mission-box{
    border:1px solid var(--sun-2);
    padding:2rem 1.8rem;
    background:
      radial-gradient(ellipse at 50% 100%, rgba(255,149,0,0.12), transparent 70%),
      linear-gradient(135deg, rgba(255,204,0,0.04), rgba(255,85,0,0.02));
    position:relative;
  }
  .mission-box::before{
    content:"";position:absolute;top:-1px;left:-1px;width:24px;height:24px;
    border-top:2px solid var(--sun-1);border-left:2px solid var(--sun-1);
  }
  .mission-box::after{
    content:"";position:absolute;bottom:-1px;right:-1px;width:24px;height:24px;
    border-bottom:2px solid var(--sun-1);border-right:2px solid var(--sun-1);
  }
  .mission-statement{
    font-family:'Inter',sans-serif;
    font-size:clamp(1.1rem,1.8vw,1.35rem);
    line-height:1.65;color:var(--ink);font-weight:400;
    letter-spacing:.01em;
  }

  /* Thesis principle cards */
  .thesis-card{
    border-left:2px solid var(--magenta);
    padding:1.2rem 0 .4rem 1.4rem;
    margin:1.8rem 0;
  }
  .thesis-card-title{
    font-family:'JetBrains Mono',monospace;
    font-size:1rem;font-weight:700;letter-spacing:.05em;
    color:var(--sun-1);text-shadow:0 0 6px var(--sun-2);
    margin-bottom:.8rem;
  }
  .thesis-take{
    margin-top:.8rem;padding:.8rem 1rem;
    background:rgba(0,240,255,0.04);
    border:1px solid rgba(0,240,255,0.18);
    font-size:.95rem;line-height:1.6;color:var(--ink-body);
  }
  .thesis-take strong{color:var(--cyan);font-weight:600}

  .bottom-line{
    margin-top:2.5rem;padding-top:2rem;
    border-top:1px solid rgba(0,240,255,0.2);
  }
  .bottom-line h3{color:var(--magenta);text-shadow:0 0 6px var(--magenta)}

  /* Timeline-style Where We Are Now */
  .timeline-group{margin-bottom:2rem}
  .timeline-label{
    font-family:'JetBrains Mono',monospace;
    font-size:.8rem;letter-spacing:.2em;text-transform:uppercase;
    color:var(--sun-1);text-shadow:0 0 6px var(--sun-2);
    margin-bottom:.8rem;
    display:flex;align-items:center;gap:.8rem;
  }
  .timeline-label::after{
    content:"";flex:1;height:1px;
    background:linear-gradient(to right, var(--sun-2), transparent);
  }
  .timeline-items{list-style:none;padding-left:0}
  .timeline-items li{
    position:relative;padding:.4rem 0 .4rem 1.4rem;
    font-size:.98rem;line-height:1.6;color:var(--ink-body);
  }
  .timeline-items li::before{
    content:"▸";position:absolute;left:0;top:.45rem;
    color:var(--cyan);font-size:.85rem;text-shadow:0 0 4px var(--cyan-dim);
  }
  .timeline-items li strong{color:var(--ink);font-weight:500}

  /* Founder note signature */
  .signature{
    margin-top:2rem;
    font-family:'Monoton',cursive;
    font-size:1.6rem;letter-spacing:.1em;
    color:var(--sun-1);text-shadow:0 0 10px var(--sun-2);
  }

  /* ─── FOOTER ─────────────────────────── */
  footer{
    padding:3rem 2rem 2rem;border-top:1px solid rgba(0,240,255,0.15);
    display:grid;grid-template-columns:1fr auto;gap:1rem;align-items:center;
    font-family:'JetBrains Mono',monospace;
    font-size:.7rem;letter-spacing:.15em;color:var(--ink-dim);text-transform:uppercase;
  }
  footer .brand{color:var(--sun-2)}
  @media (max-width:600px){footer{grid-template-columns:1fr;text-align:center}}

  /* ─── Reveal on scroll ───────────────── */
  .reveal{opacity:0;transform:translateY(20px);transition:opacity .7s ease,transform .7s ease}
  .reveal.in{opacity:1;transform:translateY(0)}
</style>
</head>
<body>

<nav>
  <a href="/" class="logo">TINY·HUB</a>
  <ul class="nav-links">
    <li><a href="/about" class="active">About</a></li>
    <li><a href="/how-it-works">How It Works</a></li>
    <li><a href="/suppliers">Suppliers</a></li>
    <li><a href="/consumers">Consumers</a></li>
    <li><a href="/investors">Investors</a></li>
    <li><a href="/dashboard">Live Demo →</a></li>
  </ul>
</nav>

<!-- ─── HERO ─── -->
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
        <clipPath id="domeClip">
          <path d="M 0,100 A 100,100 0 0 1 200,100 Z"/>
        </clipPath>
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

  <div class="page-title-wrap">
    <div class="page-eyebrow">// About Tiny-Hub</div>
    <h1 class="page-title">Our Story</h1>
  </div>
</section>

<main>

  <!-- ─── MISSION ─── -->
  <section class="block reveal">
    <div class="section-head">
      <span class="section-num">01 // Mission</span>
      <h2 class="section-title">Why We Exist</h2>
    </div>
    <div class="mission-box">
      <p class="mission-statement">
        Providing grid upgrades for the future of energy through an affordable, sustainable, and transparent marketplace where communities generate, share, and profit from their own power.
      </p>
    </div>
  </section>

  <!-- ─── THE PROBLEM ─── -->
  <section class="block reveal">
    <div class="section-head">
      <span class="section-num">02 // The Problem</span>
      <h2 class="section-title">The Grid Is Broken</h2>
    </div>
    <div class="prose">
      <p>
        The grid was built to move power one way, from centralized plants to passive customers. That model is breaking down. Data centers are driving record load growth, old generation is retiring, and severe weather is straining infrastructure that was never designed for any of it. To cover the gap, utilities are raising rates faster than their customers can absorb them.
      </p>
      <p>
        The result is a system where you pay more for worse service, and the rooftops and batteries that could actually help are locked out.
      </p>

      <h3>Ratepayers are financing a grid they barely use</h3>
      <p>
        Illinois rates have climbed sharply. Ameren residential rates have nearly doubled over five years, reaching around 15.5¢/kWh. ComEd just secured a $606M delivery rate increase. On a typical bill, nearly half the charges cover delivery. That's the cost of moving electrons across aging wire, not producing them.
      </p>
      <p>
        If your neighbor's rooftop solar powers your EV 500 feet away, you still pay the utility a toll for the trip. ComEd charges about $0.02/kWh for this. Ameren charges $0.025/kWh. Neighborhoods are subsidizing a long-distance grid they aren't using.
      </p>

      <h3>The grid is running out of capacity</h3>
      <p>
        PJM's most recent capacity auction cleared at a record $333.44/MW-day, up from $28.92. That's more than a 1,000% increase against a 6,625 MW reliability shortfall. Ninety-four percent of the new load growth is data centers. MISO's auction followed a similar path. Prices jumped from $30 to $666.50/MW-day, a 22x spike. State agencies are warning that parts of Illinois could face mandated load shedding, meaning rolling blackouts, as early as 2031.
      </p>

      <h3>Local capital is leaving the neighborhood</h3>
      <p>
        A typical Illinois community with a few thousand homes consumes hundreds of thousands of megawatt-hours per year. At current delivery tolls, millions of dollars flow out of that community annually in wheeling fees alone. That's capital that could be circulating between local producers and local buyers. Instead, it's extracted to pay corporate dividends several states away.
      </p>

      <h3>The hardware that could fix this is already installed</h3>
      <p>
        Most neighborhoods are already sitting on thousands of EV batteries capable of acting as a virtual power plant. They're mostly idle. Inverter manufacturers like Enphase, SolarEdge, and Tesla treat the hardware their customers own as proprietary. High-frequency polling triggers rate limits or outright bans. A single policy change from a manufacturer can shut down an entire distributed sensor network overnight.
      </p>
      <p>
        Utility data infrastructure has the same problem in reverse. Grid prices update every five minutes. The standard Green Button API delivers 15-minute interval data in trailing 24 to 48 hour batches. You can't balance a real-time grid with two-day-old data, and you can't optimize a home battery without knowing what it costs to discharge it. Most utility demand-response programs just pull power from residential batteries without accounting for hardware wear, which quietly loses the homeowner money every cycle.
      </p>

      <h3>What needs to exist</h3>
      <p>
        The grid needs a coordination layer that's open, real-time, and hardware-agnostic. One that routes power by physics and economics rather than by monopoly, treats local generation as the asset it is, and keeps value circulating inside the communities producing it.
      </p>
      <p><strong>That's what we're building.</strong></p>
    </div>
  </section>

  <!-- ─── THESIS ─── -->
  <section class="block reveal">
    <div class="section-head">
      <span class="section-num">03 // Thesis</span>
      <h2 class="section-title">The Grid Is a Routing Problem</h2>
    </div>
    <div class="prose">
      <p>
        The energy conversation for the last decade has mostly been about generation. How do we make more clean power? Solar, wind, batteries, nuclear, all of it.
      </p>
      <p>
        That's not actually the hard part anymore. We're already putting solar panels on roofs and batteries in garages faster than the grid knows what to do with them. The assets that could stabilize the grid are already here. They're just sitting idle.
      </p>
      <p><strong>The real problem is routing and settlement.</strong></p>
      <p>
        Most energy startups are fighting the wrong war. They build apps that gamify solar production, or they bundle home batteries into programs that prop up failing utilities. They treat the monopoly grid as a permanent fact of life and build polite software on top of it.
      </p>
      <p>
        <strong>Tiny-Hub isn't a solar app. It's a routing engine.</strong>
      </p>
      <p>
        We don't look at the grid like a public utility. We look at it like the worst logistics network in the country. Power gets hauled long distances, tolled at every junction, and priced by rules that were written before anyone had solar on their roof. We're rebuilding the routing from the ground up around four things the incumbents are ignoring:
      </p>

      <div class="thesis-card">
        <div class="thesis-card-title">1 // Short trips beat long trips</div>
        <p>
          If your roof makes an extra kilowatt, the most efficient place for it to go is the neighbor three doors down who is getting gouged by ComEd pricing. Physics agrees. The grid rules don't. Right now, that local transaction is forced up into the regional grid and back down. ComEd takes your surplus for pennies, sells it to your neighbor at a premium, and slaps a delivery toll on both of you for power that never actually left the block.
        </p>
        <div class="thesis-take">
          <strong>Our take:</strong> Distance is an economic penalty. Our matching engine uses a spatial database to route power laterally, peer-to-peer, inside tight zones (under 5 km). Shorter trips mean less line loss, no macro-grid toll, and the money stays in the neighborhood.
        </div>
      </div>

      <div class="thesis-card">
        <div class="thesis-card-title">2 // A real-time grid needs real-time settlement</div>
        <p>
          Grid prices update every 5 minutes. But the standard utility data pipeline (Green Button API) delivers 15-minute data on a 24 to 48 hour delay. You can't balance a fast-moving grid with a spreadsheet that shows up two days late.
        </p>
        <div class="thesis-take">
          <strong>Our take:</strong> If the physics is fast, the money has to move fast. We pull live data straight from the inverters, match trades as they happen, and settle in 5-minute batches. The utility's delayed data becomes a backup check, not the system of record.
        </div>
      </div>

      <div class="thesis-card">
        <div class="thesis-card-title">3 // The sensor layer has to be uncensorable</div>
        <p>
          Hardware companies like Tesla, Enphase, and SolarEdge want to be the next utility monopolies. They lock customer data inside their own clouds and rate-limit anyone trying to read it. A local grid that needs permission from three corporations to balance a single street is built to fail.
        </p>
        <div class="thesis-take">
          <strong>Our take:</strong> The sensors have to be ours. We plug $35 CT clamps directly into the breaker box as a first-class path. It's a hardware backdoor around every walled garden. The data belongs to the homeowner. The routing belongs to the protocol.
        </div>
      </div>

      <div class="thesis-card">
        <div class="thesis-card-title">4 // Stop wearing out people's batteries for free</div>
        <p>
          Standard utility demand-response programs just drain home batteries upstream when the grid is under stress. They don't account for wear. Every time a lithium battery discharges, it costs the owner about $15 per MWh in actual hardware degradation. Utility programs quietly take that from the homeowner and call it a favor.
        </p>
        <div class="thesis-take">
          <strong>Our take:</strong> Economics comes first. Our dispatch logic never discharges a battery unless the local profit beats the physical wear cost. We don't burn up your hardware to save the utility. We use it to make you money.
        </div>
      </div>

      <div class="bottom-line">
        <h3>The bottom line</h3>
        <p>
          The legacy grid is a one-way street: power flows down, and local capital flows out. We have zero interest in building polite software for incumbent monopolies, and we aren't asking for their permission.
        </p>
        <p>
          Using federal preemption (FERC Order 2222) as our legal shield, we've built an invisible, parallel routing layer that simply goes right under them. It renders their local tollbooths structurally and mathematically obsolete.
        </p>
        <p><strong>The infrastructure is live and the grid math is solved. Now we go.</strong></p>
      </div>
    </div>
  </section>

  <!-- ─── WHERE WE ARE NOW ─── -->
  <section class="block reveal">
    <div class="section-head">
      <span class="section-num">04 // Where We Are Now</span>
      <h2 class="section-title">What's Built</h2>
    </div>

    <div class="timeline-group">
      <div class="timeline-label">Platform</div>
      <ul class="timeline-items">
        <li>Live public site at <strong>tinyhub.energy</strong>, deployed on Google Cloud Run with CI/CD running out of a dedicated <code>tinyhub-cicd</code> project</li>
        <li>Full GCP enterprise organization structure built out: separate projects for platform, data, and blockchain, each with isolation policies and dedicated service accounts</li>
        <li>Real-time dashboard with WebSocket/SSE streams, matching engine running, REST API live</li>
      </ul>
    </div>

    <div class="timeline-group">
      <div class="timeline-label">Data</div>
      <ul class="timeline-items">
        <li><strong>District 91</strong> (Ameren / MISO territory) fully mapped as a digital twin</li>
        <li>PostGIS spatial database for proximity matching, live weather and DNI feeds from Open-Meteo, MISO LMP integration</li>
        <li>Green Button meter ingestion with optimistic settlement logic to work around the 24 to 48 hour data delay</li>
        <li>Pub/Sub topics and BigQuery pipelines for real-time grid event streaming</li>
      </ul>
    </div>

    <div class="timeline-group">
      <div class="timeline-label">Blockchain</div>
      <ul class="timeline-items">
        <li>Smart contracts deployed on <strong>Arbitrum Sepolia</strong> (L2): TinyHubMarket and TinyHubToken</li>
        <li>Batch settler running with optimistic aggregation, roughly 95% gas savings versus per-trade on-chain</li>
        <li>Cloud KMS for wallet key management, Firestore for identity, Firebase Auth</li>
        <li>ERC-4337 account abstraction planned through managed Pimlico or Biconomy</li>
      </ul>
    </div>

    <div class="timeline-group">
      <div class="timeline-label">Hardware</div>
      <ul class="timeline-items">
        <li>Open-standard CT clamp integration path designed ($35 Shelly EM / Emporia Vue via MQTT)</li>
        <li>Tesla Fleet API integration scoped for V2H and Powershare demo</li>
        <li>Bypasses OEM walled gardens (Enphase, SolarEdge, Tesla proprietary APIs) by design</li>
      </ul>
    </div>

    <div class="timeline-group">
      <div class="timeline-label">Legal and regulatory</div>
      <ul class="timeline-items">
        <li>FERC Order 2222 positioning as federal preemption shield over state ARES classification</li>
        <li>Deferred-fee counsel strategy identified with target firms (Cooley, Fenwick)</li>
        <li>Shadow market backtest architected as primary proof-of-economics deliverable for investors</li>
      </ul>
    </div>

    <div class="timeline-group">
      <div class="timeline-label">What's next</div>
      <ul class="timeline-items">
        <li>Illinois pilot deployment within Ameren / MISO territory</li>
        <li>30-day shadow market backtest on D91 live data</li>
        <li><strong>$2M seed raise</strong> to fund the pilot and first hires</li>
      </ul>
    </div>
  </section>

  <!-- ─── FOUNDER NOTE ─── -->
  <section class="block reveal">
    <div class="section-head">
      <span class="section-num">05 // Founder Note</span>
      <h2 class="section-title">A Note From the Founder</h2>
    </div>
    <div class="prose">
      <p>I grew up in a small town. That's not a line in a pitch deck. It's the whole reason Tiny-Hub exists.</p>

      <p>When Walmart came to small towns in the 80s and 90s, the local hardware stores, pharmacies, and grocers closed one by one. Amazon came for retail after that and finished the job. Every time, the pattern was the same: a larger player operated at a scale the local businesses couldn't match, captured the value that used to circulate locally, and permanently extracted it to somewhere else. The communities that lost the most had the least say in the decision.</p>

      <p><strong>The electrical grid is the next version of this story, and it's already underway.</strong></p>

      <p>My background is in logistics and sales. I spent years inside trucking and rail, which is really just the business of moving valuable things long distances through rigid systems that demand their cut at every stage. Then I spent years in sales, learning how to actually talk to the people on both ends of those systems. The ones writing the checks and the ones absorbing the cost. Somewhere in between, I got hooked on data. Not dashboards for the sake of dashboards, but finding the real story hiding inside a messy spreadsheet and engineering a way to fix it.</p>

      <p><strong>The electrical grid is the largest logistics system in the country. And right now, it's running on the exact same extractive pattern that hollowed out Main Street.</strong></p>

      <p>Long distances, opaque pricing, monopoly tolls at every junction, and almost no way for a local community to participate in the value it produces. Illinois ratepayers are financing a macro-grid they barely use. Rooftops and home batteries worth billions sit idle because the hardware is locked down by corporate gatekeepers and the utility data is two days late. Meanwhile, the neighborhoods actually generating the power have no practical way to share it with each other.</p>

      <p>I started building Tiny-Hub because the tools finally caught up to the problem. Google Cloud, Arbitrum, modern AI. Stack them right, and a single person can build the infrastructure that would have required a team of fifty just five years ago. That's not a flex; it's the point. If a small team can build grid-scale coordination, then the grid doesn't have to belong to the monopolies anymore. It can belong to the communities it serves.</p>

      <p>That's what I'm doing here. Building the coordination layer that lets neighbors generate, share, and profit from their own power. Keeping the economic value exactly where it's produced. Giving small communities a seat at a table they've historically paid for, but never been allowed to sit at.</p>

      <p><strong>Great moments are born from great opportunity. I'd rather spend the next decade of my life trying to get this right so that the communities I grew up in benefit from innovation for once.</strong></p>

      <div class="signature">— Cole</div>
    </div>
  </section>

</main>

<footer>
  <div><span class="brand">TINY·HUB ENERGY</span> &nbsp;//&nbsp; Upgrading the grid, one neighborhood at a time.</div>
  <div>© 2026 // tinyhub.energy</div>
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
print(f"[OK] templates/about.html created ({len(about_html)} bytes)")

# ────────────────────────────────────────────────────────────
# 2) Add /about route to app.py and update nav links on landing
# ────────────────────────────────────────────────────────────
app = Path("app.py")
src = app.read_text()

old_route = '''@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")'''
new_route = '''@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/about")
def about():
    return render_template("about.html")'''
assert old_route in src, "dashboard route not found in app.py"
src = src.replace(old_route, new_route)
app.write_text(src)
print("[OK] /about route added to app.py")

# ────────────────────────────────────────────────────────────
# 3) Update landing.html nav: /about anchor -> real /about URL
# ────────────────────────────────────────────────────────────
landing = Path("templates/landing.html")
lsrc = landing.read_text()
lsrc_new = lsrc.replace(
    '<li><a href="#about">About</a></li>',
    '<li><a href="/about">About</a></li>'
)
assert lsrc_new != lsrc, "landing nav #about link not found"
landing.write_text(lsrc_new)
print("[OK] landing.html nav updated to link to /about")

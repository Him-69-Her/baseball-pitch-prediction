#!/usr/bin/env python3
"""
TINY-HUB — Replace time.sleep() loop with Cloud Scheduler tick subscriber.

Patches d91_marketplace_live.py to:
1. Subscribe to the market-ticks Pub/Sub topic
2. Run run_trade() only when a tick message arrives
3. Remove the tight while True / time.sleep loop

Run from project root:
    python3 add_cloud_scheduler.py
"""

from pathlib import Path

TARGET = Path("d91_marketplace_live.py")
if not TARGET.exists():
    print(f"  ❌ {TARGET} not found.")
    exit(1)

source = TARGET.read_text(encoding="utf-8")

# ── Patch 1: Add tick subscription config after PROJECT_ID ─
OLD_CONFIG = 'TOPIC_ID = "district91-energy"'
NEW_CONFIG = '''TOPIC_ID = "district91-energy"
TICK_TOPIC = "market-ticks"
TICK_SUB   = "market-ticks-d91-sub"'''

if OLD_CONFIG not in source:
    print("  ❌ Patch 1 failed — TOPIC_ID config not found.")
    exit(1)

source = source.replace(OLD_CONFIG, NEW_CONFIG, 1)
print("  ✅ Patch 1: tick topic/sub constants added")

# ── Patch 2: Replace the main while True sleep loop ─────────
OLD_LOOP = """# ── Main Loop ───────────────────────────────────────────────
while True:
    try:
        run_trade()
        time.sleep(random.uniform(2, 6))
    except KeyboardInterrupt:
        total = trade_count + rejected_count
        rate = (trade_count / total * 100) if total > 0 else 0
        print()
        print("  ╔═══════════════════════════════════════════════════════════════════════╗")
        print("  ║                   D91 LIVE FINAL REPORT                              ║")
        print("  ╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"  ║  Trades settled:    {trade_count:>6}                                           ║")
        print(f"  ║  Trades rejected:   {rejected_count:>6}                                           ║")
        print(f"  ║  Settlement rate:   {rate:>6.1f}%                                          ║")
        print(f"  ║  Total MWh traded:  {total_mwh_traded:>10.2f}                                    ║")
        print(f"  ║  Community profit:  ${total_profit:>11.2f}                                    ║")
        print(f"  ║  Island events:     {island_events:>6}                                           ║")
        print("  ╚═══════════════════════════════════════════════════════════════════════╝")
        break
    except Exception as e:
        print(f"  Error: {e}")
        time.sleep(5)"""

NEW_LOOP = """# ── Cloud Scheduler Tick Mode ──────────────────────────────
# Instead of time.sleep(), we subscribe to the market-ticks
# topic. Cloud Scheduler publishes a message every 5 minutes.
# This is more reliable, auto-restarts on failure, and doesn't
# block the VM with a polling loop.

def on_tick(message):
    \"\"\"Called by Pub/Sub when a market-tick arrives.\"\"\"
    message.ack()
    try:
        payload = json.loads(message.data.decode("utf-8"))
        district = payload.get("district", "")
        if district and district != "IL_D91":
            return  # Not our district
    except Exception:
        pass  # Malformed tick — run anyway

    try:
        run_trade()
    except Exception as e:
        print(f"  ⚠️  Trade error on tick: {e}")


def ensure_tick_sub(subscriber):
    \"\"\"Create the tick subscription if it doesn't exist.\"\"\"
    tick_topic_path = f"projects/{PROJECT_ID}/topics/{TICK_TOPIC}"
    tick_sub_path   = subscriber.subscription_path(PROJECT_ID, TICK_SUB)
    try:
        subscriber.create_subscription(
            request={
                "name": tick_sub_path,
                "topic": tick_topic_path,
                "ack_deadline_seconds": 60,
            }
        )
        print(f"  ✅ Created tick subscription: {TICK_SUB}")
    except Exception as e:
        if "ALREADY_EXISTS" in str(e) or "lready" in str(e):
            print(f"  ⏭️  Tick subscription exists: {TICK_SUB}")
        else:
            print(f"  ⚠️  Tick sub error (will fall back to local loop): {e}")
            return False
    return True


# Try to set up Cloud Scheduler tick mode
_tick_subscriber = pubsub_v1.SubscriberClient()
_tick_ok = ensure_tick_sub(_tick_subscriber)

if _tick_ok:
    # ── Tick-driven mode (Cloud Scheduler) ─────────────────
    _tick_sub_path = _tick_subscriber.subscription_path(PROJECT_ID, TICK_SUB)
    _streaming = _tick_subscriber.subscribe(_tick_sub_path, callback=on_tick)
    print()
    print("  ⏱  Tick-driven mode active — waiting for Cloud Scheduler ticks")
    print("     (ticks every 5 min from GCP Cloud Scheduler)")
    print("     Ctrl+C to stop.")
    print()
    try:
        _streaming.result()
    except KeyboardInterrupt:
        _streaming.cancel()
        _streaming.result()
else:
    # ── Fallback: local sleep loop ──────────────────────────
    print()
    print("  ⚠️  Falling back to local sleep loop (Cloud Scheduler not reachable)")
    print()
    while True:
        try:
            run_trade()
            time.sleep(300)  # 5 minutes
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(30)

total = trade_count + rejected_count
rate = (trade_count / total * 100) if total > 0 else 0
print()
print("  ╔═══════════════════════════════════════════════════════════════════════╗")
print("  ║                   D91 LIVE FINAL REPORT                              ║")
print("  ╠═══════════════════════════════════════════════════════════════════════╣")
print(f"  ║  Trades settled:    {trade_count:>6}                                           ║")
print(f"  ║  Trades rejected:   {rejected_count:>6}                                           ║")
print(f"  ║  Settlement rate:   {rate:>6.1f}%                                          ║")
print(f"  ║  Total MWh traded:  {total_mwh_traded:>10.2f}                                    ║")
print(f"  ║  Community profit:  ${total_profit:>11.2f}                                    ║")
print(f"  ║  Island events:     {island_events:>6}                                           ║")
print("  ╚═══════════════════════════════════════════════════════════════════════╝")"""

if OLD_LOOP not in source:
    print("  ❌ Patch 2 failed — main loop not found.")
    exit(1)

source = source.replace(OLD_LOOP, NEW_LOOP, 1)
print("  ✅ Patch 2: sleep loop replaced with tick subscriber")

TARGET.write_text(source, encoding="utf-8")
print()
print("  ✅ d91_marketplace_live.py patched for Cloud Scheduler.")
print()
print("  Next steps:")
print("  1. Run setup_cloud_scheduler.sh (needs gcloud auth login)")
print("  2. Restart d91_marketplace_live.py — it will wait for ticks")
print("  3. Verify in GCP Console → Cloud Scheduler → Run Now to test")
print()

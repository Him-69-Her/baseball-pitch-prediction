"""
TINY-HUB-NETWORK — District 91 Pub/Sub Topic Setup
Creates the dedicated 'district91-energy' topic + subscription
on the tiny-hub-network GCP project.

Run once on the VM:
    python3 d91_topic_setup.py

Separate from D63's 'energy-pulse' topic so each district
has its own message stream. The bridge (Step 4) connects them.
"""

import os
import json
from google.cloud import pubsub_v1

# ── Config ──────────────────────────────────────────────────
PROJECT_ID = "tiny-hub-network"
TOPIC_ID = "district91-energy"
SUBSCRIPTION_ID = "district91-energy-sub"

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "key.json"

# ── Create Topic ────────────────────────────────────────────
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

print()
print("  ╔══════════════════════════════════════════════════════════════╗")
print("  ║  TINY-HUB-NETWORK — District 91 Pub/Sub Setup              ║")
print("  ╠══════════════════════════════════════════════════════════════╣")
print(f"  ║  Project:      {PROJECT_ID:>30}            ║")
print(f"  ║  Topic:        {TOPIC_ID:>30}            ║")
print(f"  ║  Subscription: {SUBSCRIPTION_ID:>30}            ║")
print("  ╚══════════════════════════════════════════════════════════════╝")
print()

try:
    topic = publisher.create_topic(request={"name": topic_path})
    print(f"  ✅ Created topic: {topic.name}")
except Exception as e:
    if "ALREADY_EXISTS" in str(e):
        print(f"  ⏭️  Topic already exists: {topic_path}")
    else:
        print(f"  ❌ Topic error: {e}")
        raise

# ── Create Subscription ────────────────────────────────────
subscriber = pubsub_v1.SubscriberClient()
sub_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)

try:
    sub = subscriber.create_subscription(
        request={
            "name": sub_path,
            "topic": topic_path,
            "ack_deadline_seconds": 60,
            "message_retention_duration": {"seconds": 86400},  # 24h retention
            "retain_acked_messages": False,
        }
    )
    print(f"  ✅ Created subscription: {sub.name}")
except Exception as e:
    if "ALREADY_EXISTS" in str(e):
        print(f"  ⏭️  Subscription already exists: {sub_path}")
    else:
        print(f"  ❌ Subscription error: {e}")
        raise

# ── Verify with a test message ──────────────────────────────
test_msg = json.dumps({
    "type": "topic_init",
    "district": "IL_D91",
    "status": "online",
    "towns": 15,
    "sellers": 1289,
    "mwh_potential": 720252.41,
}).encode("utf-8")

future = publisher.publish(topic_path, test_msg)
msg_id = future.result()

print(f"  ✅ Test message published: {msg_id}")
print()
print("  ── Topic Map ───────────────────────────────────────────")
print(f"    energy-pulse        → McHenry D63  (11 sellers, ~63 MWh/yr)")
print(f"    district91-energy   → IL D91       (1,289 sellers, ~720K MWh/yr)")
print(f"    (bridge)            → cross-district surplus routing")
print()
print("  Ready. Run d91_marketplace.py next.")
print()

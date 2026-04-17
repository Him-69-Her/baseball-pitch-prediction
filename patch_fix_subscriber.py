#!/usr/bin/env python3
"""Fix start_subscribers: skip D63 entirely, only subscribe to D91."""
from pathlib import Path

f = Path("app.py")
src = f.read_text()
orig = src

old = '''def start_subscribers():
    """Start Pub/Sub subscribers in background threads."""
    subscriber = pubsub_v1.SubscriberClient()
    d63_sub_path = subscriber.subscription_path(PROJECT_ID, D63_SUB)
    d91_sub_path = subscriber.subscription_path(PROJECT_ID, D91_SUB)
    # Ensure subs exist
    publisher = pubsub_v1.PublisherClient()
    d63_topic_path = publisher.topic_path(PROJECT_ID, D63_TOPIC)
    d91_topic_path = publisher.topic_path(PROJECT_ID, D91_TOPIC)
    for sub_path, topic_path in [(d63_sub_path, d63_topic_path), (d91_sub_path, d91_topic_path)]:
        try:
            subscriber.create_subscription(
                request={"name": sub_path, "topic": topic_path, "ack_deadline_seconds": 30}
            )
            print(f"  \u2705 Created {sub_path}")
        except Exception as e:
            if "ALREADY_EXISTS" in str(e) or "lready" in str(e):
                print(f"  \u23ed\ufe0f  {sub_path} exists")
            else:
                print(f"  \u274c {sub_path}: {e}")
    flow = pubsub_v1.types.FlowControl(max_messages=20)
    subscriber.subscribe(d63_sub_path, callback=d63_callback, flow_control=flow)
    subscriber.subscribe(d91_sub_path, callback=d91_callback, flow_control=flow)
    print("  \u2705 Subscribed to both topics")'''

new = '''def start_subscribers():
    """Start Pub/Sub subscriber for D91 only."""
    try:
        subscriber = pubsub_v1.SubscriberClient()
        d91_sub_path = subscriber.subscription_path(PROJECT_ID, D91_SUB)
        d91_topic_path = f"projects/{PROJECT_ID}/topics/{D91_TOPIC}"
        # Ensure subscription exists
        try:
            subscriber.create_subscription(
                request={"name": d91_sub_path, "topic": d91_topic_path, "ack_deadline_seconds": 30}
            )
            print(f"  \u2705 Created subscription {d91_sub_path}")
        except Exception as e:
            if "ALREADY_EXISTS" in str(e) or "lready" in str(e):
                print(f"  \u23ed\ufe0f  {d91_sub_path} exists")
            else:
                print(f"  \u26a0\ufe0f  Sub setup: {e}")
        flow = pubsub_v1.types.FlowControl(max_messages=20)
        subscriber.subscribe(d91_sub_path, callback=d91_callback, flow_control=flow)
        print("  \u2705 Subscribed to D91 trades")
    except Exception as e:
        print(f"  \u274c Subscriber failed: {e}")
        print("  Dashboard will run without live trade streaming")'''

assert old in src, "start_subscribers function not found"
src = src.replace(old, new)

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] start_subscribers fixed — D91 only, with error handling")

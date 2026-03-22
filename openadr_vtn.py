"""
TINY-HUB — OpenADR 2.0b Virtual Top Node (VTN)
================================================
Implements the OpenADR 2.0b Simple HTTP profile.

A VTN is the utility-side server (Ameren's control room).
A VEN is each TinyHub district node that registers and polls for events.

Endpoints (Simple HTTP profile):
  POST /OpenADR2/Simple/2.0b/EiRegisterParty   — VEN registration
  POST /OpenADR2/Simple/2.0b/EiEvent           — Poll for active DR events
  POST /OpenADR2/Simple/2.0b/EiOpt             — VEN opt-in/out of event
  POST /OpenADR2/Simple/2.0b/EiReport          — VEN telemetry report
  POST /OpenADR2/Simple/2.0b/OadrPoll          — Lightweight poll

Admin endpoints (JSON — for Ameren control room UI):
  GET  /oadr/vens          — List registered VENs
  GET  /oadr/events        — List active DR events
  POST /oadr/event/create  — Create a new DR event
  POST /oadr/event/cancel  — Cancel an event
  GET  /oadr/status        — VTN health + event summary

When an event is created it:
  1. Stores the event in memory
  2. Publishes a curtailment message to the Pub/Sub market-ticks topic
  3. Returns XML to polling VENs

Run as part of app.py (imported) or standalone:
    python3 openadr_vtn.py
"""

from __future__ import annotations
import json
import threading
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from xml.etree import ElementTree as ET

from flask import Flask, request, Response, jsonify, Blueprint

# ── OpenADR 2.0b XML Namespaces ─────────────────────────────
NS = {
    "oadr":   "http://openadr.org/oadr-2.0b/2012/07",
    "ei":     "http://docs.oasis-open.org/ns/energyinterop/201110",
    "pyld":   "http://docs.oasis-open.org/ns/energyinterop/201110/payloads",
    "emix":   "http://docs.oasis-open.org/ns/emix/2011/06",
    "xcal":   "http://www.w3.org/2002/12/cal/ical",
    "strm":   "http://docs.oasis-open.org/ns/emix/2011/06/siscale",
    "scale":  "http://docs.oasis-open.org/ns/emix/2011/06/siscale",
}

# Register namespaces for pretty XML output
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

VTN_ID   = "TinyHub-VTN-001"
VTN_NAME = "TinyHub Microgrid VTN"

# ── Signal name mappings ─────────────────────────────────────
SIGNAL_SIMPLE = "SIMPLE"   # 0=normal, 1=low, 2=high, 3=special
SIGNAL_LEVEL  = {
    0: "NORMAL",
    1: "MODERATE",   # ~50% curtailment
    2: "HIGH",       # ~80% curtailment
    3: "EMERGENCY",  # 100% curtailment
}

# ── In-memory state ─────────────────────────────────────────
_lock        = threading.Lock()
_vens: dict[str, dict]   = {}   # venId -> VEN record
_events: dict[str, dict] = {}   # eventId -> event record
_pub_client  = None              # Pub/Sub publisher (set during init)
_project_id  = None
_tick_topic  = None


def init_vtn(pub_client, project_id: str, tick_topic: str = "market-ticks"):
    """Call this from app.py to wire in Pub/Sub."""
    global _pub_client, _project_id, _tick_topic
    _pub_client  = pub_client
    _project_id  = project_id
    _tick_topic  = tick_topic
    print(f"  ✅ OpenADR VTN initialized — topic: projects/{project_id}/topics/{tick_topic}")


# ── XML Helpers ──────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _request_id() -> str:
    return f"req-{uuid.uuid4().hex[:8]}"


def _make_registration_response(ven_id: str, ven_name: str, request_id: str) -> str:
    """Build oadrCreatedParty XML response."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<oadr:oadrPayload xmlns:oadr="http://openadr.org/oadr-2.0b/2012/07"
                  xmlns:ei="http://docs.oasis-open.org/ns/energyinterop/201110"
                  xmlns:pyld="http://docs.oasis-open.org/ns/energyinterop/201110/payloads">
  <oadr:oadrSignedObject>
    <pyld:oadrCreatedParty>
      <ei:eiResponse>
        <ei:responseCode>200</ei:responseCode>
        <ei:responseDescription>OK</ei:responseDescription>
        <requestID>{request_id}</requestID>
      </ei:eiResponse>
      <ei:registrationID>{ven_id}-reg</ei:registrationID>
      <ei:venID>{ven_id}</ei:venID>
      <ei:vtnID>{VTN_ID}</ei:vtnID>
    </pyld:oadrCreatedParty>
  </oadr:oadrSignedObject>
</oadr:oadrPayload>"""
    return xml


def _make_distribute_event(events: list[dict], request_id: str) -> str:
    """Build oadrDistributeEvent XML with all active events."""
    event_xml_list = []
    for ev in events:
        dtstart = ev["dtstart"]
        duration = ev["duration_min"]
        signal_level = ev["signal_level"]
        event_xml_list.append(f"""      <ei:eiEvent>
        <ei:eventDescriptor>
          <ei:eventID>{ev["event_id"]}</ei:eventID>
          <ei:modificationNumber>0</ei:modificationNumber>
          <ei:priority>1</ei:priority>
          <ei:eiMarketContext>
            <emix:marketContext xmlns:emix="http://docs.oasis-open.org/ns/emix/2011/06">
              http://tinyhub.energy/oadr/market
            </emix:marketContext>
          </ei:eiMarketContext>
          <ei:createdDateTime>{ev["created"]}</ei:createdDateTime>
          <ei:eventStatus>active</ei:eventStatus>
          <ei:testEvent>false</ei:testEvent>
        </ei:eventDescriptor>
        <ei:eiActivePeriod>
          <xcal:dtstart xmlns:xcal="http://www.w3.org/2002/12/cal/ical">
            <xcal:date-time>{dtstart}</xcal:date-time>
          </xcal:dtstart>
          <xcal:duration xmlns:xcal="http://www.w3.org/2002/12/cal/ical">
            <xcal:duration>PT{duration}M</xcal:duration>
          </xcal:duration>
          <ei:tolerance><ei:tolerate><xcal:duration xmlns:xcal="http://www.w3.org/2002/12/cal/ical">PT0M</xcal:duration></xcal:tolerate></ei:tolerance>
        </ei:eiActivePeriod>
        <ei:eiEventSignals>
          <ei:eiEventSignal>
            <strm:intervals xmlns:strm="http://docs.oasis-open.org/ns/emix/2011/06/siscale">
              <ei:interval>
                <xcal:duration xmlns:xcal="http://www.w3.org/2002/12/cal/ical">
                  <xcal:duration>PT{duration}M</xcal:duration>
                </xcal:duration>
                <ei:signalPayload>
                  <ei:payloadFloat>
                    <ei:value>{signal_level}</ei:value>
                  </ei:payloadFloat>
                </ei:signalPayload>
              </ei:interval>
            </strm:intervals>
            <ei:signalName>{SIGNAL_SIMPLE}</ei:signalName>
            <ei:signalType>level</ei:signalType>
            <ei:signalID>sig-{ev['event_id']}</ei:signalID>
            <ei:currentValue>
              <ei:payloadFloat><ei:value>{signal_level}</ei:value></ei:payloadFloat>
            </ei:currentValue>
          </ei:eiEventSignal>
        </ei:eiEventSignals>
        <ei:eiTarget>
          <ei:venID>{ev.get("target_ven", "ALL")}</ei:venID>
        </ei:eiTarget>
      </ei:eiEvent>""")

    events_block = "\n".join(event_xml_list) if event_xml_list else ""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<oadr:oadrPayload xmlns:oadr="http://openadr.org/oadr-2.0b/2012/07"
                  xmlns:ei="http://docs.oasis-open.org/ns/energyinterop/201110"
                  xmlns:pyld="http://docs.oasis-open.org/ns/energyinterop/201110/payloads">
  <oadr:oadrSignedObject>
    <pyld:oadrDistributeEvent>
      <ei:eiResponse>
        <ei:responseCode>200</ei:responseCode>
        <ei:responseDescription>OK</ei:responseDescription>
        <requestID>{request_id}</requestID>
      </ei:eiResponse>
      <ei:vtnID>{VTN_ID}</ei:vtnID>
{events_block}
    </pyld:oadrDistributeEvent>
  </oadr:oadrSignedObject>
</oadr:oadrPayload>"""
    return xml


def _make_created_event_response(event_id: str, request_id: str) -> str:
    """Build oadrCreatedEvent XML — VEN opts in."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<oadr:oadrPayload xmlns:oadr="http://openadr.org/oadr-2.0b/2012/07"
                  xmlns:ei="http://docs.oasis-open.org/ns/energyinterop/201110"
                  xmlns:pyld="http://docs.oasis-open.org/ns/energyinterop/201110/payloads">
  <oadr:oadrSignedObject>
    <pyld:oadrCreatedEvent>
      <ei:eiResponse>
        <ei:responseCode>200</ei:responseCode>
        <ei:responseDescription>OK</ei:responseDescription>
        <requestID>{request_id}</requestID>
      </ei:eiResponse>
      <ei:eventResponses>
        <ei:eventResponse>
          <ei:responseCode>200</ei:responseCode>
          <ei:responseDescription>optIn</ei:responseDescription>
          <requestID>{request_id}</requestID>
          <ei:qualifiedEventID>
            <ei:eventID>{event_id}</ei:eventID>
            <ei:modificationNumber>0</ei:modificationNumber>
          </ei:qualifiedEventID>
          <ei:optType>optIn</ei:optType>
        </ei:eventResponse>
      </ei:eventResponses>
      <ei:venID>TinyHub-D91-VEN</ei:venID>
    </pyld:oadrCreatedEvent>
  </oadr:oadrSignedObject>
</oadr:oadrPayload>"""
    return xml


# ── Pub/Sub curtailment publisher ───────────────────────────

def _publish_curtailment(event: dict):
    """Publish a curtailment command to the market-ticks Pub/Sub topic."""
    if not _pub_client or not _project_id:
        print(f"  ⚠️  OpenADR: Pub/Sub not initialized — curtailment not published")
        return

    signal_level = event["signal_level"]
    curtail_pct  = {0: 0.0, 1: 0.50, 2: 0.80, 3: 1.00}.get(signal_level, 0.5)

    payload = {
        "type":          "OADR_CURTAILMENT",
        "event_id":      event["event_id"],
        "district":      event.get("district", "ALL"),
        "signal_level":  signal_level,
        "signal_name":   SIGNAL_LEVEL.get(signal_level, "UNKNOWN"),
        "curtail_pct":   curtail_pct,
        "duration_min":  event["duration_min"],
        "issued_by":     "TinyHub-VTN",
        "source":        "OpenADR2.0b",
        "timestamp":     _now_iso(),
    }

    topic_path = f"projects/{_project_id}/topics/{_tick_topic}"
    try:
        future = _pub_client.publish(topic_path, json.dumps(payload).encode("utf-8"))
        future.result()
        print(f"  📡 OpenADR event published → Pub/Sub | Level: {SIGNAL_LEVEL[signal_level]} | {curtail_pct*100:.0f}% curtailment")
    except Exception as e:
        print(f"  ❌ OpenADR Pub/Sub publish failed: {e}")


# ── Flask Blueprint ──────────────────────────────────────────
oadr_bp = Blueprint("oadr", __name__)

OADR_BASE = "/OpenADR2/Simple/2.0b"


@oadr_bp.route(f"{OADR_BASE}/EiRegisterParty", methods=["POST"])
def register_party():
    """VEN sends oadrRegisterReport or oadrCreateParty to register."""
    body = request.data.decode("utf-8", errors="replace")
    req_id = _request_id()

    # Parse venID from XML if present
    ven_id   = "TinyHub-D91-VEN"
    ven_name = "TinyHub District 91"
    try:
        root = ET.fromstring(body)
        for child in root.iter():
            if "venID" in child.tag:
                ven_id = child.text or ven_id
            if "venName" in child.tag:
                ven_name = child.text or ven_name
    except Exception:
        pass

    with _lock:
        _vens[ven_id] = {
            "ven_id":       ven_id,
            "ven_name":     ven_name,
            "registered_at": _now_iso(),
            "last_poll":    _now_iso(),
        }

    print(f"  📋 OpenADR VEN registered: {ven_id} ({ven_name})")
    xml = _make_registration_response(ven_id, ven_name, req_id)
    return Response(xml, mimetype="application/xml", status=200)


@oadr_bp.route(f"{OADR_BASE}/EiEvent", methods=["POST"])
@oadr_bp.route(f"{OADR_BASE}/OadrPoll", methods=["POST"])
def ei_event():
    """VEN polls for active DR events."""
    req_id = _request_id()

    # Update last poll time
    body = request.data.decode("utf-8", errors="replace")
    try:
        root = ET.fromstring(body)
        for child in root.iter():
            if "venID" in child.tag and child.text:
                with _lock:
                    if child.text in _vens:
                        _vens[child.text]["last_poll"] = _now_iso()
    except Exception:
        pass

    # Return all active events
    now = datetime.now(timezone.utc)
    with _lock:
        active = [
            ev for ev in _events.values()
            if ev["status"] == "active" and
               datetime.fromisoformat(ev["dtstart"].replace("Z", "+00:00")) <= now <=
               datetime.fromisoformat(ev["dtstart"].replace("Z", "+00:00")) + timedelta(minutes=ev["duration_min"])
        ]

    xml = _make_distribute_event(active, req_id)
    return Response(xml, mimetype="application/xml", status=200)


@oadr_bp.route(f"{OADR_BASE}/EiOpt", methods=["POST"])
def ei_opt():
    """VEN opts in or out of an event."""
    req_id = _request_id()
    body   = request.data.decode("utf-8", errors="replace")
    event_id = "unknown"
    try:
        root = ET.fromstring(body)
        for child in root.iter():
            if "eventID" in child.tag:
                event_id = child.text or event_id
    except Exception:
        pass

    xml = _make_created_event_response(event_id, req_id)
    return Response(xml, mimetype="application/xml", status=200)


@oadr_bp.route(f"{OADR_BASE}/EiReport", methods=["POST"])
def ei_report():
    """VEN submits telemetry report (accept and ack)."""
    req_id = _request_id()
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<oadr:oadrPayload xmlns:oadr="http://openadr.org/oadr-2.0b/2012/07"
                  xmlns:ei="http://docs.oasis-open.org/ns/energyinterop/201110"
                  xmlns:pyld="http://docs.oasis-open.org/ns/energyinterop/201110/payloads">
  <oadr:oadrSignedObject>
    <pyld:oadrCreatedReport>
      <ei:eiResponse>
        <ei:responseCode>200</ei:responseCode>
        <ei:responseDescription>OK</ei:responseDescription>
        <requestID>{req_id}</requestID>
      </ei:eiResponse>
      <ei:pendingReports/>
    </pyld:oadrCreatedReport>
  </oadr:oadrSignedObject>
</oadr:oadrPayload>"""
    return Response(xml, mimetype="application/xml", status=200)


# ── Admin JSON endpoints ─────────────────────────────────────

@oadr_bp.route("/oadr/vens", methods=["GET"])
def admin_vens():
    with _lock:
        return jsonify(list(_vens.values()))


@oadr_bp.route("/oadr/events", methods=["GET"])
def admin_events():
    with _lock:
        return jsonify(list(_events.values()))


@oadr_bp.route("/oadr/event/create", methods=["POST"])
def admin_create_event():
    """
    Create a new DR event.
    JSON body:
      {
        "signal_level": 2,        // 0=normal 1=moderate 2=high 3=emergency
        "duration_min": 30,       // duration in minutes
        "district": "IL_D91",     // or "ALL"
        "note": "Grid stress"     // optional
      }
    """
    data         = request.get_json(force=True) or {}
    signal_level = int(data.get("signal_level", 1))
    duration_min = int(data.get("duration_min", 30))
    district     = data.get("district", "ALL")
    note         = data.get("note", "")
    event_id     = f"evt-{uuid.uuid4().hex[:8]}"

    event = {
        "event_id":     event_id,
        "signal_level": signal_level,
        "signal_name":  SIGNAL_LEVEL.get(signal_level, "UNKNOWN"),
        "duration_min": duration_min,
        "district":     district,
        "dtstart":      _now_iso(),
        "created":      _now_iso(),
        "status":       "active",
        "note":         note,
        "target_ven":   "ALL",
    }

    with _lock:
        _events[event_id] = event

    # Publish curtailment to Pub/Sub
    _publish_curtailment(event)

    print(f"  🔴 OpenADR DR Event created: {event_id} | Level {signal_level} ({SIGNAL_LEVEL.get(signal_level)}) | {duration_min}min | {district}")
    return jsonify({"status": "created", "event": event}), 201


@oadr_bp.route("/oadr/event/cancel", methods=["POST"])
def admin_cancel_event():
    """Cancel an active event. JSON: {"event_id": "evt-abc123"}"""
    data     = request.get_json(force=True) or {}
    event_id = data.get("event_id")
    with _lock:
        if event_id in _events:
            _events[event_id]["status"] = "cancelled"
            # Publish level-0 (normal) to clear curtailment
            clear_event = dict(_events[event_id])
            clear_event["signal_level"] = 0
            _publish_curtailment(clear_event)
            return jsonify({"status": "cancelled", "event_id": event_id})
    return jsonify({"error": "event not found"}), 404


@oadr_bp.route("/oadr/status", methods=["GET"])
def admin_status():
    with _lock:
        active_count = sum(1 for e in _events.values() if e["status"] == "active")
        return jsonify({
            "vtn_id":       VTN_ID,
            "vtn_name":     VTN_NAME,
            "vens":         len(_vens),
            "total_events": len(_events),
            "active_events": active_count,
            "timestamp":    _now_iso(),
        })


# ── Standalone runner ────────────────────────────────────────
if __name__ == "__main__":
    app = Flask(__name__)
    app.register_blueprint(oadr_bp)
    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║  TinyHub OpenADR 2.0b VTN — Standalone Mode             ║")
    print("  ║  Pub/Sub NOT connected (run via app.py for integration)  ║")
    print("  ╠══════════════════════════════════════════════════════════╣")
    print("  ║  VEN endpoints:                                          ║")
    print(f"  ║    POST /OpenADR2/Simple/2.0b/EiRegisterParty           ║")
    print(f"  ║    POST /OpenADR2/Simple/2.0b/EiEvent                   ║")
    print(f"  ║    POST /OpenADR2/Simple/2.0b/OadrPoll                  ║")
    print(f"  ║    POST /OpenADR2/Simple/2.0b/EiOpt                     ║")
    print(f"  ║    POST /OpenADR2/Simple/2.0b/EiReport                  ║")
    print("  ║  Admin endpoints:                                        ║")
    print("  ║    GET  /oadr/status                                     ║")
    print("  ║    GET  /oadr/vens                                       ║")
    print("  ║    GET  /oadr/events                                     ║")
    print("  ║    POST /oadr/event/create                               ║")
    print("  ║    POST /oadr/event/cancel                               ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()
    app.run(host="0.0.0.0", port=5001, debug=False)

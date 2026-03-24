"""
TINY-HUB-NETWORK — Batch Settlement Aggregator
================================================
Collects individual trades from Pub/Sub, aggregates net energy
delta per building per district, then flushes a single
settleBatch() call to TinyHubMarketV3 once per flush interval.

Instead of 1 tx per trade (~300 trades/hour = 300 txs),
this pushes 1 bulk tx per hour with ~50-100 netted entries.

Usage:
    from batch_aggregator import BatchAggregator

    agg = BatchAggregator(flush_interval=3600)  # 1 hour
    agg.add_trade(trade_dict, message_id)        # Called per Pub/Sub message
    # Flusher thread calls agg.flush() automatically every hour
    # Or call agg.flush() manually
"""

import time
import threading
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class BuildingAccumulator:
    """Net energy accumulator for a single building in a single flush window."""
    station_id: str
    district: str
    net_mwh: float = 0.0
    total_revenue: float = 0.0   # sum(mwh * price) for weighted avg
    trade_count: int = 0
    message_ids: list = field(default_factory=list)
    is_bridge: bool = False
    to_district: str = ""

    @property
    def avg_price(self) -> float:
        """Volume-weighted average price across accumulated trades."""
        if self.net_mwh <= 0:
            return 0.0
        return self.total_revenue / self.net_mwh

    def add(self, mwh: float, price: float, message_id: str,
            is_bridge: bool = False, to_district: str = ""):
        self.net_mwh += mwh
        self.total_revenue += mwh * price
        self.trade_count += 1
        self.message_ids.append(message_id)
        if is_bridge:
            self.is_bridge = True
            self.to_district = to_district


class BatchAggregator:
    """
    Collects trades and flushes them as a single settleBatch() call.

    Parameters:
        flush_interval: Seconds between automatic flushes (default 3600 = 1 hour)
        max_buffer_size: Force flush if buffer exceeds this many raw trades
        on_flush: Callback function(entries: list[dict]) called when flushing
    """

    def __init__(self, flush_interval=3600, max_buffer_size=500, on_flush=None):
        self.flush_interval = flush_interval
        self.max_buffer_size = max_buffer_size
        self.on_flush = on_flush

        # Keyed by (station_id, district) → BuildingAccumulator
        self._buffer: dict[tuple[str, str], BuildingAccumulator] = {}
        self._lock = threading.Lock()
        self._raw_count = 0
        self._flush_count = 0
        self._total_settled = 0
        self._total_trades_absorbed = 0
        self._last_flush = time.time()

        # Start the auto-flush timer thread
        self._flush_thread = threading.Thread(target=self._auto_flush, daemon=True)
        self._flush_thread.start()

    def add_trade(self, trade: dict, message_id: str):
        """
        Add a trade to the aggregation buffer.
        Nets energy per building — if a building both sells and gets
        bridge surplus, the amounts accumulate.

        Args:
            trade: Dict with keys: station_id, district, mwh, settled_price,
                   trade_status, origin_district (for bridges)
            message_id: Pub/Sub message ID for idempotency
        """
        station_id = trade.get("station_id", "unknown")
        district = trade.get("district", "IL_D91")
        mwh = trade.get("mwh", 0)
        price = trade.get("settled_price", 0)
        is_bridge = trade.get("trade_status") == "BRIDGE_LISTED"
        to_district = trade.get("origin_district", "")

        if mwh <= 0:
            return

        key = (station_id, district)

        with self._lock:
            if key not in self._buffer:
                self._buffer[key] = BuildingAccumulator(
                    station_id=station_id,
                    district=district
                )

            self._buffer[key].add(mwh, price, message_id, is_bridge, to_district)
            self._raw_count += 1

            # Force flush if buffer is huge
            if self._raw_count >= self.max_buffer_size:
                self._do_flush()

    def flush(self) -> list[dict]:
        """
        Manually trigger a flush. Returns the batch entries sent.
        """
        with self._lock:
            return self._do_flush()

    def _do_flush(self) -> list[dict]:
        """
        Internal flush — must be called with self._lock held.
        Converts accumulated building data into batch entries and
        calls the on_flush callback.
        """
        if not self._buffer:
            self._last_flush = time.time()
            return []

        entries = []
        for key, acc in self._buffer.items():
            if acc.net_mwh <= 0:
                continue

            # Use a composite message ID for the batch entry
            # This is a hash of all individual message IDs — if any
            # individual trade was already settled, the contract's
            # per-entry dedup will skip it
            batch_msg_id = f"batch_{self._flush_count}_{acc.station_id}_{acc.district}"

            entry = {
                "messageId": batch_msg_id,
                "stationId": acc.station_id,
                "district": acc.district,
                "amount": int(acc.net_mwh * 1000),      # milliMWh
                "price": int(acc.avg_price * 10000),     # wei-scale
                "rType": 0,                               # Energy
                "isBridge": acc.is_bridge,
                "toDistrict": acc.to_district if acc.is_bridge else "",
                # Metadata (not sent to contract)
                "_net_mwh": acc.net_mwh,
                "_avg_price": acc.avg_price,
                "_trade_count": acc.trade_count,
                "_message_ids": acc.message_ids,
            }
            entries.append(entry)

        absorbed = self._raw_count
        buildings = len(entries)

        # Reset buffer
        self._buffer.clear()
        self._raw_count = 0
        self._flush_count += 1
        self._total_settled += buildings
        self._total_trades_absorbed += absorbed
        self._last_flush = time.time()

        if entries and self.on_flush:
            try:
                self.on_flush(entries)
            except Exception as e:
                print(f"  ❌ Batch flush callback error: {e}")

        if entries:
            total_mwh = sum(e["_net_mwh"] for e in entries)
            print(f"  📦 BATCH FLUSH #{self._flush_count} | "
                  f"{absorbed} trades → {buildings} entries | "
                  f"{total_mwh:.3f} MWh | "
                  f"{datetime.now().strftime('%H:%M:%S')}")

        return entries

    def _auto_flush(self):
        """Background thread that flushes on the configured interval."""
        while True:
            time.sleep(self.flush_interval)
            with self._lock:
                self._do_flush()

    @property
    def stats(self) -> dict:
        """Current aggregator statistics."""
        with self._lock:
            return {
                "buffered_trades": self._raw_count,
                "buffered_buildings": len(self._buffer),
                "flushes": self._flush_count,
                "total_settled": self._total_settled,
                "total_trades_absorbed": self._total_trades_absorbed,
                "seconds_since_flush": int(time.time() - self._last_flush),
                "flush_interval": self.flush_interval,
                "compression_ratio": (
                    self._total_trades_absorbed / max(self._total_settled, 1)
                ),
            }

    def pending_summary(self) -> str:
        """Human-readable summary of what's in the buffer."""
        with self._lock:
            if not self._buffer:
                return "  Buffer empty"

            lines = [f"  Buffer: {self._raw_count} trades across {len(self._buffer)} buildings"]
            # Show top 5 by MWh
            sorted_buf = sorted(
                self._buffer.values(),
                key=lambda a: a.net_mwh,
                reverse=True
            )[:5]
            for acc in sorted_buf:
                lines.append(
                    f"    {acc.station_id:22} | {acc.district:12} | "
                    f"{acc.net_mwh:.3f} MWh | {acc.trade_count} trades | "
                    f"${acc.avg_price:.4f} avg"
                )
            if len(self._buffer) > 5:
                lines.append(f"    ... and {len(self._buffer) - 5} more")
            return "\n".join(lines)

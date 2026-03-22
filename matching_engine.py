"""
TINY-HUB — Deterministic Order Matching Engine
===============================================
Replaces random.choice(seller) + random.choice(buyer) with a proper
order book that matches deterministically every tick.

Matching strategy: Price-priority + Pro-rata allocation
  - Sellers sorted by ask_price ascending  (cheapest first)
  - Buyers  sorted by bid_price descending (highest willingness first)
  - When multiple sellers qualify for one buyer → pro-rata by MWh capacity
  - Settled price = midpoint of bid and ask

Usage (drop into any marketplace file):
    from matching_engine import MatchingEngine

    engine = MatchingEngine()

    # Each tick: submit fresh orders, then match
    for seller in SELLERS:
        mwh = solar_output(seller)
        if mwh > 0:
            engine.add_sell_order(seller["id"], seller["label"], seller["town"],
                                  seller["type"], mwh, ask_price,
                                  lat=seller.get("lat"), lng=seller.get("lng"))

    for buyer in BUYERS:
        engine.add_buy_order(buyer["id"], buyer["label"], buyer["town"],
                             buyer["type"], buyer["max_bid"] * 0.9,  # bid slightly below max
                             lat=buyer.get("lat"), lng=buyer.get("lng"))

    trades = engine.match()
    engine.clear()  # reset for next tick
"""

from __future__ import annotations
from battery_vpp import get_battery, all_battery_status
import math
from dataclasses import dataclass, field

# Ameren IL retail rate — fallback price when no P2P seller available
AMEREN_RETAIL_RATE = 0.12   # $/kWh (typical IL residential retail)
AMEREN_SELLER_ID   = "ameren-macro-grid"
AMEREN_SELLER_LABEL = "Ameren IL Macro-Grid"
AMEREN_SELLER_TOWN  = "District-wide"

# Local I²R distribution line loss (~5% typical for low-voltage networks)
# Buyer pays for delivered MWh; seller earns on generated MWh.
LINE_LOSS_PCT = 0.05

# Distance tiers for proximity-first matching (km)
# Closest sellers fill demand first; pro-rata within each tier.
PROXIMITY_TIERS = [5.0, 15.0, 50.0, float('inf')]
PROXIMITY_TIER_LABELS = ["<5km", "<15km", "<50km", "50km+"]
from typing import Optional


@dataclass
class SellOrder:
    station_id: str
    label: str
    town: str
    seller_type: str
    mwh: float
    ask_price: float          # $/kWh
    lat: Optional[float] = None
    lng: Optional[float] = None
    remaining_mwh: float = field(init=False)

    def __post_init__(self):
        self.remaining_mwh = self.mwh


@dataclass
class BuyOrder:
    buyer_id: str
    label: str
    town: str
    buyer_type: str
    bid_price: float          # $/kWh — max willingness to pay
    demand_mwh: float = 1.0   # how much the buyer wants this tick
    lat: Optional[float] = None
    lng: Optional[float] = None
    remaining_mwh: float = field(init=False)

    def __post_init__(self):
        self.remaining_mwh = self.demand_mwh


@dataclass
class MatchedTrade:
    seller_id: str
    seller_label: str
    seller_town: str
    seller_type: str
    buyer_id: str
    buyer_label: str
    buyer_town: str
    buyer_type: str
    mwh: float
    ask_price: float
    bid_price: float
    settled_price: float
    net_profit: float
    grid_price: float
    match_type: str           # "price_priority" | "pro_rata"
    distance_km: Optional[float] = None


def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    """Great-circle distance between two lat/lng points in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def battery_output(station_id: str, label: str, capacity_mwh: float,
                   grid_price_kwh: float, toll: float = 0.025) -> float:
    """
    VPP arbitrage wrapper for battery sellers.
    Returns MWh to sell this tick (0 if charging or idle).
    Automatically manages state of charge and LCOS economics.
    """
    vpp = get_battery(station_id, label, capacity_mwh, toll)
    return vpp.get_output(grid_price_kwh)


class MatchingEngine:
    """
    Deterministic P2P energy order book.

    Call flow each market tick:
        engine.add_sell_order(...)   # once per active seller
        engine.add_buy_order(...)    # once per active buyer
        trades = engine.match()      # returns list[MatchedTrade]
        engine.clear()               # reset for next tick
    """

    def __init__(self, toll: float = 0.025, mode: str = "pro_rata",
                 fallback_routing: bool = True,
                 retail_rate: float = AMEREN_RETAIL_RATE):
        """
        Args:
            toll:             Grid toll in $/kWh (Ameren=0.025, ComEd=0.02)
            mode:             "pro_rata", "price_priority", or "proximity"
            fallback_routing: If True, unmatched buyers get macro-grid supply
                              at retail_rate. Zero disruption to buyer.
            retail_rate:      Ameren/ComEd retail rate for fallback trades.
        """
        self.toll = toll
        self.mode = mode
        self.fallback_routing = fallback_routing
        self.retail_rate = retail_rate
        self._sell_orders: list[SellOrder] = []
        self._buy_orders:  list[BuyOrder]  = []

    # ── Order submission ────────────────────────────────────

    def add_sell_order(self, station_id: str, label: str, town: str,
                       seller_type: str, mwh: float, ask_price: float,
                       lat: float = None, lng: float = None):
        if mwh <= 0 or ask_price <= 0:
            return
        self._sell_orders.append(SellOrder(
            station_id=station_id, label=label, town=town,
            seller_type=seller_type, mwh=mwh, ask_price=ask_price,
            lat=lat, lng=lng,
        ))

    def add_buy_order(self, buyer_id: str, label: str, town: str,
                      buyer_type: str, bid_price: float, demand_mwh: float = 1.0,
                      lat: float = None, lng: float = None):
        if bid_price <= 0:
            return
        self._buy_orders.append(BuyOrder(
            buyer_id=buyer_id, label=label, town=town,
            buyer_type=buyer_type, bid_price=bid_price,
            demand_mwh=demand_mwh, lat=lat, lng=lng,
        ))

    # ── Matching ────────────────────────────────────────────

    def match(self, grid_price: float = 0.0) -> list[MatchedTrade]:
        if self.mode == "proximity":
            trades = self._match_proximity(grid_price)
        elif self.mode == "pro_rata":
            trades = self._match_pro_rata(grid_price)
        else:
            trades = self._match_price_priority(grid_price)

        if self.fallback_routing:
            trades += self._fallback_unmatched(grid_price)

        return trades

    def _fallback_unmatched(self, grid_price: float) -> list[MatchedTrade]:
        """
        For any buyer still holding unmet demand after P2P matching,
        synthesize a macro-grid trade at Ameren retail rate.
        The buyer pays retail; the 'seller' is Ameren's macro-grid.
        Logged with trade_status FALLBACK so dashboard can distinguish.
        """
        fallback_trades: list[MatchedTrade] = []

        for b in self._buy_orders:
            if b.remaining_mwh < 1e-4:
                continue  # fully matched by P2P

            fill_mwh = round(b.remaining_mwh, 4)
            # Buyer pays retail; no seller profit — cost is passed through
            profit = round((self.retail_rate - self.toll) * fill_mwh, 4)

            fallback_trades.append(MatchedTrade(
                seller_id=AMEREN_SELLER_ID,
                seller_label=AMEREN_SELLER_LABEL,
                seller_town=AMEREN_SELLER_TOWN,
                seller_type="macro_grid",
                buyer_id=b.buyer_id,
                buyer_label=b.label,
                buyer_town=b.town,
                buyer_type=b.buyer_type,
                mwh=fill_mwh,
                ask_price=self.retail_rate,
                bid_price=self.retail_rate,
                settled_price=self.retail_rate,
                net_profit=profit,
                grid_price=grid_price,
                match_type="fallback",
                distance_km=None,
            ))

            b.remaining_mwh = 0.0  # mark as filled

        return fallback_trades

    def _match_proximity(self, grid_price: float) -> list[MatchedTrade]:
        """
        Proximity-first: group sellers by distance tier from each buyer,
        fill closest tier first, pro-rata within each tier.

        Tier boundaries (km): [5.0, 15.0, 50.0] + [inf]
        Sellers without lat/lng go into the last tier.
        Buyers without lat/lng fall back to pro_rata matching.
        """
        buyers  = sorted(self._buy_orders,  key=lambda b: b.bid_price, reverse=True)
        sellers = list(self._sell_orders)  # mutable copy for remaining_mwh tracking

        trades: list[MatchedTrade] = []

        for b in buyers:
            if b.remaining_mwh < 1e-4:
                continue

            # If buyer has no location, fall back to pro-rata across all qualifying sellers
            if b.lat is None or b.lng is None:
                qualifying = [s for s in sellers if s.ask_price <= b.bid_price and s.remaining_mwh > 1e-4]
                trades += self._pro_rata_fill(b, qualifying, grid_price)
                continue

            # Group qualifying sellers into distance tiers
            tiers: list[list] = [[] for _ in PROXIMITY_TIERS]

            for s in sellers:
                if s.ask_price > b.bid_price or s.remaining_mwh < 1e-4:
                    continue

                if s.lat is None or s.lng is None:
                    tiers[-1].append((s, None))  # no location → last tier
                    continue

                dist = _haversine_km(s.lat, s.lng, b.lat, b.lng)
                placed = False
                for ti, threshold in enumerate(PROXIMITY_TIERS):
                    if dist < threshold:
                        tiers[ti].append((s, dist))
                        placed = True
                        break
                if not placed:
                    tiers[-1].append((s, dist))

            # Fill tier by tier, closest first
            for ti, tier_sellers in enumerate(tiers):
                if b.remaining_mwh < 1e-4:
                    break
                if not tier_sellers:
                    continue

                # Within tier: pro-rata by available MWh
                total_avail = sum(s.remaining_mwh for s, _ in tier_sellers)
                demand = b.remaining_mwh

                for s, dist in tier_sellers:
                    if b.remaining_mwh < 1e-4:
                        break

                    share = s.remaining_mwh / total_avail
                    generated_mwh = round(min(share * demand, s.remaining_mwh), 4)
                    if generated_mwh < 1e-4:
                        continue

                    delivered_mwh = round(generated_mwh * (1 - LINE_LOSS_PCT), 4)
                    settled = round((s.ask_price + b.bid_price) / 2, 4)
                    profit  = round((settled - self.toll) * generated_mwh, 4)

                    tier_label = PROXIMITY_TIER_LABELS[ti] if ti < len(PROXIMITY_TIER_LABELS) else "far"

                    trades.append(MatchedTrade(
                        seller_id=s.station_id, seller_label=s.label,
                        seller_town=s.town, seller_type=s.seller_type,
                        buyer_id=b.buyer_id, buyer_label=b.label,
                        buyer_town=b.town, buyer_type=b.buyer_type,
                        mwh=delivered_mwh, ask_price=s.ask_price,
                        bid_price=b.bid_price, settled_price=settled,
                        net_profit=profit, grid_price=grid_price,
                        match_type=f"proximity_{tier_label}",
                        distance_km=round(dist, 2) if dist is not None else None,
                    ))

                    s.remaining_mwh -= generated_mwh
                    b.remaining_mwh -= delivered_mwh

        return trades

    def _pro_rata_fill(self, buyer: BuyOrder, sellers: list,
                       grid_price: float) -> list[MatchedTrade]:
        """Helper: pro-rata fill a single buyer from a list of sellers."""
        if not sellers or buyer.remaining_mwh < 1e-4:
            return []

        total_avail = sum(s.remaining_mwh for s in sellers)
        if total_avail < 1e-4:
            return []

        demand = buyer.remaining_mwh
        trades: list[MatchedTrade] = []

        for s in sellers:
            if buyer.remaining_mwh < 1e-4:
                break

            share = s.remaining_mwh / total_avail
            generated_mwh = round(min(share * demand, s.remaining_mwh), 4)
            if generated_mwh < 1e-4:
                continue

            delivered_mwh = round(generated_mwh * (1 - LINE_LOSS_PCT), 4)
            settled = round((s.ask_price + buyer.bid_price) / 2, 4)
            profit  = round((settled - self.toll) * generated_mwh, 4)
            dist    = self._distance(s, buyer)

            trades.append(MatchedTrade(
                seller_id=s.station_id, seller_label=s.label,
                seller_town=s.town, seller_type=s.seller_type,
                buyer_id=buyer.buyer_id, buyer_label=buyer.label,
                buyer_town=buyer.town, buyer_type=buyer.buyer_type,
                mwh=delivered_mwh, ask_price=s.ask_price,
                bid_price=buyer.bid_price, settled_price=settled,
                net_profit=profit, grid_price=grid_price,
                match_type="pro_rata", distance_km=dist,
            ))

            s.remaining_mwh -= generated_mwh
            buyer.remaining_mwh -= delivered_mwh

        return trades

        def _match_price_priority(self, grid_price: float) -> list[MatchedTrade]:
        """
        Standard order book: cheapest seller fills highest bidder first.
        Greedy. Produces 1 trade per seller-buyer pair.
        """
        # Sort: sellers cheapest first, buyers highest bid first
        sellers = sorted(self._sell_orders, key=lambda s: s.ask_price)
        buyers  = sorted(self._buy_orders,  key=lambda b: b.bid_price, reverse=True)

        trades: list[MatchedTrade] = []
        si = bi = 0

        while si < len(sellers) and bi < len(buyers):
            s = sellers[si]
            b = buyers[bi]

            if b.bid_price < s.ask_price:
                bi += 1   # no more buyers can afford this seller
                continue

            generated_mwh = min(s.remaining_mwh, b.remaining_mwh)
            delivered_mwh = round(generated_mwh * (1 - LINE_LOSS_PCT), 4)
            settled  = round((s.ask_price + b.bid_price) / 2, 4)
            profit   = round((settled - self.toll) * generated_mwh, 4)
            dist     = self._distance(s, b)

            trades.append(MatchedTrade(
                seller_id=s.station_id, seller_label=s.label,
                seller_town=s.town, seller_type=s.seller_type,
                buyer_id=b.buyer_id, buyer_label=b.label,
                buyer_town=b.town, buyer_type=b.buyer_type,
                mwh=delivered_mwh, ask_price=s.ask_price,
                bid_price=b.bid_price, settled_price=settled,
                net_profit=profit, grid_price=grid_price,
                match_type="price_priority", distance_km=dist,
            ))

            s.remaining_mwh -= generated_mwh
            b.remaining_mwh -= delivered_mwh

            if s.remaining_mwh < 1e-4:
                si += 1
            if b.remaining_mwh < 1e-4:
                bi += 1

        return trades

    def _match_pro_rata(self, grid_price: float) -> list[MatchedTrade]:
        """
        Pro-rata: each buyer is served by ALL qualifying sellers
        proportionally to their available MWh.
        Ensures no single large seller monopolises premium buyers.
        """
        buyers  = sorted(self._buy_orders,  key=lambda b: b.bid_price, reverse=True)
        sellers = sorted(self._sell_orders, key=lambda s: s.ask_price)

        trades: list[MatchedTrade] = []

        for b in buyers:
            # Find all sellers whose ask <= this buyer's bid
            qualifying = [s for s in sellers if s.ask_price <= b.bid_price and s.remaining_mwh > 1e-4]
            if not qualifying:
                continue

            total_avail = sum(s.remaining_mwh for s in qualifying)
            demand = b.remaining_mwh

            for s in qualifying:
                # Each seller gets a share proportional to their remaining MWh
                share = s.remaining_mwh / total_avail
                generated_mwh = round(min(share * demand, s.remaining_mwh), 4)
                if generated_mwh < 1e-4:
                    continue

                delivered_mwh = round(generated_mwh * (1 - LINE_LOSS_PCT), 4)
                settled = round((s.ask_price + b.bid_price) / 2, 4)
                profit  = round((settled - self.toll) * generated_mwh, 4)
                dist    = self._distance(s, b)

                trades.append(MatchedTrade(
                    seller_id=s.station_id, seller_label=s.label,
                    seller_town=s.town, seller_type=s.seller_type,
                    buyer_id=b.buyer_id, buyer_label=b.label,
                    buyer_town=b.town, buyer_type=b.buyer_type,
                    mwh=delivered_mwh, ask_price=s.ask_price,
                    bid_price=b.bid_price, settled_price=settled,
                    net_profit=profit, grid_price=grid_price,
                    match_type="pro_rata", distance_km=dist,
                ))

                s.remaining_mwh -= generated_mwh
                b.remaining_mwh -= delivered_mwh

        return trades

    # ── Helpers ─────────────────────────────────────────────

    def _distance(self, s: SellOrder, b: BuyOrder) -> Optional[float]:
        if None in (s.lat, s.lng, b.lat, b.lng):
            return None
        return round(_haversine_km(s.lat, s.lng, b.lat, b.lng), 2)

    def clear(self):
        """Reset order book for the next tick."""
        self._sell_orders.clear()
        self._buy_orders.clear()

    def stats(self) -> dict:
        return {
            "pending_sell_orders": len(self._sell_orders),
            "pending_buy_orders":  len(self._buy_orders),
            "sell_mwh_available":  sum(s.remaining_mwh for s in self._sell_orders),
            "buy_mwh_demanded":    sum(b.remaining_mwh for b in self._buy_orders),
            "batteries":           all_battery_status(),
        }

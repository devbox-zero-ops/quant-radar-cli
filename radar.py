"""
quant-radar-cli — Zero-Dependency Crypto Cross-Venue Funding Arbitrage,
Polymarket Mispricing Scanner & Persistent Paper-Trading Simulator.

Public read-only market data (zero API keys required):
- Hyperliquid Mainnet API: metaAndAssetCtxs + predictedFundings (HlPerp / BinPerp / BybitPerp)
- Polymarket Gamma API: active liquid events & NegRisk multi-outcome bundles

Strictly simulation/analytics by default ($0 real funds risked).
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

HL_INFO_URL = "https://api.hyperliquid.xyz/info"
POLY_EVENTS_URL = "https://gamma-api.polymarket.com/events"
POLY_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
UA = "quant-radar-cli/1.0 (+https://github.com/devbox-zero-ops/quant-radar-cli)"

# Conservative taker round-trip fees (bps, entry + exit across both legs)
DEFAULT_CROSS_VENUE_RT_BPS = 18.0  # ~0.035% HL + ~0.055% CEX x 2 sides = 0.18%
DEFAULT_CASH_CARRY_RT_BPS = 15.0   # ~0.035% HL + ~0.040% spot x 2 sides = 0.15%


def _http_json(url: str, payload=None, timeout: int = 20):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=("POST" if data is not None else "GET"))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def annualize_rate(rate: float, interval_hours: float) -> float:
    if not interval_hours or interval_hours <= 0:
        return 0.0
    return rate * (24.0 / interval_hours) * 365.0 * 100.0


def calc_breakeven_hours(net_apr_pct: float, rt_fee_bps: float) -> float:
    """Hours of holding required for funding spread to recover round-trip taker fees."""
    if net_apr_pct <= 0:
        return float("inf")
    hourly_pct = net_apr_pct / (365.0 * 24.0)
    fee_pct = rt_fee_bps / 100.0
    return round(fee_pct / hourly_pct, 2)


def fetch_hyperliquid_funding(min_oi_usd: float = 500_000.0, min_vol_usd: float = 1_000_000.0, rt_fee_bps: float = DEFAULT_CROSS_VENUE_RT_BPS):
    """Fetch Hyperliquid asset contexts + cross-venue predicted funding rates (HL/Binance/Bybit)."""
    meta_ctxs = _http_json(HL_INFO_URL, {"type": "metaAndAssetCtxs"})
    pred_raw = _http_json(HL_INFO_URL, {"type": "predictedFundings"})

    pred_map = {}
    for entry in pred_raw:
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        sym, venues = entry[0], entry[1]
        vmap = {}
        for vpair in venues:
            if not isinstance(vpair, list) or len(vpair) < 2 or not isinstance(vpair[1], dict):
                continue
            vname, vdata = vpair[0], vpair[1]
            try:
                fr = float(vdata["fundingRate"])
                ih = float(vdata.get("fundingIntervalHours") or 1.0)
                vmap[vname] = {
                    "rate": fr,
                    "interval_hours": ih,
                    "apr_pct": round(annualize_rate(fr, ih), 2),
                }
            except Exception:
                pass
        pred_map[sym] = vmap

    universe = meta_ctxs[0]["universe"]
    ctxs = meta_ctxs[1]
    rows = []
    for u, c in zip(universe, ctxs):
        sym = u.get("name", "")
        try:
            mark_px = float(c.get("markPx") or 0)
            oracle_px = float(c.get("oraclePx") or 0)
            oi_usd = float(c.get("openInterest") or 0) * mark_px
            vol_usd = float(c.get("dayNtlVlm") or 0)
            hl_fr = float(c.get("funding") or 0)
        except Exception:
            continue
        if oi_usd < min_oi_usd or vol_usd < min_vol_usd or mark_px <= 0:
            continue

        hl_apr = round(annualize_rate(hl_fr, 1.0), 2)
        basis_bps = round(((mark_px - oracle_px) / oracle_px) * 10000.0, 2) if oracle_px > 0 else 0.0
        venues = pred_map.get(sym, {})
        best_cross = None
        if len(venues) >= 2:
            sorted_v = sorted(venues.items(), key=lambda kv: kv[1]["apr_pct"])
            low_v, low_d = sorted_v[0]
            high_v, high_d = sorted_v[-1]
            spread_apr = round(high_d["apr_pct"] - low_d["apr_pct"], 2)
            if spread_apr > 0:
                best_cross = {
                    "long_venue": low_v,
                    "short_venue": high_v,
                    "long_apr_pct": low_d["apr_pct"],
                    "short_apr_pct": high_d["apr_pct"],
                    "spread_apr_pct": spread_apr,
                    "breakeven_hours": calc_breakeven_hours(spread_apr, rt_fee_bps),
                }

        rows.append({
            "symbol": sym,
            "mark_px": mark_px,
            "oracle_px": oracle_px,
            "basis_bps": basis_bps,
            "oi_usd": round(oi_usd, 2),
            "vol_24h_usd": round(vol_usd, 2),
            "hl_hourly_rate": hl_fr,
            "hl_apr_pct": hl_apr,
            "cash_carry_breakeven_hours": calc_breakeven_hours(abs(hl_apr), DEFAULT_CASH_CARRY_RT_BPS),
            "venues": venues,
            "best_cross_arb": best_cross,
        })

    cross_top = sorted(
        [r for r in rows if r["best_cross_arb"]],
        key=lambda r: r["best_cross_arb"]["spread_apr_pct"],
        reverse=True,
    )
    single_top = sorted(rows, key=lambda r: abs(r["hl_apr_pct"]), reverse=True)
    return {
        "observed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "liquid_markets_scanned": len(rows),
        "filters": {"min_oi_usd": min_oi_usd, "min_vol_usd": min_vol_usd, "rt_fee_bps": rt_fee_bps},
        "top_cross_venue_arb": cross_top[:12],
        "top_single_hl_funding": single_top[:12],
    }


def analyze_polymarket_events(events: list, now_ts: float = None, min_vol_usd: float = 10_000.0):
    """Analyze active Polymarket NegRisk events for sum-to-1 deviations and short-dated high-certainty bonds."""
    now = now_ts if now_ts is not None else datetime.now(timezone.utc).timestamp()
    negrisk_arbs = []
    short_bonds = []

    for ev in events:
        title = ev.get("title", "")
        slug = ev.get("slug", "")
        vol_ev = float(ev.get("volume24hr") or 0)
        mkts = ev.get("markets") or []

        if ev.get("negRisk") and len(mkts) >= 2 and vol_ev >= min_vol_usd:
            active_yes = []
            for m in mkts:
                if m.get("closed") or not m.get("active", True):
                    continue
                try:
                    raw_p = m.get("outcomePrices")
                    prices = json.loads(raw_p) if isinstance(raw_p, str) else (raw_p or [])
                    if len(prices) >= 1:
                        active_yes.append((m.get("groupItemTitle") or m.get("question", "")[:40], float(prices[0])))
                except Exception:
                    continue
            if len(active_yes) >= 2:
                yes_sum = round(sum(p for _, p in active_yes), 4)
                edge_pct = round((1.0 - yes_sum) * 100.0, 2)
                if yes_sum < 0.992 or yes_sum > 1.015:
                    negrisk_arbs.append({
                        "event": title,
                        "url": f"https://polymarket.com/event/{slug}" if slug else "",
                        "outcomes_count": len(active_yes),
                        "yes_sum": yes_sum,
                        "raw_edge_pct": edge_pct,
                        "direction": "BUY_ALL_YES" if yes_sum < 1.0 else "SELL_OVERPRICED_YES",
                        "vol_24h_usd": round(vol_ev, 2),
                    })

        for m in mkts:
            if m.get("closed") or not m.get("active", True):
                continue
            mvol = float(m.get("volume24hr") or 0)
            if mvol < min_vol_usd:
                continue
            end_str = str(m.get("endDate") or "")
            if not end_str:
                continue
            try:
                end_ts = datetime.fromisoformat(end_str.replace("Z", "+00:00")).timestamp()
                days_left = (end_ts - now) / 86400.0
                if days_left < 0.5 or days_left > 35.0:
                    continue
                raw_p = m.get("outcomePrices")
                prices = json.loads(raw_p) if isinstance(raw_p, str) else (raw_p or [])
                if len(prices) != 2:
                    continue
                p_yes, p_no = float(prices[0]), float(prices[1])
                top_side, top_px = ("YES", p_yes) if p_yes >= p_no else ("NO", p_no)
                if 0.88 <= top_px <= 0.988:
                    raw_ret = (1.0 - top_px) / top_px
                    ann_apr = round(raw_ret * (365.0 / days_left) * 100.0, 2)
                    short_bonds.append({
                        "question": m.get("question", title),
                        "side": top_side,
                        "price": round(top_px, 4),
                        "days_to_expiry": round(days_left, 1),
                        "gross_return_pct": round(raw_ret * 100.0, 2),
                        "annualized_apr_pct": ann_apr,
                        "vol_24h_usd": round(mvol, 2),
                        "url": f"https://polymarket.com/event/{slug}" if slug else "",
                    })
            except Exception:
                continue

    negrisk_arbs.sort(key=lambda x: abs(x["raw_edge_pct"]), reverse=True)
    short_bonds.sort(key=lambda x: x["annualized_apr_pct"], reverse=True)
    return {
        "observed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "events_scanned": len(events),
        "negrisk_sum_deviations": negrisk_arbs[:10],
        "short_dated_high_prob_bonds": short_bonds[:12],
    }


def fetch_polymarket_opportunities(limit_events: int = 40, min_vol_usd: float = 10_000.0):
    url = f"{POLY_EVENTS_URL}?active=true&closed=false&order=volume24hr&ascending=false&limit={limit_events}"
    events = _http_json(url)
    return analyze_polymarket_events(events, min_vol_usd=min_vol_usd)


def update_paper_portfolio(ledger_path: str, funding_snapshot: dict, virtual_equity: float = 1000.0, max_positions: int = 3, min_entry_apr: float = 25.0, exit_apr: float = 8.0, rt_fee_bps: float = DEFAULT_CROSS_VENUE_RT_BPS):
    """
    Maintain a realistic delta-neutral cross-venue funding paper portfolio on disk.
    - Deducts half of round-trip taker fee on open and half on close.
    - Accrues real funding spread cashflow strictly over real wall-clock elapsed hours.
    - Zero real funds risked; strictly empirical strategy validation.
    """
    now_ts = datetime.now(timezone.utc).timestamp()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if os.path.exists(ledger_path):
        with open(ledger_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    else:
        state = {
            "created_utc": now_iso,
            "initial_equity_usd": virtual_equity,
            "cash_usd": virtual_equity,
            "realized_pnl_usd": 0.0,
            "total_fees_paid_usd": 0.0,
            "total_funding_accrued_usd": 0.0,
            "open_positions": {},
            "closed_trades": [],
            "snapshots_count": 0,
        }

    by_sym = {r["symbol"]: r for r in funding_snapshot.get("top_cross_venue_arb", [])}
    for r in funding_snapshot.get("top_single_hl_funding", []):
        by_sym.setdefault(r["symbol"], r)

    # 1. Accrue real-time funding & check exit threshold on open positions
    to_close = []
    for sym, pos in state["open_positions"].items():
        elapsed_h = max(0.0, (now_ts - pos["last_mark_ts"]) / 3600.0)
        cur = by_sym.get(sym)
        cur_spread_apr = 0.0
        if cur and cur.get("best_cross_arb"):
            arb = cur["best_cross_arb"]
            if arb["long_venue"] == pos["long_venue"] and arb["short_venue"] == pos["short_venue"]:
                cur_spread_apr = arb["spread_apr_pct"]
            elif arb["long_venue"] == pos["short_venue"] and arb["short_venue"] == pos["long_venue"]:
                cur_spread_apr = -arb["spread_apr_pct"]
        accrued = pos["notional_usd"] * (cur_spread_apr / 100.0) * (elapsed_h / (365.0 * 24.0))
        pos["accrued_funding_usd"] = round(pos["accrued_funding_usd"] + accrued, 6)
        pos["last_mark_ts"] = now_ts
        pos["last_mark_utc"] = now_iso
        pos["last_spread_apr_pct"] = cur_spread_apr
        state["total_funding_accrued_usd"] = round(state["total_funding_accrued_usd"] + accrued, 6)
        if cur_spread_apr < exit_apr:
            to_close.append((sym, f"spread dropped to {cur_spread_apr}% < {exit_apr}%"))

    half_fee_rate = (rt_fee_bps / 2.0) / 10000.0
    for sym, reason in to_close:
        pos = state["open_positions"].pop(sym)
        exit_fee = round(pos["notional_usd"] * half_fee_rate, 6)
        net_pnl = round(pos["accrued_funding_usd"] - pos["entry_fee_usd"] - exit_fee, 6)
        state["cash_usd"] = round(state["cash_usd"] + pos["margin_usd"] + pos["accrued_funding_usd"] - exit_fee, 6)
        state["total_fees_paid_usd"] = round(state["total_fees_paid_usd"] + exit_fee, 6)
        state["realized_pnl_usd"] = round(state["realized_pnl_usd"] + net_pnl, 6)
        pos["closed_utc"] = now_iso
        pos["exit_fee_usd"] = exit_fee
        pos["net_pnl_usd"] = net_pnl
        pos["close_reason"] = reason
        state["closed_trades"].append(pos)

    # 2. Open new paper positions up to max_positions on high-spread liquid pairs
    for row in funding_snapshot.get("top_cross_venue_arb", []):
        if len(state["open_positions"]) >= max_positions:
            break
        sym = row["symbol"]
        arb = row["best_cross_arb"]
        if sym in state["open_positions"] or arb["spread_apr_pct"] < min_entry_apr:
            continue
        alloc = round(state["initial_equity_usd"] / max_positions, 2)
        if state["cash_usd"] < alloc:
            continue
        entry_fee = round(alloc * half_fee_rate, 6)
        state["cash_usd"] = round(state["cash_usd"] - alloc - entry_fee, 6)
        state["total_fees_paid_usd"] = round(state["total_fees_paid_usd"] + entry_fee, 6)
        state["open_positions"][sym] = {
            "symbol": sym,
            "opened_utc": now_iso,
            "last_mark_utc": now_iso,
            "last_mark_ts": now_ts,
            "long_venue": arb["long_venue"],
            "short_venue": arb["short_venue"],
            "entry_spread_apr_pct": arb["spread_apr_pct"],
            "last_spread_apr_pct": arb["spread_apr_pct"],
            "breakeven_hours": arb["breakeven_hours"],
            "margin_usd": alloc,
            "notional_usd": alloc,  # 1x conservative delta-neutral sizing
            "entry_fee_usd": entry_fee,
            "accrued_funding_usd": 0.0,
        }

    open_margin = sum(p["margin_usd"] for p in state["open_positions"].values())
    open_accrued = sum(p["accrued_funding_usd"] for p in state["open_positions"].values())
    est_exit_fees = sum(p["notional_usd"] * half_fee_rate for p in state["open_positions"].values())
    mtm_equity = round(state["cash_usd"] + open_margin + open_accrued - est_exit_fees, 4)

    state["last_updated_utc"] = now_iso
    state["snapshots_count"] = state.get("snapshots_count", 0) + 1
    state["mark_to_market_equity_usd"] = mtm_equity
    state["net_return_pct"] = round(((mtm_equity - state["initial_equity_usd"]) / state["initial_equity_usd"]) * 100.0, 4)

    os.makedirs(os.path.dirname(os.path.abspath(ledger_path)), exist_ok=True)
    with open(ledger_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return state


def format_digest(funding: dict, poly: dict) -> str:
    lines = [
        f"Quant Radar Snapshot ({funding['observed_utc']})",
        "",
        "Top Cross-Venue Delta-Neutral Funding Spreads (Hyperliquid / Binance / Bybit):",
    ]
    for r in funding["top_cross_venue_arb"][:5]:
        a = r["best_cross_arb"]
        lines.append(
            f"- {r['symbol']}: {a['spread_apr_pct']:+.1f}% APR "
            f"(Long {a['long_venue']} {a['long_apr_pct']:+.1f}% / Short {a['short_venue']} {a['short_apr_pct']:+.1f}%) "
            f"| BE={a['breakeven_hours']}h | OI=${r['oi_usd']/1e6:.1f}M"
        )
    lines.append("")
    lines.append("Top Polymarket Short-Dated High-Probability Yields (<=35d, vol>=$10k):")
    for b in poly["short_dated_high_prob_bonds"][:5]:
        lines.append(
            f"- [{b['side']} @{b['price']:.3f} | {b['days_to_expiry']}d | {b['annualized_apr_pct']:.1f}% APR] {b['question'][:75]}"
        )
    if poly["negrisk_sum_deviations"]:
        lines.append("")
        lines.append("Polymarket NegRisk Sum-to-1 Deviations:")
        for nr in poly["negrisk_sum_deviations"][:3]:
            lines.append(f"- {nr['event'][:65]} | sum={nr['yes_sum']} ({nr['raw_edge_pct']:+.2f}% {nr['direction']})")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="quant-radar-cli — Crypto Funding & Polymarket Arbitrage Scanner")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_f = sub.add_parser("funding")
    p_f.add_argument("--min-oi", type=float, default=500_000.0)
    p_f.add_argument("--min-vol", type=float, default=1_000_000.0)
    p_f.add_argument("--rt-fee-bps", type=float, default=DEFAULT_CROSS_VENUE_RT_BPS)

    p_p = sub.add_parser("polymarket")
    p_p.add_argument("--limit", type=int, default=40)
    p_p.add_argument("--min-vol", type=float, default=10_000.0)

    p_sim = sub.add_parser("paper")
    p_sim.add_argument("--ledger", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_ledger.json"))
    p_sim.add_argument("--equity", type=float, default=1000.0)
    p_sim.add_argument("--min-apr", type=float, default=25.0)
    p_sim.add_argument("--exit-apr", type=float, default=8.0)

    p_d = sub.add_parser("digest")
    p_d.add_argument("--json", action="store_true")

    args = p.parse_args()
    if args.cmd == "funding":
        print(json.dumps(fetch_hyperliquid_funding(args.min_oi, args.min_vol, args.rt_fee_bps), ensure_ascii=False, indent=2))
    elif args.cmd == "polymarket":
        print(json.dumps(fetch_polymarket_opportunities(args.limit, args.min_vol), ensure_ascii=False, indent=2))
    elif args.cmd == "paper":
        snap = fetch_hyperliquid_funding()
        st = update_paper_portfolio(args.ledger, snap, virtual_equity=args.equity, min_entry_apr=args.min_apr, exit_apr=args.exit_apr)
        print(json.dumps(st, ensure_ascii=False, indent=2))
    elif args.cmd == "digest":
        f_snap = fetch_hyperliquid_funding()
        p_snap = fetch_polymarket_opportunities()
        if args.json:
            print(json.dumps({"funding": f_snap, "polymarket": p_snap}, ensure_ascii=False, indent=2))
        else:
            print(format_digest(f_snap, p_snap))


if __name__ == "__main__":
    main()

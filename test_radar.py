import json
import os
import shutil
import sys
import tempfile
import time

os.environ.pop("PYTHONHOME", None)
os.environ.pop("PYTHONPATH", None)

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import radar  # noqa: E402

print("1. Unit test annualize_rate & calc_breakeven_hours...")
assert round(radar.annualize_rate(0.0001, 1.0), 2) == 87.6
assert round(radar.annualize_rate(0.0004, 4.0), 2) == 87.6
assert radar.calc_breakeven_hours(87.6, 18.0) == 18.0
assert radar.calc_breakeven_hours(0.0, 18.0) == float("inf")
print("  Math OK")

print("2. Unit test Polymarket NegRisk sum-to-1 & short-dated bond analyzer...")
now_ts = time.time()
mock_events = [
    {
        "title": "Mock Rate Decision",
        "slug": "mock-rate-decision",
        "negRisk": True,
        "volume24hr": 250000,
        "markets": [
            {"question": "Cut 25bps?", "groupItemTitle": "Cut 25", "active": True, "closed": False, "outcomePrices": '["0.30", "0.70"]', "volume24hr": 120000, "endDate": "2026-12-09T00:00:00Z"},
            {"question": "Hold?", "groupItemTitle": "Hold", "active": True, "closed": False, "outcomePrices": '["0.65", "0.35"]', "volume24hr": 130000, "endDate": "2026-12-09T00:00:00Z"},
        ],
    },
    {
        "title": "Short Bond Event",
        "slug": "short-bond-event",
        "negRisk": False,
        "volume24hr": 90000,
        "markets": [
            {"question": "Will X stay above Y by Dec 5?", "active": True, "closed": False, "outcomePrices": '["0.95", "0.05"]', "volume24hr": 90000, "endDate": "2026-12-05T00:00:00Z"},
        ],
    },
]
pm_res = radar.analyze_polymarket_events(mock_events, now_ts=now_ts, min_vol_usd=10000)
assert len(pm_res["negrisk_sum_deviations"]) == 1 and pm_res["negrisk_sum_deviations"][0]["yes_sum"] == 0.95
assert len(pm_res["short_dated_high_prob_bonds"]) == 1 and pm_res["short_dated_high_prob_bonds"][0]["side"] == "YES"
print("  Polymarket analyzer OK")

print("3. Unit test persistent paper-trading ledger open -> accrue -> close...")
tmp_dir = tempfile.mkdtemp(prefix="quant_radar_test_")
try:
    ledger = os.path.join(tmp_dir, "ledger.json")
    snap_open = {
        "top_cross_venue_arb": [
            {"symbol": "TEST", "best_cross_arb": {"long_venue": "BybitPerp", "short_venue": "HlPerp", "spread_apr_pct": 120.0, "breakeven_hours": 13.14}}
        ],
        "top_single_hl_funding": [],
    }
    st1 = radar.update_paper_portfolio(ledger, snap_open, virtual_equity=900.0, max_positions=3, min_entry_apr=25.0, exit_apr=8.0)
    assert "TEST" in st1["open_positions"] and st1["total_fees_paid_usd"] > 0
    # Verify a held symbol outside top_cross_venue_arb[:12] is still marked via all_cross_venue_by_symbol
    st1["open_positions"]["TEST"]["last_mark_ts"] -= 12 * 3600
    with open(ledger, "w", encoding="utf-8") as f:
        json.dump(st1, f)
    snap_mid = {
        "top_cross_venue_arb": [],
        "top_single_hl_funding": [],
        "all_cross_venue_by_symbol": {
            "TEST": {"symbol": "TEST", "best_cross_arb": {"long_venue": "BybitPerp", "short_venue": "HlPerp", "spread_apr_pct": 40.0, "breakeven_hours": 39.42}}
        },
    }
    st_mid = radar.update_paper_portfolio(ledger, snap_mid, virtual_equity=900.0, max_positions=3, min_entry_apr=25.0, exit_apr=8.0)
    assert "TEST" in st_mid["open_positions"] and st_mid["open_positions"]["TEST"]["accrued_funding_usd"] > 0
    # Simulate 24h elapsed and spread collapsing below exit_apr
    st_mid["open_positions"]["TEST"]["last_mark_ts"] -= 24 * 3600
    with open(ledger, "w", encoding="utf-8") as f:
        json.dump(st_mid, f)
    snap_close = {
        "top_cross_venue_arb": [
            {"symbol": "TEST", "best_cross_arb": {"long_venue": "BybitPerp", "short_venue": "HlPerp", "spread_apr_pct": 2.0, "breakeven_hours": 788.4}}
        ],
        "top_single_hl_funding": [],
    }
    st2 = radar.update_paper_portfolio(ledger, snap_close, virtual_equity=900.0, max_positions=3, min_entry_apr=25.0, exit_apr=8.0)
    assert "TEST" not in st2["open_positions"] and len(st2["closed_trades"]) == 1
    assert st2["closed_trades"][0]["exit_fee_usd"] > 0
    print("  Paper-trading lifecycle OK: closed net_pnl=", st2["closed_trades"][0]["net_pnl_usd"])
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)

print("4. Live API smoke test (Hyperliquid + Polymarket)...")
live_f = radar.fetch_hyperliquid_funding()
assert live_f["liquid_markets_scanned"] >= 20 and len(live_f["top_cross_venue_arb"]) >= 5, live_f
live_p = radar.fetch_polymarket_opportunities(limit_events=25)
assert live_p["events_scanned"] >= 10, live_p
digest = radar.format_digest(live_f, live_p)
assert "Top Cross-Venue Delta-Neutral Funding Spreads" in digest
print(f"  Live OK: HL liquid={live_f['liquid_markets_scanned']} | top_spread={live_f['top_cross_venue_arb'][0]['symbol']} {live_f['top_cross_venue_arb'][0]['best_cross_venue' if False else 'best_cross_arb']['spread_apr_pct']}% APR | Poly events={live_p['events_scanned']}")
print("QUANT_RADAR_ALL_TESTS_PASS")

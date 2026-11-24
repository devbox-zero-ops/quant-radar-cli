# quant-radar-cli

Zero-dependency Python CLI for real-time **cross-venue crypto perpetual funding arbitrage** (Hyperliquid / Binance / Bybit), **Polymarket NegRisk & short-dated bond scanning**, and **fee-aware delta-neutral paper trading**.

- **Zero external dependencies** — runs on standard library Python 3.8+ (`urllib`, `json`).
- **Zero API keys required** — queries public read-only Hyperliquid Mainnet & Polymarket Gamma APIs.
- **Fee-adjusted math** — automatically computes round-trip taker fee break-even hours and liquidity filters (`min_oi`, `min_vol`).
- **Persistent paper-trading ledger** — tracks virtual positions, entry/exit fees, real elapsed hourly funding accrual, rollover exit hysteresis (`--confirm-exit-ticks`), immediate negative sign-inversion stop-loss (`--emergency-exit-apr`), and extreme spike filtering (`--max-entry-apr`) before committing live capital.
- **Anti-spam Webhook & Telegram alerting (`notify`)** — filters high-spread funding & Polymarket signals with configurable per-key cooldown state files for 24/7 cron monitoring.

## Quick Start

```bash
# 1. Scan cross-venue funding spreads (Hyperliquid vs Binance vs Bybit)
python radar.py funding --min-oi 500000 --min-vol 1000000

# 2. Scan Polymarket NegRisk sum-to-1 deviations & short-dated high-probability yields
python radar.py polymarket --limit 40 --min-vol 10000

# 3. Print a concise human-readable market digest (great for cron / Telegram channels)
python radar.py digest

# 4. Run persistent delta-neutral paper-trading simulation ($0 real funds)
#    Includes rollover hysteresis, sign-inversion stop-loss, and spike-regime filter
python radar.py paper --equity 1000 --min-apr 25 --max-entry-apr 500 --exit-apr 8 --emergency-exit-apr -25 --confirm-exit-ticks 2

# 5. Preview or dispatch threshold alerts with 60-minute anti-spam cooldown (Webhook / Telegram)
python radar.py notify --min-spread-apr 60 --max-breakeven-hours 36 --cooldown-min 60 --dry-run
# Live delivery via env vars (Discord/Slack/custom webhook or Telegram Bot API):
# QUANT_RADAR_WEBHOOK="https://..." python radar.py notify --min-spread-apr 60
# TELEGRAM_BOT_TOKEN="..." TELEGRAM_CHAT_ID="..." python radar.py notify --min-spread-apr 60
```

## Engineering Notes

- [Why 4h Funding Rollovers Break Cross-Exchange Perp Arbitrage Bots (and a Pure-Python Fix)](https://dev.to/devboxzeroops/why-4h-funding-rollovers-break-cross-exchange-perp-arbitrage-bots-and-a-pure-python-fix-4elc) — empirical breakdown of `:00` settlement baseline resets, missing-quote protection, and sign-inversion stop-loss design.

## Verify Locally

```bash
python test_radar.py
```

## Related Zero-Tracking Tools & Commercial Support

- **Browser DeFi Calculator (IL V2/V3, APY, Position Sizing)**: [ChainCalc Zero](https://devbox-zero-ops.github.io/chaincalc-zero/)
- **Multi-Chain USDT/USDC Monitor CLI**: [wallet-watch-cli](https://github.com/devbox-zero-ops/wallet-watch-cli)
- **Full 8-Tool White-Label Bundle (5 USDT / ¥29)**: [XiaheAI ZeroSuite Pro](https://devbox-zero-ops.github.io/xiaheai-hub/pro.html)
- **All Free Local Web Tools**: [XiaheAI Hub](https://devbox-zero-ops.github.io/xiaheai-hub/)
- **Custom Quantitative Bots / VPS Alert Channels (USDT / USDC)**: `chenweiyi0827@gmail.com`

## License

MIT License — see [LICENSE](./LICENSE).

# quant-radar-cli

Zero-dependency Python CLI for real-time **cross-venue crypto perpetual funding arbitrage** (Hyperliquid / Binance / Bybit), **Polymarket NegRisk & short-dated bond scanning**, and **fee-aware delta-neutral paper trading**.

- **Zero external dependencies** — runs on standard library Python 3.8+ (`urllib`, `json`).
- **Zero API keys required** — queries public read-only Hyperliquid Mainnet & Polymarket Gamma APIs.
- **Fee-adjusted math** — automatically computes round-trip taker fee break-even hours and liquidity filters (`min_oi`, `min_vol`).
- **Persistent paper-trading ledger** — tracks virtual positions, entry/exit fees, real elapsed hourly funding accrual, and mark-to-market net return before committing live capital.

## Quick Start

```bash
# 1. Scan cross-venue funding spreads (Hyperliquid vs Binance vs Bybit)
python radar.py funding --min-oi 500000 --min-vol 1000000

# 2. Scan Polymarket NegRisk sum-to-1 deviations & short-dated high-probability yields
python radar.py polymarket --limit 40 --min-vol 10000

# 3. Print a concise human-readable market digest (great for cron / Telegram channels)
python radar.py digest

# 4. Run persistent delta-neutral paper-trading simulation ($0 real funds)
python radar.py paper --equity 1000 --min-apr 25 --exit-apr 8
```

## Verify Locally

```bash
python test_radar.py
```

## Related Zero-Tracking Tools & Commercial Support

- **Browser DeFi Calculator (IL V2/V3, APY, Position Sizing)**: [ChainCalc Zero](https://devbox-zero-ops.github.io/chaincalc-zero/)
- **Multi-Chain USDT/USDC Monitor CLI**: [wallet-watch-cli](https://github.com/devbox-zero-ops/wallet-watch-cli)
- **Full 7-Tool White-Label Bundle (5 USDT / ¥29)**: [XiaheAI ZeroSuite Pro](https://devbox-zero-ops.github.io/xiaheai-hub/pro.html)
- **Custom Quantitative Bots / VPS Alert Channels (USDT / USDC)**: `chenweiyi0827@gmail.com`

## License

MIT License — see [LICENSE](./LICENSE).

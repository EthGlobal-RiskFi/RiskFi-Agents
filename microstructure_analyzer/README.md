# Market Microstructure Analyzer (drop‑in scripts)

This folder contains a Python implementation of the **Market Microstructure** module described in your spec. It is Uniswap v3–first, modular, and testable.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run (example)

```bash
python -m microstructure.runner \

  --rpc $RPC_URL \

  --chain-id 1 \

  --subgraph https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3 \

  --base 0xC02aaA39b223FE8D0A0E5C4F27eAD9083C756Cc2 \

  --quote 0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48
```

*Use your chain's correct subgraph URL. For Polygon/Arbitrum/etc., pass the corresponding v3 subgraph.*

## What it does

1. **Discover pools** for the base/quote pair and choose the best by fee tier and volume.

2. **Read core state** (`slot0`, liquidity, fee, tick spacing) on-chain.

3. **Fetch initialized ticks** in a window around the active tick via subgraph.

4. **Simulate depth to ±2/5/10% moves** segment‑wise across ticks.

5. **Compute a slippage curve** for realistic quote‑side trade sizes.

6. **Detect liquidity cliffs** and estimate the active liquidity ratio.

7. **Sample active LP positions** and compute concentration metrics.

8. **Estimate cross‑venue spread** (placeholder; extend with other venues).

9. **MEV exposure proxy** from depth and small‑trade impact.

10. **Score** into a `microstructure_score` with human‑readable reasons.

## Notes

* The swap simulator uses unscaled `sqrtP` (i.e., `sqrtPriceX96 / 2^96`) and the standard v3 math: `Δy = L(√P' − √P)`, `Δx = L(1/√P' − 1/√P)` per constant‑L segment.

* Fees are applied on the **input leg** by gross‑up: required input = effective / (1 − fee).

* Down‑move notional is reported in **quote terms** by multiplying base input by the start mid — a standard, transparent approximation.

* Subgraph schemas differ; tick/position queries are written to tolerate common variants.

## Extend

* Add Uniswap v2/Sushi/Curve discovery for **cross‑venue spread**.

* Plug a sandwich dataset (EigenPhi or internal) into `mev_proxy.py`.

* Replace the down‑move notional approximation with an integral of price along the path if desired.

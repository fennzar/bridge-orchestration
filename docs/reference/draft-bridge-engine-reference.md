Zephyr Bridge Engine: Imporant reference

  An arbitrage and liquidity management bot for the Zephyr Protocol. It monitors price discrepancies across three venues (EVM/Uniswap
  V4, native Zephyr chain, CEX/MEXC), executes profitable trades with risk controls, and manages liquidity positions.

  ---
  4 Strategies

  ┌─────┬────────────┬───────────┬─────────────────────────────────────┬─────────────────────────────────────────────────────────────┐
  │  #  │  Strategy  │    ID     │                File                 │                           Purpose                           │
  ├─────┼────────────┼───────────┼─────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
  │ 1   │ Arbitrage  │ arb       │ src/domain/strategies/arbitrage.ts  │ Cross-venue price discrepancy trading across 8+ routes (EVM │
  │     │            │           │                                     │  ↔ native ↔ CEX)                                            │
  ├─────┼────────────┼───────────┼─────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
  │ 2   │ Rebalancer │ rebalance │ src/domain/strategies/rebalancer.ts │ Maintains target asset allocation across venues (e.g. ZEPH: │
  │     │            │           │                                     │  30% EVM, 50% native, 20% CEX)                              │
  ├─────┼────────────┼───────────┼─────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
  │ 3   │ Peg Keeper │ peg       │ src/domain/strategies/pegkeeper.ts  │ Monitors ZSD's $1.00 peg on EVM pools — sells ZSD on        │
  │     │            │           │                                     │ premium, buys on discount                                   │
  ├─────┼────────────┼───────────┼─────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
  │ 4   │ LP Manager │ lp        │ src/domain/strategies/lpmanager.ts  │ Manages Uniswap V4 liquidity positions — range monitoring,  │
  │     │            │           │                                     │ fee collection, repositioning                               │
  └─────┴────────────┴───────────┴─────────────────────────────────────┴─────────────────────────────────────────────────────────────┘

  ---
  Strategy Details

  1. Arbitrage — The largest strategy (~20 supporting files in src/domain/arbitrage/). Detects price gaps, builds multi-leg execution
  plans, and clips trades with RR-aware sizing (e.g. $500 ZEPH, $1000 ZSD default clips). Supports native close and CEX close paths. Has
   spot/MA spread safety checks requiring manual approval if spot deviates >500bps from moving average.

  2. Rebalancer — Triggers when venue allocation drifts >10 percentage points from target. Actions include wrap/unwrap (bridge),
  deposit/withdraw (CEX), and same-venue swaps. Caps movements at 25% of venue balance per cycle. Auto-executes only in normal RR mode.

  3. Peg Keeper — Thresholds widen by RR mode: normal (30bps min), defensive (100bps), crisis (300bps). Dynamic clip sizing: $500 base,
  scaling to $2000 at >200bps deviation.

  4. LP Manager — Tracks active positions in Postgres via Prisma. Range configs tighten/widen by RR mode (e.g. ZSD normal: $0.98–$1.02,
  crisis: $0.50–$1.10). Auto-collects fees when >$10 accumulated.

  ---
  Common Interface

  All strategies implement the same interface: evaluate() → returns opportunities, buildPlan() → converts to executable steps,
  shouldAutoExecute() → determines if manual approval needed. Registered in a strategy registry, selected via CLI flags like
  --strategies arb,peg.








understanding and testing the engine is a mammoth but critical task. 
we have to understand how to test each strategy in isolation; and how we can use the bridge orchestration system in devnet to do this.

We have to check every case. I.e. for the arb:
we have evm premium and evm discount cases. 
task: List out all the cases!

We also have to consider inventory management as a whole; does this work? 

Critical zephyr protocol restriction handling:
task: In different RR levels; certain actions are restricted. List these out!


Liquidity management/pegs.

We have several LPs; and they arent all typical.
wzsd/usdt - stable rail into zephyr ecosystem
wzeph/wzsd - "normal" market; floating. (just <400% RR we cant mint any zsd.n)

Difficult ones:
wzys/wzsd - this is a growth stable. (yielding stable from zsd yield) 
ZYS has a native price that only goes up slowly in zsd. (1.00 zsd -> 1.80 zsd in 14 months) Pegging this is tricky!
Can only get zys by zsd -> zys conversion. So the zsd can be gated out due <400% RR.

wzrs/wzeph: can float but is restricted redeeming <400% RR and minting restricted >800% RR.
How we manage this LP is hard and critical. When its between 400-800 its easy; there are no restrictions; we can freely mint and redeem to peg the lp price to the native price
(arb pathing is just through the native wallet and bridge wrap/unwraps).
But when RR > 800% there could be a ZRS shortage
- Price we ask for it on the LP needs to be intentially expensive because we cannot replenish until RR drops back below 400%. 
When RR < 400% its not redeemable; so we have to buy it up at a steeper and steeper discount as we take on risk until the RR recovers.


When we are "close" to the 400 and 800 RR places; we can intitute some leeway around loose restrictions until liquidity get more and more scarce. Evenually we have to increase the pool fee or set our liquidity in such a way as we are selling at an ever increasing premium or buying at ever increasing discount. In some ways the liquidity pools have a bit of this baked in but we need to find what will work the best.







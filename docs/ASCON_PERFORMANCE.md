# ASCON performance repair

The merged baseline executed the full public matrix, but averaged **816.05 USDC behind the starter** and won only **19 of 60** cases. Execution success did not establish competitive performance.

## Defects and changes

- The official starting basket is about 66% base assets, while the old limits admitted only 50% total and 30% per asset. This blocked replenishment from the outset. Limits now admit the supplied basket, while keeping cash reserves, independent funding and bounded exposure.
- The SDK's recent-outcome ring does not age when an agent is idle. The old revert pause could therefore never recover (224 idle blocks in crash-101). Recovery now waits 12 blocks and permits a profitable, 100-USDC probe, with the same spacing if failures persist.
- The final eight blocks previously forced sales below reference value, even though remaining spot inventory is marked. Closing mode now permits profitable reductions only. Drawdown emergency exits remain; they select the best price relative to reference rather than nearly equal rounded notionals.
- The old 0.1-gwei tip put the candidate after market flow. The bid now responds to the observed auction, capped by three times the default, the observed limit and 2 gwei. Oracle bids cannot trigger an unbounded fee.
- Reserve-free Balancer quotes previously limited WETH trades to 0.1 WETH. The pinned official 50/50 pools and 30-bps fee allow depth inference from both executable probes. A 10% depth discount, 0.1% reserve-input cap, maximum probe multiple and size impact estimate constrain extrapolation. Curve keeps its actual probe cap.
- Standalone reference bets repeatedly depleted inventory. The default strategy now seeks cross-venue pairs, funding both legs from balances already held. A pair must cover both slippage allowances, both gas estimates and an uncertainty margin. Bundles are **not atomic**: either leg can fail.

Malformed-data checks, gas reserves, drawdown control, cooldowns, maximum sizes and the official SDK pin remain enforced. No borrowing, perpetuals, raw transactions or discovered pools were added. Directional fallback remains an explicit constant for controlled comparisons and is disabled by default.

- The pinned competition chain has zero base fee, and its fee rule charges the bid. The old gas estimate added an unsupported 1 gwei. The estimate now uses the actual fee rule while keeping the conservative 350,000 gas-unit budget per leg and wallet gas reserves.

## Development evidence

[Twenty-eight full-length development runs](validation/2026-10-20-performance-development.json) compare the baseline, risk fixes, fee priority, sizing, mixed pairs, paired-only policy and the corrected gas model on calm/crash/cex-drift/whale at seed 101. These selected cases informed development and are not held-out evidence.

Paired-only exceeded holding the starting basket in all four development cases, with fewer transactions and higher P&L than mixed pairs in three cases. It still trailed the starter in three cases. Correcting gas pricing then raised mean P&L from 1,055.67 to 1,250.54 USDC across these four cases, with one mined revert versus two. This supports broader validation, not a claim of competition readiness or hidden-field ranking.

| Variant | Mean P&L | Mean vs starter | Mean vs no-op | Transactions | Reverts |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | +234.34 | -2186.81 | +63.23 | 185 | 14 |
| risk | +336.80 | -2010.74 | +165.70 | 272 | 12 |
| priority | +373.77 | -1820.90 | +202.67 | 258 | 0 |
| sizing | +826.17 | -1459.89 | +655.07 | 238 | 0 |
| paired | +1017.85 | -960.56 | +846.75 | 257 | 0 |
| pair-only | +1055.67 | -1030.87 | +884.57 | 112 | 2 |
| fee-cap | +1250.54 | -935.94 | +1079.44 | 164 | 1 |

All monetary columns are USDC per development scenario. These four deliberately selected cases are different from the full 60-case baseline; their means must not be substituted for the full-set comparison.

## Frozen validation protocol

Before the broad comparison, select paired-only with corrected gas pricing and freeze its source bytes. An earlier broad run of the pre-correction source was superseded before any additional-seed results were used. Run every published case (12 regimes × seeds 101–505), plus all 12 regimes at additional seed 606. Seed 606 was selected before paired comparisons completed and is not used for tuning. The standard seed is public in other upstream examples; it is an unused development holdout, not a secret evaluation seed.

Every case uses the pinned official duration and cadence, all official venues, unchanged starter/no-op controls, and actual Docker settings of 2 CPUs, 4 GiB RAM, no extra swap and read-only root. The workflow blanks all inference keys. Public and additional-seed aggregates require exact coverage and matching strategy/SDK hashes separately.

Reports retain P&L, within-run differences to each control, win counts, mined reverts, pre-submission failures and partial paired fills. Receipt matching uses the simulator round rather than the chain block number. A passing execution flag never substitutes for the performance comparison.

Broad validation is pending on this branch. Its results and candidate bundle will be recorded before the pull request is marked ready. No paid model call, organizer registration or competition submission is part of this repair.

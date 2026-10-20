# ASCON validation record

**The frozen candidate passed all 60 public market scenarios and the Docker
resource checks. Live LLM revisions and final submission acceptance remain unverified.**

Validated October 20, 2026. Candidate sources: repository commit
`b6ac83f7ffad985639b220c46201c036ed8b0b67`. Eris/Python SDK pin:
`e5b93b651bba2384aedfa891cecbf7b64d05b88b`.

## Full market and Docker evidence

The [market workflow](https://github.com/code-up-matrix/ASCON-AGENT/actions/runs/39347083417)
passed **60/60 scenarios**: all 12 published regimes × 5 seeds, each with the
published 360 blocks at 2 seconds per block. It deployed all seven official venues
and ran the candidate beside unchanged `my-arb-py` and no-op controls. Every agent
was frozen; the workflow used no inference keys.

All scenarios completed without early agent exits, decision errors/timeouts,
missing transaction logs, failed valuation reads or rule/gas violations. The
review also checked the live epoch and interval valuation boundaries. Actual
running containers had **2 CPUs, 4 GiB RAM, no additional swap and a read-only root**.
All 60 results matched the same candidate source hashes, images and SDK pin.

The [committed evidence](validation/2026-10-20-public-matrix.json) records per-case
P&L, source and artifact hashes, observed Docker settings, transaction outcomes
and the bundle hash. Full summaries and logs remain in the workflow's
`ascon-market-result-<regime>-<seed>` artifacts; `ascon-public-matrix-report` contains
the aggregate audit. Artifact retention is finite; the committed record preserves
the reviewed results. See [the setup guide](ASCON_SETUP.md#automated-market-and-resource-validation)
for reproduction.

These are execution checks under observed configured caps, not peak RAM
measurements or certification of organizer network isolation. The official local
Docker runner uses host networking. Full competition scoring uses other entrants
and hidden scenarios, so this three-agent test does not predict placement.

## Trading results

Across the 60 scenarios, mean economic P&L was **−33.16 USDC** per scenario.
The candidate averaged **+127.05 USDC versus no-op** and **−816.05 USDC versus the
starter**, beating them in 37/60 and 19/60 cases respectively. It is operationally
validated but does not consistently outperform the starter.

Each row below averages five seeds. Differences compare agents within the same
run using `pnlUsdc`, not the runtime's separate `netPnlUsdc` or `alphaUsdc` fields.

| Regime | Mean P&L (USDC) | Versus starter | Versus no-op |
| --- | ---: | ---: | ---: |
| calm | +196.87 | +233.27 | +214.92 |
| cdp-incident | -612.18 | -536.52 | +419.73 |
| cex-drift | +591.85 | -2,976.84 | -401.00 |
| crash | -410.81 | -1,156.63 | +0.14 |
| depeg | +145.24 | -373.38 | -134.72 |
| depeg-persist | +428.45 | +164.40 | +235.07 |
| informed-flow | +289.99 | +13.82 | +307.62 |
| launch | -23.17 | +80.86 | -2.01 |
| lending-incident | -1,006.11 | -1,279.55 | +82.43 |
| spike | -544.31 | -1,068.41 | +296.29 |
| vuln | +133.73 | -145.81 | +180.00 |
| whale | +412.50 | -2,747.74 | +326.08 |

There were **2,521 included candidate transactions: 2,406 succeeded and 115 reverted**.
Successful fills included 904 Uniswap, 538 Balancer and 964 Curve transactions.
There were also 73 pre-submission failures: 70 `Too little received` responses and
3 `BAL#507` responses. These outcomes are retained in the evidence, not hidden by
the execution pass. The crash-101 run triggered the execution-failure pause.
A successful simulator process alone is not evidence of successful fills or profit.

### Defect corrected during validation

The [earlier baseline](https://github.com/code-up-matrix/ASCON-AGENT/actions/runs/39340156274)
completed all 60 cases, but its trade logs exposed a venue integration defect.
The pinned Balancer/Curve adapters supply executable quotes without reserve fields;
the old depth check therefore prevented both venues from trading.

The fix bounds missing-reserve trades to the adapter's actual 0.1-base-unit probe,
or its USDC sell proceeds for a buy. When reserves are present, their fraction cap
still applies. Existing cash, gas, exposure, slippage and notional limits remain.
Tests cover actual adapter observation shapes and WETH/WBTC buys and sells. The
corrected candidate's full matrix above confirms successful fills on all three
venues. No return improvement is attributed solely to this fix: wall-clock order
and interactions also affect market results.

## Other completed checks

[Competition CI](https://github.com/code-up-matrix/ASCON-AGENT/actions/runs/39347089061)
and [repository CI](https://github.com/code-up-matrix/ASCON-AGENT/actions/runs/39347089063)
passed for the tested candidate.

| Check | Result |
| --- | --- |
| Python strategy, SDK protocol and result-audit tests | 65 passed on Python 3.11.16 |
| OpenRouter/AkashML configuration tests | 6 passed on Node.js 24 |
| Competition lint, formatting and types | Passed; 0 type errors/warnings |
| Official static checker | Passed across 50 staged/upstream files |
| Actual TypeScript-to-Python bridge | Decisions, compiled replacement/restoration and actual AMM observation shapes passed |
| Official improvement policy loader/parser | Synthetic replacement passed; no real model called |
| Official inference transport | Both providers passed mocked routing, authorization, token caps, usage/errors and credential-filtering checks |
| Full retained application suite | 10,855 passed, 40 skipped, 5 deselected; 93% coverage |
| Repository lint, types, import contracts, vulnerability audit and secret scan | Passed |
| Official bundle | Source bytes, license, absence of environment files and SHA-256 manifest verified |

The CI-built candidate is in `ascon-validated-candidate-input` on the market run.
Its ZIP SHA-256 is:

```text
4f3d010dd07cbcd04045e5eb18272a28bbbd129d9454b8e6a2869f48f62b1f4d
```

A later rebuild can have different ZIP metadata; verify its source hashes as well
as its own archive hash. Packaging does not constitute an accepted submission.

## Remaining readiness steps

OpenRouter/AkashML key-presence checks found neither credential configured in this
workspace. No real provider request has been made. Mocked transport and synthetic
replacement tests do not validate credentials, credits, model-generated code or
live state persistence/reversion.

1. Configure one designated competition provider and approve a specific paid
   revision run. `AGENTS.md` requires per-run spend approval with the exact command
   and a cost estimate. The [key and run guide](ASCON_SETUP.md#2-keys-which-ones-and-where)
   contains the local setup and commands. OpenRouter/AkashML support is for local
   development; the published designated services are Ollama Cloud, Anthropic API
   and OpenAI API.
2. Inspect real revision outcomes and subsequent decisions, then validate
   persistence/reversion and the accepted model configuration in Docker. A model
   declining to change code validates retention, not replacement execution. A
   connection smoke test alone does not exercise strategy revision.
3. Check the final evaluation SDK when its hash is published on October 31.
   Register the provider credential separately and submit the reviewed ZIP through
   the organizer's process. Retain the accepted artifact hash and confirmation.

No paid inference, competition registration or submission is automated by CI.

# ASCON validation record

**The repaired frozen candidate passed all 60 public scenarios and all 12 additional-seed scenarios under observed 2 CPU / 4 GiB Docker limits.** Performance improved, but the candidate still trails the starter on average. Live LLM revision and organizer acceptance remain unverified.

Validated October 20, 2026. Tested repository commit: `8cadc87a0c728ee509f77d2a4ee5a6c1a3d1ed8c`. Eris/Python SDK pin: `e5b93b651bba2384aedfa891cecbf7b64d05b88b`. Later documentation and retained-application dependency commits do not change the validated agent source hashes.

## Full market and resource evidence

The [market workflow](https://github.com/code-up-matrix/ASCON-AGENT/actions/runs/39478740739) completed the published 12 regimes × seeds 101, 202, 303, 404 and 505, plus all 12 regimes at seed 606. Each case retained the official **360 blocks at 2 seconds per block**. All seven official venues were deployed; the candidate ran beside unchanged starter and no-op controls. All agents were frozen and inference keys were blank.

Every successful case passed checks for complete block windows, valuation reads, decision errors/timeouts, early exits, transaction logging and rule/gas violations. Downloaded artifact hashes were verified; all successful cases used identical agent source hashes, SDK revision, Docker images and observed resource settings: **2 CPUs, 4 GiB RAM, no additional swap, read-only root**.

The committed [public evidence](validation/2026-10-20-performance-public.json) and [additional-seed evidence](validation/2026-10-20-performance-extra-seed.json) preserve per-case returns, execution outcomes, artifact hashes, resource settings and bundle provenance. Full logs and summaries remain in the workflow artifacts, whose retention is finite. The [previous baseline](validation/2026-10-20-public-matrix.json) remains unchanged for comparison. See [the setup guide](ASCON_SETUP.md#automated-market-and-resource-validation) for reproduction.

### Startup retry

The first spike/202 attempt stopped during the official simulator's wallet funding: it could not locate an ERC20 balance slot. It produced no agent trades or scenario summary. The initial aggregate correctly failed. That same case passed on one unchanged retry; the other 71 successful cases were retained. The final aggregate then passed exact coverage and source/SDK checks.

The evidence retains the failed attempt's log excerpt and artifact digest, both attempt identifiers, and the successful retry. No completed economic result was discarded or retried to improve a score.

These are observations of configured caps, not peak-memory measurements or certification of organizer network isolation. The official local Docker runner uses host networking.

## Trading results

The same 60 public regime/seed combinations were used before and after the repair. All monetary values below are simulated USDC per scenario, using economic `pnlUsdc` and within-run differences to controls.

| Metric | Baseline | Repaired |
| --- | ---: | ---: |
| Mean P&L (USDC) | −33.16 | +473.19 |
| Mean versus starter (USDC) | −816.05 | −292.08 |
| Mean versus no-op (USDC) | +127.05 | +633.40 |
| Wins versus starter | 19/60 | 25/60 |
| Wins versus no-op | 37/60 | 59/60 |
| Mined reverts / included transactions | 115 / 2,521 (4.56%) | 5 / 1,567 (0.32%) |
| Pre-submission failures | 73 | 11 |

The mean deficit to the starter narrowed by **64.2%**, but was not eliminated. Median candidate P&L was **+276.06 USDC** and the median difference to the starter was **−102.68 USDC**. Trending prices, lending incidents and crashes remain substantial weaknesses. Market interactions and wall-clock ordering can change the controls' results between runs; this is an observed matched-set comparison, not a claim that every difference has a single cause.

Each row below averages all five public seeds:

| Regime | Mean P&L | Versus starter | Versus no-op | Wins vs starter |
| --- | ---: | ---: | ---: | ---: |
| calm | +190.88 | +245.27 | +208.94 | 3/5 |
| cdp-incident | −567.63 | −337.56 | +464.28 | 1/5 |
| cex-drift | +1,320.61 | −2,350.97 | +327.77 | 0/5 |
| crash | −41.10 | −943.39 | +369.84 | 1/5 |
| depeg | +511.85 | +101.86 | +231.89 | 3/5 |
| depeg-persist | +520.23 | +489.24 | +326.85 | 4/5 |
| informed-flow | +731.21 | −47.24 | +748.84 | 1/5 |
| launch | +195.94 | +38.45 | +217.10 | 3/5 |
| lending-incident | −826.96 | −1,163.76 | +261.58 | 1/5 |
| spike | −484.54 | −703.87 | +356.07 | 0/5 |
| vuln | +278.13 | +310.74 | +324.41 | 5/5 |
| whale | +3,849.71 | +856.28 | +3,763.29 | 3/5 |

The candidate attempted **752 pairs**, with **16 one-leg fills**. It had **1,567 included transactions, 5 mined reverts and 11 pre-submission failures**. Successful fills occurred on Uniswap, Balancer and Curve. Paired orders are independently funded but not atomic; starting inventory and partial fills can lose value.

The [performance repair](ASCON_PERFORMANCE.md) explains the defects and the 28 controlled development runs used to choose this candidate. Those four development cases are included in the public matrix and must not be described as held out.

### Additional seed

The strategy was frozen before testing seed 606 across all 12 regimes. This seed was selected before paired comparisons completed and was not used for tuning. It is a public seed in other upstream examples, not a secret contest seed.

All **12/12** extra cases passed the execution/resource checks. Mean candidate P&L was **+121.13 USDC**; median P&L was **−79.34 USDC**. The mean difference was **−547.43 USDC versus the starter** and **+472.88 USDC versus no-op**. The candidate won **4/12** against the starter and **12/12** against no-op, with **223 included transactions, 2 mined reverts, 3 pre-submission failures and 5 partial pairs**.

These 12 cases are separate from the public 60. Their mean must not be compared to the old 60-case mean as a same-set improvement. They support execution robustness and value over holding this basket, but do not establish consistent starter outperformance.

### Interpretation of competition scoring

The [pinned official scorer](https://github.com/NyxFoundation/eris-agent-simulator/blob/e5b93b651bba2384aedfa891cecbf7b64d05b88b/core/src/scoring/deviationScore.ts) standardizes economic P&L among non-benchmark entrants **within each epoch**, then applies epoch-order weights. This report's raw-USDC means are diagnostics, not predicted contest scores. A three-agent roster, known regimes and one additional seed do not establish performance against the full field or hidden scenarios.

## Other completed checks

[Competition CI](https://github.com/code-up-matrix/ASCON-AGENT/actions/runs/39478747285) and [repository CI](https://github.com/code-up-matrix/ASCON-AGENT/actions/runs/39478747434) passed for the tested source.

| Check | Result |
| --- | --- |
| Python strategy, SDK protocol and audit tests | 84 passed on Python 3.11.16 |
| OpenRouter/AkashML configuration tests | 6 passed on Node.js 24 |
| Competition lint, formatting and types | Passed; 0 type errors/warnings |
| Official static checker | Passed across 50 staged/upstream files |
| Actual TypeScript-to-Python bridge | Paired decisions, compiled replacement/restoration and actual AMM observations passed |
| Official improvement policy and inference transport | Synthetic revision and mocked provider transport passed; no real model called |
| Retained application suite | 10,855 passed, 40 skipped, 5 deselected; 93% coverage |
| Repository lint, types, import contracts, vulnerability audit and secret scan | Passed |
| Official bundle | Agent bytes, upstream license, absence of environment files and SHA-256 verified |

### Dependency audit follow-up

The publication audit detected [GHSA-6q48-6c7w-9gw2](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2), published while the market validation was running. The retained application used certifi 2026.7.22, whose trust bundle included an affected emSign root. Its requirement and lockfile now select **certifi 2026.10.19**, the advised fixed release; no other package version changed.

The fixed package was uploaded on October 20, so a dated certifi-only cutoff admits it while the default one-week freshness rule still applies to other dependencies. Remove that dated exception on or after **October 27, 2026** to restore certifi's normal one-week delay. The competition lockfile does not contain certifi, and the validated strategy/SDK/bundle are unchanged. The existing audit suppressions were not expanded.

The [publication job](https://github.com/code-up-matrix/ASCON-AGENT/actions/runs/39530278944) verified the complete repository tree (`2751967738ea67b13150ae04e79936001ea39164`) against the locally reviewed patch before committing it. The generated lockfile also passes `uv lock --check --offline`.

The [validated candidate artifact](https://github.com/code-up-matrix/ASCON-AGENT/actions/runs/39478740739/artifacts/12291507824) contains the submission ZIP and its manifest. The **inner submission ZIP** SHA-256 is:

```text
56094304f14049cebd47d9d78c117e4f4f5ea99747b2e3a90b8ce540f64cf579
```

The outer Actions artifact has a separate digest, recorded in the evidence. Rebuilding can change ZIP metadata; verify source hashes as well as the rebuilt archive's hash. Packaging is not submission acceptance.

## Remaining readiness steps

1. Configure a supported provider and approve a specific paid revision run. `AGENTS.md` requires per-run spend approval with an exact command and cost estimate. The [key guide](ASCON_SETUP.md#2-keys-which-ones-and-where) covers OpenRouter/AkashML for local development and designated competition providers.
2. Inspect real model responses and subsequent decisions, including replacement, retention, persistence and explicit reversion in Docker. A connectivity smoke test or mocked revision is insufficient evidence for this path.
3. Verify compatibility with the organizer's final evaluation SDK, register the provider credential separately, and submit the reviewed ZIP through the official process. Retain its accepted hash and confirmation.

No paid inference, organizer registration or submission was performed by this repair.

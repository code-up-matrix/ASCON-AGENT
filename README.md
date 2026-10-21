# ASCON Agent

A Python trading agent for **NYX ASCON**, built against the official Eris simulator.
The existing forecasting application is retained; its documentation
is in [FORECASTING.md](FORECASTING.md).

**Status:** the repaired frozen candidate passed **60 public + 12 additional-seed
scenarios** under observed **2 CPU / 4 GiB Docker limits**. Public mean P&L improved
to **+473.19 simulated USDC**, while the starter still leads by **292.08 USDC**
on average. CI and bundle checks pass. Live LLM revisions and final submission
acceptance remain unverified. See [validation results](docs/ASCON_VALIDATION.md)
and [the performance repair](docs/ASCON_PERFORMANCE.md).

## Start here

Use Linux, macOS, WSL2 or a suitable development VM with Git, uv, Node.js 24 and npm.
The competition project uses Python **3.11.16**, matching the pinned official image;
the existing forecasting application keeps its separate Python 3.12+ environment.

```bash
make ascon-install
make ascon-check       # offline tests, lint, formatting and types; no keys
make ascon-prepare     # clone the pinned official runtime and stage the agent
make ascon-doctor
```

Follow [the setup and API key guide](docs/ASCON_SETUP.md) for the simulator, frozen
baseline, model revision test and submission ZIP. No API key is needed for offline
checks or frozen backtests. An improving run requires one inference provider.

Use the [official ASCON dashboard](https://ascon-dash.nyx.foundation/) for
registration, submission, practice monitoring and environment updates. The
[competition handoff checklist](docs/ASCON_SETUP.md#7-register-practice-and-submit)
covers deadlines, separate credential registration and the final evaluation SDK.

For local LLM development, store `OPENROUTER_API_KEY` and `AKASHML_API_KEY` in the
Eris checkout's `.env.local`, then use `make ascon-llm-check ARGS="--provider openrouter"`
or `--provider akashml`. Both keys can coexist. See the guide for model selection
and explicit paid smoke/backtest commands. These two providers are not listed
among the competition's designated inference services.

## Competition functionality

`eris-adaptive-v1` implements the official Python `decide(obs, ctx)` / JSONL interface:

- Independently funded WETH/USDC and WBTC/USDC trade pairs across Uniswap, Balancer
  and Curve, using executable two-sided quotes and conservative size impact.
- Fee, estimated gas, slippage and pool-depth checks before entering a position.
- Smaller entries during large price moves, cash and gas reserves, exposure limits,
  decision cooldowns and spaced small recovery probes after excessive reverted transactions.
- Profitable reductions near an epoch's end and emergency inventory reduction after a drawdown.
- An improvement policy requesting LLM strategy review every 60 blocks, using the
  official runtime's version history, memory and explicit revert mechanism.
- Separate frozen and improving rosters, an unchanged `my-arb-py` comparison agent,
  a pinned SDK/runtime, and a bundle with SHA-256 provenance.

Paired bundles fund each leg from current balances and are not atomic: either leg
can fail independently, and starting inventory can lose value. Standalone directional
entries are disabled by default. Limits were reviewed with controlled frozen comparisons;
performance on selected development cases is not proof of generalization.
The policy asks revisions to retain risk limits; that instruction is not an
independent runtime risk gate. The official runtime has no automatic rollback.

Aave borrower discovery/liquidation, atomic multi-leg arbitrage, lending and
perpetuals are not implemented in this first candidate. Reserved USDC is currently
cash, not a liquidation execution feature.

## Repository map

| Path | Purpose |
| --- | --- |
| `competition/agents/eris-adaptive-v1/` | Strategy, constants and mandatory improvement policy |
| `competition/tests/` | Offline decision and SDK protocol tests |
| `competition/rosters/` | Frozen comparison and manual improving runs |
| `competition/tools.py` | Pinned runtime setup, checks, bundle, frozen backtests and explicit local LLM commands |
| `competition/llm/` | Local OpenRouter/AkashML selection using the official inference transport |
| `competition/validation.py` | Full public-scenario, Docker-limit and result aggregation checks |
| `docs/validation/` | Reviewed scenario results and artifact/source hashes |
| `docs/ASCON_SETUP.md` | Installation, keys, local simulation and packaging |
| `docs/ASCON_VALIDATION.md` | Completed checks and remaining acceptance work |
| `FORECASTING.md` | Forecasting application guide, including optional FRED research |

The separate competition lockfile pins the SDK to the same official Eris commit as
`competition/eris.lock`. Updating it means updating both pins and rerunning the
compatibility and baseline checks. The ASCON CI workflow uses no provider secrets
and never runs paid inference or submits an entry.

## Attribution

Third-party copyright and permission notices are recorded in [LICENSE](LICENSE).
Historical forecasting results do not establish this agent's performance.
The competition integration uses
[NYX Foundation's Eris](https://github.com/NyxFoundation/eris-agent-simulator)
under its upstream license. Original licensing and attribution are retained.

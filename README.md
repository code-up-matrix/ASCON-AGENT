# ASCON Agent

A Python trading agent for **NYX ASCON**, built against the official Eris simulator.
The existing forecasting application is retained; its documentation
is in [FORECASTING.md](FORECASTING.md).

**Status:** initial implementation with offline tests and a submission packaging
workflow. Profitability, Docker resource compliance and live LLM revisions still
need simulator validation. See [validation results](docs/ASCON_VALIDATION.md).

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

For local LLM development, store `OPENROUTER_API_KEY` and `AKASHML_API_KEY` in the
Eris checkout's `.env.local`, then use `make ascon-llm-check ARGS="--provider openrouter"`
or `--provider akashml`. Both keys can coexist. See the guide for model selection
and explicit paid smoke/backtest commands. These two providers are not listed
among the competition's designated inference services.

## Competition functionality

`eris-adaptive-v1` implements the official Python `decide(obs, ctx)` / JSONL interface:

- WETH/USDC and WBTC/USDC relative-value trading across supported Uniswap, Balancer
  and Curve observations, using executable quotes when available.
- Fee, estimated gas, slippage and pool-depth checks before entering a position.
- Smaller entries during large price moves, cash and gas reserves, exposure limits,
  decision cooldowns and pauses after excessive reverted transactions.
- Inventory reduction near an epoch's end or after a drawdown.
- An improvement policy requesting LLM strategy review every 60 blocks, using the
  official runtime's version history, memory and explicit revert mechanism.
- Separate frozen and improving rosters, an unchanged `my-arb-py` comparison agent,
  a pinned SDK/runtime, and a bundle with SHA-256 provenance.

This is a single-action spot strategy. A reference-price discrepancy is not a
guaranteed arbitrage profit: the reference lags, trades can fail, and inventory
can lose value. Risk constants are starting assumptions, not fitted parameters.
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

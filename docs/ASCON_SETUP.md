# ASCON setup and API keys

This guide targets the official Eris commit recorded in `competition/eris.lock`,
currently `e5b93b651bba2384aedfa891cecbf7b64d05b88b`. Keep the SDK, simulator,
deployment state and public scenarios from the same revision when comparing runs.

Official references: [rules](https://ascon.dev/en/rules),
[competition guide](https://github.com/NyxFoundation/eris-agent-simulator/blob/e5b93b651bba2384aedfa891cecbf7b64d05b88b/docs/competition-start.md),
[Python SDK](https://github.com/NyxFoundation/eris-agent-simulator/tree/e5b93b651bba2384aedfa891cecbf7b64d05b88b/sdk-py),
and [local deployment](https://github.com/NyxFoundation/eris-agent-simulator/blob/e5b93b651bba2384aedfa891cecbf7b64d05b88b/docs/guide/local-deploy.md).

## 1. Install and run the checks that need no keys

Use Linux/macOS or WSL2 on Windows. Install Git, [uv](https://docs.astral.sh/uv/),
Node.js 24 and npm. Full market simulation also needs
[Foundry](https://getfoundry.sh/introduction/installation/) (`forge`, `anvil`),
Yarn for the official vendor setup, and Docker for the competition resource limits.
A machine must permit local processes and local socket listeners.

From this repository's root:

```bash
make ascon-install
make ascon-check
make ascon-prepare
make ascon-doctor
cd .eris/eris-agent-simulator
npm ci --ignore-scripts
```

`ascon-install` uses uv to install Python 3.11.16 and the isolated
`competition/.venv`. It does not change the forecasting application's environment.
`ascon-prepare` stages the candidate and two rosters, and creates `.env.local` with
blank credentials. It never overwrites an existing `.env.local` or a locally edited
improving roster. It refuses a different Eris revision or unexpected tracked
runtime changes (the generated local deployment address file is allowed).

After editing files under `competition/agents/`, run `make ascon-prepare` from the
repository root again to refresh the staged copy. Backtest and bundle commands
also refresh it automatically. Do not edit the staged strategy as your source.

## 2. Keys: which ones, and where

| Test or feature | Key required | Location |
| --- | --- | --- |
| Unit tests, official static checks, bundle | None | — |
| Frozen simulator baseline | None | Local Anvil test wallets are provided by Eris |
| Default improving run: Ollama Cloud | `OLLAMA_API_KEY` | `.eris/eris-agent-simulator/.env.local` |
| Alternative improving run: OpenAI | `OPENAI_API_KEY` | Same `.env.local`; change the candidate model in the improving roster |
| Alternative improving run: Anthropic | `ANTHROPIC_API_KEY` | Same `.env.local`; change the candidate model in the improving roster |
| Retained FRED economic research | `FRED_API_KEY` | Repository-root `.env`, with `FINANCIAL_DATA_ENABLED=true` |
| Hosted competition inference | One supported provider credential | Organizer's credential form, separately from the ZIP |

Only **one inference provider** is needed. The default candidate roster selects
`gpt-oss:120b` through Ollama Cloud. Create an API key in your
[Ollama account](https://ollama.com/settings/keys) and enter it locally:

```dotenv
OLLAMA_API_KEY=your_key_here
```

For an alternative provider, create a key in the
[OpenAI platform](https://platform.openai.com/api-keys) or
[Anthropic console](https://console.anthropic.com/settings/keys). In
`.eris/eris-agent-simulator/config/rosters/ascon-improving.yaml`, change the candidate's
`ERIS_LLM_MODEL` to `openai:<supported-model-id>` or the supported `claude...` model
name. The explicit roster setting takes priority over a global model environment
variable. Check the organizer's allowed provider/model list before submission;
the published provider expansion takes effect on November 1, 2026. Local SDK
support alone does not prove competition eligibility.

Keep real values out of source files, prompts, chat, logs and the ZIP. `.env.local`
is ignored by Git and excluded by the official bundler. Local Anvil wallet keys
are public test credentials: do not substitute a funded wallet. The hosted
inference gateway injects its own connection variables; do not invent gateway
tokens or embed provider keys in the agent.

FRED is optional research for the retained forecasting app. Get its key from
[FRED API keys](https://fred.stlouisfed.org/docs/api/api_key.html). The existing
point-in-time research paths are retained. FRED is not called from `decide()`:
competition observations are simulated and the strategy has no direct external
network access. Forecasting provider and Metaculus keys are not needed to test
this competition agent; see [FORECASTING.md](../FORECASTING.md) for that app.

## 3. Prepare local market state once

From `.eris/eris-agent-simulator`, follow the pinned official setup:

```bash
cp config/example.yaml config/local.yaml
npm run build:contracts
cd deployer
npm ci
forge build
cp .env.example .env
./scripts/setup-vendors.sh
```

Leave the deployment running in **terminal A**, inside the official checkout:

```bash
cd deployer
npm run deploy -- --keep-fresh
```

In **terminal B**, inside `.eris/eris-agent-simulator`:

```bash
npm run gen:local-constants
npm run gen:state-dump
```

This creates `backtest/state/manifest.json` and the matching chain state. Do not
deploy twice into the same running Anvil when rebuilding the initial state;
restart it first, as the official guide directs. None of these commands need a
model key. State dumps and deployment addresses are local artifacts.

## 4. Establish a frozen baseline before paying for revisions

From this repository's root:

```bash
make ascon-backtest ARGS="--regime calm --seed 101 --sandbox process"
make ascon-backtest ARGS="--regime crash --seed 101 --sandbox process"
```

The frozen roster compares `eris-adaptive-v1` against the unchanged official
`my-arb-py` starter and a no-op wallet. Every agent has revision disabled, including
when keys happen to exist in your environment. Process mode is useful for
debugging, but does not test Docker resource limits.

For the resource-limited run, build all three agent images inside the
official checkout:

```bash
npm run agent:build -- team noop
npm run agent:build -- team my-arb-py
npm run agent:build -- team eris-adaptive-v1
```

Then run from this repository's root:

```bash
make ascon-backtest ARGS="--regime calm --seed 101 --sandbox docker"
make ascon-backtest ARGS="--matrix --sandbox docker"
```

The public matrix contains 12 regimes × 5 seeds at the pinned revision and can
take about 12 hours. First prove one scenario works. Save each run's `summary.json`,
agent logs and transaction logs. Compare `agents[].pnlUsdc` for economic P&L;
`alphaUsdc` and `netPnlUsdc` are different measures. Check failed reads, timeouts,
early exits, reverts, violations and final inventory as well as the profit number.
Record the commit, seed, runtime pin, roster, sandbox and source hashes with results.
Deterministic inputs do not eliminate wall-clock scheduling differences.

A three-agent local ranking is not a prediction of placement in the full contest.
Do not tune solely to one calm seed or claim a gain without the unchanged starter
run on the same conditions. Public seeds may change after an official rule update.

## 5. Test the required LLM improvement path explicitly

This is the first step that can spend provider credits. Set one provider key as
above, confirm your budget, and run it manually. From `.eris/eris-agent-simulator`:

```bash
export ERIS_PYTHON="$(cd ../../competition && pwd)/.venv/bin/python"
npm run backtest -- --regime calm --seed 101 --agents config/rosters/ascon-improving.yaml --agent-sandbox process
```

Only the candidate improves; the starter and no-op remain frozen controls. The
policy schedules revision every 60 blocks: a 360-block epoch has approximately
six opportunities, and the full public matrix approximately 360. Actual requests,
tokens and costs depend on completion timing, model and provider. The prompt
caps output at 16,000 tokens and requests a 65,536-token context; these are ceilings,
not a cost estimate. Check your provider's current limits and pricing first.

Inspect revision logs to confirm authentication, model response, parse/compile and
installation, retention or explicit reversion. A simulator that finishes despite
model errors has not validated improvement. Revisions replace `strategy.py`;
`constants.py` remains available on the runtime's Python path. A revision can still
change its own risk logic. Static checks and compilation do not establish economic
safety, and the runtime does not automatically roll back losing code.

For multi-epoch memory tests, the official backtester accepts
`--agent-state-root runs/ascon-learning-state`. Use a fresh state root for a clean
experiment and keep learning-state runs separate from frozen comparisons. Repeat
the accepted model configuration in Docker before submission.

## 6. Build the reviewable ZIP

From this repository's root, after installing the official Node dependencies:

```bash
make ascon-bundle
```

This invokes the pinned official static checker, exercises the real Python bridge
with a local replacement/restoration fixture (no LLM call), then bundles and produces:

- `dist/ascon/bundle-eris-adaptive-v1.zip`
- `dist/ascon/manifest.json`, recording the runtime pin and ZIP/source SHA-256 hashes

The bundle includes the official runtime/SDK, the candidate and its improvement
policy. It does not include local credentials or the forecasting application.
The official bundler may warn about a missing `AgentERC20` artifact referenced by
its shared library. This candidate does not deploy tokens or call that helper;
build contracts first if you later add deployment functionality.
Packaging is not a simulation score or an accepted submission. Follow the current
organizer submission procedure, supply credentials through their separate form,
and retain the accepted artifact hash and confirmation. This repository does not
automatically submit or enable paid competition runs.

## Troubleshooting

- **`forge`, `anvil` or Docker missing:** install them on the simulation machine;
  offline checks and bundle creation do not require them.
- **Socket/listen permission denied:** use a host permitting local Anvil and
  Docker. A successful offline check does not remove that requirement.
- **State dump missing:** complete section 3 before calling the backtester.
- **Model key appears ignored:** check the improving roster's explicit model and
  provider prefix; the frozen roster intentionally never calls a model.
- **Eris revision mismatch:** use a fresh checkout at the recorded pin. Evaluate
  rule/runtime updates deliberately with a new baseline rather than silently
  mixing old SDK code, new scenarios and a stale state dump.
- **Original app:** use its own `uv sync --dev` and root `.env`; the competition
  virtual environment is intentionally separate.

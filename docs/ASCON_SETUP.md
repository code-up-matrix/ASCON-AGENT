# ASCON setup and API keys

This guide targets the official Eris commit recorded in `competition/eris.lock`,
currently `e5b93b651bba2384aedfa891cecbf7b64d05b88b`. Keep the SDK, simulator,
deployment state and public scenarios from the same revision when comparing runs.

Official references: [dashboard](https://ascon-dash.nyx.foundation/),
[rules](https://ascon.dev/en/rules),
[current English participant guide](https://github.com/NyxFoundation/eris-agent-simulator/blob/main/docs/competition-start.en.md),
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
`ascon-prepare` stages the candidate and three rosters, and creates `.env.local` with
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
| Local OpenRouter development | `OPENROUTER_API_KEY` | Same `.env.local`; select with `--provider openrouter` |
| Local AkashML development | `AKASHML_API_KEY` | Same `.env.local`; select with `--provider akashml` |
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
network access. Forecasting provider and platform keys are not needed to test
this competition agent; see [FORECASTING.md](../FORECASTING.md) for that app.

### OpenRouter and AkashML: store both keys, select one per run

Create your own key at [OpenRouter](https://openrouter.ai/settings/keys) and in
[AkashML Settings → API Keys](https://akashml.com/docs/getting-started/introduction).
Add these entries to `.eris/eris-agent-simulator/.env.local` in your local editor.
If that file already exists, append the entries rather than overwriting your
existing deployment settings. Do not paste actual keys into chat or commit them.

```dotenv
OPENROUTER_API_KEY=your_personal_openrouter_key
AKASHML_API_KEY=your_akashml_key
ASCON_LLM_PROVIDER=openrouter
OPENROUTER_MODEL=
AKASHML_MODEL=
```

Both model fields default to `openai/gpt-oss-120b`, listed in both providers'
catalogs on October 19, 2026. You can set different models for each provider.
Copy the exact provider model ID; do not add Eris's `openai:` routing prefix.
Check current availability and limits at
[OpenRouter models](https://openrouter.ai/models) and
[AkashML models](https://akashml.com/docs/platform/models). The revision prompt
can grow over an epoch, and its output cap is 16,000 tokens; choose a model with
enough context and output capacity. This launcher supports Chat Completions;
IDs that the pinned Eris runtime routes to Responses (`pro`/`codex`) are rejected.

From the ASCON repository root, after preparing Eris and running its `npm ci`:

```bash
# No network request or spend: validate the selection and key presence.
make ascon-llm-check ARGS="--provider openrouter"
make ascon-llm-check ARGS="--provider akashml"
```

The check prints provider, model, endpoint and key presence, never key values.
It cannot establish that the key is valid or has credits. A CLI `--provider`
overrides `ASCON_LLM_PROVIDER`; shell variables override `.env.local`. The launcher
maps only the selected provider's key to `OPENAI_API_KEY` and sets its official
endpoint in the child process. It overwrites stale `OPENAI_BASE_URL` and
`ERIS_LLM_MODEL` values there without editing your file. Do not manually alias
keys or put `${OPENROUTER_API_KEY}` into `.env.local`: Eris's loader does not expand
variable references. Missing selected keys fail; there is no fallback spend on
the other provider. The original provider keys do not pass Eris's agent-process
allowlist, and its strategy-worker filter strips the mapped key too.

When you choose to spend credits, these are **separate, manual operations**:

```bash
# ONE real model request, capped at 2,048 generated tokens including reasoning.
make ascon-llm-smoke ARGS="--provider openrouter --i-accept-spend"
make ascon-llm-smoke ARGS="--provider akashml --i-accept-spend"

# After section 3 and the frozen baseline: one improving process-sandbox epoch.
make ascon-llm-backtest ARGS="--provider openrouter --regime calm --seed 101 --i-accept-spend"
# Substitute --provider akashml to test that provider in a separate paid run.
```

Each smoke command makes one request via the actual pinned Eris LLM transport.
It reports the `ASCON_OK` marker and token usage. At the published default-model
rates on October 19, a 2,048-output-token smoke request is roughly **under $0.001**
with its short input; rates may change. Set provider spending limits. Reasoning
can exhaust the cap before returning the marker: a failed/truncated test can
still be billed. A backtest can make about six revisions in one 360-block epoch,
each with up to 16,000 output tokens and a growing input. It is a different spend
from a smoke test. This wrapper supports the local **process** sandbox only.

The local roster keeps both controls frozen and takes the candidate model from
the launcher. It is refreshed on each invocation, so keep model choices in
`.env.local`. The original `ascon-improving.yaml` still serves direct designated
providers, and `make ascon-backtest` remains entirely frozen.

**Competition eligibility:** the published revision effective November 1, 2026
names Ollama Cloud, Anthropic API and OpenAI API as designated services. Neither
OpenRouter nor AkashML is listed. API compatibility or using the same underlying
model does not establish eligibility. Use these configurations for local
development; use a designated service/model for submission unless the organizer
explicitly approves another provider. The launcher refuses a run with
`ERIS_INFERENCE_BASE_URL` set so it cannot redirect the organizer's gateway.
Provider settings and keys are outside the agent directory and the submission ZIP.

Protocol references:
[OpenRouter Chat Completions](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request),
[AkashML Chat Completions](https://akashml.com/docs/api-reference/openai/post-v1-chat-completions),
and [ASCON rules §2.5 / Appendix A](https://ascon.dev/en/rules).

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

### Automated market and resource validation

The **ASCON market validation** GitHub Actions workflow runs on competition-source
or market-workflow pushes, or manual dispatch. Documentation-only pushes do not
repeat the matrix. It deploys the pinned local economy and builds the three official
agent images. The published calm/crash smoke cases and all 12 regimes at additional
seed 606 then run in parallel. Passing both smoke cases releases the remaining
58 published regime/seed pairs. Every scenario retains its official block count and timing. The workflow
uses no inference keys; all agents are frozen.

The check fails for incomplete block windows, missing/failed valuation reads,
early agent exits, decision errors/timeouts, missing decision logs, rule or gas
violations, or missing resource evidence. During execution it inspects each
running container to confirm 2 CPUs, 4 GiB RAM with no additional swap, and a
read-only root filesystem. These are observed limits, not peak memory measurements.
The official local runner uses host networking; this check does not certify the
organizer's network isolation or live inference gateway.

Download `ascon-public-matrix-report` from the workflow run for coverage, source
hashes and economic P&L against both controls. The individual
`ascon-market-result-<regime>-<seed>` artifacts contain summaries and execution
logs. The aggregate passes only when all 60 cases pass with the same candidate
sources and runtime pin. The separate `ascon-extra-seed-report` requires all 12 regimes
at seed 606 with matching sources and SDK; its results never count toward public coverage.
Performance summaries include mean/median P&L, within-run control differences, wins,
mined reverts, pre-submission failures and partially filled pairs. Receipt outcomes
match simulator rounds, which can differ from chain block numbers. A green offline
workflow is a separate result.

On a Docker-enabled machine with deployed state and the images already built,
run the same audit from the repository root:

```bash
uv run --project competition --frozen python competition/validation.py run --regime calm --seed 101 --out dist/market/calm-101

# Additional seed; the default audit refuses non-public regime/seed combinations.
uv run --project competition --frozen python competition/validation.py run --regime calm --seed 606 --allow-extra-seed --out dist/holdout/calm-606
```

After collecting all 12 extra-seed reports under `dist/holdout`, aggregate them with:

```bash
uv run --project competition --frozen python competition/validation.py aggregate --inputs dist/holdout --seed 606 --allow-extra-seed --out dist/extra-seed-report.json
```

Use a seed that was not used for selecting changes when evaluating generalization.
Keep strategy bytes frozen across the set. See [the performance repair](ASCON_PERFORMANCE.md)
for the current selection protocol and measured results.

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

In `runs/<run-id>/agents/eris-adaptive-v1.jsonl`, inspect the actual outcome:

| Runtime event | What it establishes |
| --- | --- |
| `revision installed`, followed by successful decisions | A real model replacement compiled and ran |
| `revision reverted`, followed by successful decisions | A saved version was selected and ran again |
| `revision declined` | The model returned a valid decision to retain the current code; replacement execution remains untested |
| `revision rejected` | The call, response validation or compilation failed; inspect `state.reason` |
| `revision_resumed` | Saved state was loaded; inspect `versionsRefused`, `runningVersion` and `hasMemory` |

Record the run directory, provider/model, source hashes, successful revision
outcomes and subsequent decision errors with the test result. An `ASCON_OK`
connection smoke test alone does not exercise strategy revision. Do not treat a
short epoch as passing the upstream hourly revision-health check, which requires
more than an hour of evidence.

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

The bundle includes the official runtime/SDK, its `ERIS_LICENSE.txt` notice, the
candidate and its improvement policy. Packaging verifies the candidate bytes
against the checked source and refuses environment files. It does not include
local credentials or the forecasting application.
The official bundler may warn about a missing `AgentERC20` artifact referenced by
its shared library. This candidate does not deploy tokens or call that helper;
build contracts first if you later add deployment functionality.
Packaging is not a simulation score or an accepted submission. Follow the current
organizer submission procedure, supply credentials through their separate form,
and retain the accepted artifact hash and confirmation. This repository does not
automatically submit or enable paid competition runs.

## 7. Register, practice and submit

Checked against the [dashboard](https://ascon-dash.nyx.foundation/) and
[rules](https://ascon.dev/en/rules) on October 19, 2026. The rules take precedence
over dashboard summaries and older guide text. All dates below use **Japan
Standard Time (JST, UTC+9)**.

| Milestone | Date in 2026 |
| --- | --- |
| Registration closes | October 24 |
| Submission and practice close; agent freezes | October 31 |
| Live competition | November 1–7 |
| Optional report-track deadline | November 21 |

1. Join Discord **#ascon** through the dashboard, then use **Register**. Each team
   member completes registration; having a GitHub repository does not register you.
2. Open the separate inference-key form linked in **#ascon**. Register a designated
   provider credential there, separately from the ZIP. The announced November 1
   provider list is Ollama Cloud, Anthropic API and OpenAI API; choose a supported
   model from rules Appendix A. The local OpenRouter/AkashML configuration in
   section 2 does not register a competition credential.
3. Complete the baseline, resource-limit and approved LLM-revision checks in
   sections 4–5. Consult [validation results](ASCON_VALIDATION.md) for work still
   outstanding; a passing bundle check alone is insufficient.
4. Build the ZIP with `make ascon-bundle`, then use **Submit** on the dashboard
   (Google sign-in required). Retain the acceptance email and the matching
   `dist/ascon/manifest.json`. Up to five accepted replacements are allowed per
   JST day; the most recently accepted submission at the deadline is evaluated.

Optional practice: registered participants can run their agent locally against
the trial chain. Follow the participant guide's
[practice section](https://github.com/NyxFoundation/eris-agent-simulator/blob/main/docs/competition-start.en.md#9-the-practice-devnet-optional)
using the dashboard's published environment manifest. To appear in practice
standings, post the practice wallet's public address in **#ascon**. Practice
results do not count toward the competition score.

The [October 18 update](https://ascon-dash.nyx.foundation/updates/2026-10-18)
explains that evaluation uses only the agent directory from the ZIP, combined
with the organizer's frozen SDK/runtime. The final commit hash is due on
October 31 in rules Appendix A and Discord. When published, verify the strategy
against that SDK; `competition/eris.lock` records our local development pin,
not a confirmed final evaluation commit. An older bundled runtime alone is not
a reason for rejection or for rebuilding an already accepted ZIP.

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

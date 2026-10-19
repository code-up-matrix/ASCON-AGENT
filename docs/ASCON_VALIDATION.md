# ASCON validation record

Initial candidate: `eris-adaptive-v1`. Runtime and SDK pin:
`e5b93b651bba2384aedfa891cecbf7b64d05b88b`.

No profitability or competition acceptance claim is made.

## Checks completed on October 19, 2026

| Check | Result |
| --- | --- |
| Competition decisions and SDK JSONL tests, Python 3.11.16 | 34 passed |
| Competition Ruff checks and formatting | Passed |
| Competition basedpyright | 0 errors, 0 warnings |
| Official strategy static checker | Passed across 50 staged/upstream Python and TypeScript files |
| Actual official TypeScript-to-Python bridge | Passed: resident decisions, cooldown, compiled replacement importing the companion module, restored original source |
| Official improvement policy loader and revision parser | Passed with the candidate policy and a synthetic replacement; no LLM called |
| Official bundle creation | Passed; ZIP and source hashes recorded in the generated manifest |
| Original app Ruff, formatting, basedpyright, deptry, import contracts | Passed; 0 type errors and all six import contracts kept |
| Original app full test suite in this host | 10,807 passed, 63 skipped, 5 deselected, 6 failed and 13 setup errors on the first run |

The legacy failures were investigated without changing the forecasting code or
weakening its network guards. Rechecking the 19 affected tests with proxy variables
removed **for the mocked offline test process only** passed 16; the remaining
three source-capture tests attempt real DNS resolution for `example.org`, which
this host cannot resolve. They fail at the existing SSRF preflight before the fake
HTTP session. This is not a fully green local legacy suite; consult the PR's GitHub
Actions results for the clean-runner gate.

The first GitHub audit found four advisories in the inherited root lockfile.
`aiohttp` was updated from 3.14.3 to 3.14.4 and transitive `mcp` from 1.29.1 to
1.30.0; the resolver also updated `yarl` from 1.24.5 to 1.25.1 for compatibility.
Minimum constraints retain these fixes. The one-week freshness policy and existing
audit exclusions were not changed. See the PR checks for the audit after this update.

The bridge test supplies a deterministic synthetic observation and replacement
source. It validates the execution interface and helper imports, not a model's
judgment, persistent multi-epoch learning or on-chain fills.

The official bundler warns that its shared library references a missing
`AgentERC20` Forge artifact. The candidate does not deploy tokens or call that
helper. The ZIP must be rebuilt after compiling contracts if deployment features
are added. No credentials are part of the candidate directory or bundle.

Foundry, Anvil, Yarn and Docker were not preinstalled here. The TypeScript CLI's
IPC listener is restricted, so the checks invoke the same official source via
`node --import tsx`; local TCP binding itself is available. No complete market
backtest, Docker resource-limit test or paid model run is claimed.

## Acceptance work requiring the simulation host

1. Deploy the pinned contracts and generate a fresh state dump.
2. Run the frozen candidate and unchanged `my-arb-py` control on calm and crash,
   then the complete public matrix. Record P&L, failures and violations.
3. Validate one provider-authenticated revision, state persistence and explicit
   revert behavior, then rerun with the official Docker resource limits.
4. Evaluate results before tuning or claiming improvement. Build and review the
   final ZIP and submit through the organizer's process.

No paid inference or live competition submission is performed by the offline CI.

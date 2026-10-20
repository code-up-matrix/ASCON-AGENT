"""Run and audit the pinned public market scenarios without inference credentials.

The official backtester can exit successfully with incomplete/failed agents. This
runner inspects its evidence, observes actual Docker resource settings, and refuses
to label a partial scenario set as a completed public matrix.
"""

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
import threading
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median

import tools

AGENTS = ("noop", "my-arb-py", "eris-adaptive-v1")
SMOKE = {("calm", 101), ("crash", 101)}
MEMORY_BYTES = 4 * 1024**3
NANO_CPUS = 2_000_000_000


def read_json(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def yaml_json(checkout: Path, path: str):
    return json.loads(
        tools.command(
            [
                "node",
                "-e",
                "console.log(JSON.stringify(require('yaml').parse(require('fs').readFileSync(process.argv[1],'utf8'))))",
                path,
            ],
            checkout,
            capture=True,
        )
    )


def public_cases(checkout: Path) -> list[dict]:
    doc = yaml_json(checkout, "config/scenarios/public.yaml")
    return [{"regime": regime, "seed": seed} for regime in doc["regimes"] for seed in doc["seeds"]]


def source_hashes() -> dict[str, str]:
    agent = tools.root() / "agents" / "eris-adaptive-v1"
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(agent.iterdir()) if p.is_file()}


def assess(summary: dict, expected: dict, resources: dict, logs: dict[str, str]) -> list[str]:
    problems = []
    if summary.get("blocksProcessed") != expected["blocks"]:
        problems.append(f"incomplete block window: {summary.get('blocksProcessed')} != {expected['blocks']}")
    if summary.get("blockTimeSec") != expected["blockTimeSec"]:
        problems.append("block time differs from the official regime")
    if summary.get("valueSeries", {}).get("failedReads") != 0:
        problems.append("missing or failed valuation reads")
    for name in ("violations", "gasViolations"):
        if summary.get(name):
            problems.append(f"{name}: {len(summary[name])}")
    if summary.get("v0FloorSkipped"):
        problems.append("initial valuation boundary was not read")
    reported = summary.get("agents", [])
    if sorted(a.get("id", "") for a in reported) != sorted(AGENTS):
        problems.append("missing, duplicate or unexpected agents")
    for agent in reported:
        name = agent.get("id", "unknown")
        if agent.get("processExitedEarly") not in (None, False):
            problems.append(f"{name}: exited early")
        for key in ("pnlUsdc", "finalValueUsdc", "netPnlUsdc"):
            value = agent.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                problems.append(f"{name}: missing/non-finite {key}")
        if isinstance(agent.get("finalValueUsdc"), (int, float)) and agent["finalValueUsdc"] <= 0:
            problems.append(f"{name}: non-positive final portfolio value")
        if agent.get("unloggedTxCount", 0):
            problems.append(f"{name}: transactions missing from its decision log")
        if re.search(r"decide error:|decide timeout:", logs.get(name, "") + agent.get("stderrTail", "")):
            problems.append(f"{name}: failed or timed-out decision")
    for name in AGENTS:
        cap = resources.get(name)
        if not cap:
            problems.append(f"{name}: no observed Docker resource configuration")
        elif (
            cap.get("memory") != MEMORY_BYTES
            or cap.get("memorySwap") != MEMORY_BYTES
            or cap.get("nanoCpus") != NANO_CPUS
            or cap.get("readOnlyRootfs") is not True
        ):
            problems.append(f"{name}: unexpected Docker limits")
        if not logs.get(name):
            problems.append(f"{name}: empty decision log")
    return problems


def observe_containers(done: threading.Event, resources: dict) -> None:
    while not done.is_set():
        try:
            result = subprocess.run(
                ["docker", "inspect", *[f"eris-{name}" for name in AGENTS]],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            for container in json.loads(result.stdout or "[]"):
                name = container["Name"].removeprefix("/eris-")
                if name not in AGENTS or not container["State"]["Running"]:
                    continue
                config = container["HostConfig"]
                # Never retain Config.Env: credentials can exist in a developer's shell.
                resources[name] = {
                    "image": container["Image"],
                    "memory": config["Memory"],
                    "memorySwap": config["MemorySwap"],
                    "nanoCpus": config["NanoCpus"],
                    "readOnlyRootfs": config["ReadonlyRootfs"],
                    "networkMode": config["NetworkMode"],
                }
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
            pass  # Missing evidence fails assess(), including when observation never succeeds.
        done.wait(5)


def execution_activity(log: str, settled: dict[str, str] | None = None) -> dict:
    records = []
    malformed = 0
    for line in log.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                records.append(value)
            else:
                malformed += 1
        except ValueError:
            malformed += 1
    decisions = [row for row in records if row.get("marker") == "ASCON_DECISION"]
    result = {
        "decisionReasons": dict(Counter(str(row.get("reason")) for row in decisions)),
        "pairedTrades": sum(row.get("reason") == "cross_venue_pair" for row in decisions),
        "submitted": sum(row.get("event") == "submitted" for row in records),
        "submitFailures": sum(row.get("event") == "submit_failed" for row in records),
        "malformedLogLines": malformed,
    }
    if settled is not None:
        outcomes = Counter()
        for decision in decisions:
            if decision.get("reason") != "cross_venue_pair":
                continue
            hashes = {
                row["hash"]
                for row in records
                if row.get("event") == "submitted"
                and row.get("blockSeen") == decision.get("round")
                and row.get("bundleId") is not None
                and isinstance(row.get("hash"), str)
            }
            filled = sum(settled.get(tx_hash) == "success" for tx_hash in hashes)
            outcomes["bothFilled" if filled == 2 else "oneFilled" if filled == 1 else "noneFilled"] += 1
        result["pairOutcomes"] = dict(outcomes)
    return result


def validate_case(case: dict, published: list[dict], *, allow_extra_seed: bool = False) -> None:
    if case in published:
        return
    seed = case.get("seed")
    if (
        allow_extra_seed
        and case.get("regime") in {row["regime"] for row in published}
        and isinstance(seed, int)
        and not isinstance(seed, bool)
        and 0 <= seed < 2**32
    ):
        return
    raise ValueError("Select a published regime/seed pair, or explicitly allow an extra seed for a published regime")


def summarize_metrics(metrics: list[dict]) -> dict:
    """Descriptive comparisons, separate from the execution/resource pass flag."""
    if not metrics:
        return {"scenarios": 0}
    return {
        "scenarios": len(metrics),
        "meanPnlUsdc": mean(row["pnlUsdc"] for row in metrics),
        "medianPnlUsdc": median(row["pnlUsdc"] for row in metrics),
        "meanVersusStarterUsdc": mean(row["versusStarterUsdc"] for row in metrics),
        "medianVersusStarterUsdc": median(row["versusStarterUsdc"] for row in metrics),
        "meanVersusNoopUsdc": mean(row["versusNoopUsdc"] for row in metrics),
        "winsVersusStarter": sum(row["versusStarterUsdc"] > 0 for row in metrics),
        "winsVersusNoop": sum(row["versusNoopUsdc"] > 0 for row in metrics),
        "worstVersusStarterUsdc": min(row["versusStarterUsdc"] for row in metrics),
        "worstPnlUsdc": min(row["pnlUsdc"] for row in metrics),
        "includedTxCount": sum(row.get("includedTxCount", 0) for row in metrics),
        "revertCount": sum(row.get("revertCount", 0) for row in metrics),
        "submitFailures": sum(row.get("submitFailures", 0) for row in metrics),
        "pairedTrades": sum(row.get("pairedTrades", 0) for row in metrics),
        "partialPairs": sum(row.get("partialPairs", 0) for row in metrics),
    }


def run_case(checkout: Path, case: dict, output: Path, *, allow_extra_seed: bool = False) -> None:
    tools.stage(checkout)
    published = public_cases(checkout)
    validate_case(case, published, allow_extra_seed=allow_extra_seed)
    config = yaml_json(checkout, f"config/regimes/{case['regime']}.yaml")["run"]
    expected = {key: config[key] for key in ("blocks", "blockTimeSec")}
    if not (checkout / "backtest/state/manifest.json").exists():
        raise ValueError("Missing deployed state dump")
    runs = checkout / "runs"
    before = set(runs.glob("*/summary.json")) if runs.exists() else set()
    output.mkdir(parents=True, exist_ok=True)
    env = tools.execution_env()
    env.update(ERIS_AGENT_FROZEN="1", ERIS_DOCKER_MEM="4g", ERIS_DOCKER_CPUS="2")
    for key in ("OLLAMA_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "AKASHML_API_KEY"):
        env[key] = ""
    resources: dict = {}
    done = threading.Event()
    observer = threading.Thread(target=observe_containers, args=(done, resources), daemon=True)
    observer.start()
    problems = []
    logs: dict[str, str] = {}
    started = datetime.now(UTC).isoformat()
    try:
        with (output / "backtest.log").open("w") as log:
            subprocess.run(
                [
                    "node",
                    "--import",
                    "tsx",
                    "core/src/cli/backtest.ts",
                    "--regime",
                    case["regime"],
                    "--seed",
                    str(case["seed"]),
                    "--agents",
                    "config/rosters/ascon-frozen.yaml",
                    "--agent-sandbox",
                    "docker",
                ],
                cwd=checkout,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=config["seconds"] + 300,
                check=True,
            )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        problems.append(f"backtest did not complete: {type(exc).__name__}")
    finally:
        done.set()
        observer.join(timeout=15)
    summaries = set(runs.glob("*/summary.json")) - before
    summary = {}
    run_dir = None
    settled: dict[str, str] = {}
    if len(summaries) != 1:
        problems.append(f"expected one new run summary, got {len(summaries)}")
    else:
        path = summaries.pop()
        run_dir = path.parent
        summary = read_json(path)
        logs = {
            name: (run_dir / "agents" / f"{name}.jsonl").read_text()
            if (run_dir / "agents" / f"{name}.jsonl").is_file()
            else ""
            for name in AGENTS
        }
        problems.extend(assess(summary, expected, resources, logs))
        write_json(output / "summary.json", summary)
        with (run_dir / "blocks.csv").open() as stream:
            settled = {
                row["hash"]: row["status"] for row in csv.DictReader(stream) if row["ownerId"] == "eris-adaptive-v1"
            }
    report = {
        **case,
        "published_case": case in published,
        "passed": not problems,
        "problems": problems,
        "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "expected": expected,
        "eris_revision": tools.revision(),
        "source_sha256": source_hashes(),
        "resources": resources,
        "run_directory": str(run_dir) if run_dir else None,
        "agents": summary.get("agents", []),
        "execution": execution_activity(logs.get("eris-adaptive-v1", ""), settled),
        "frozen": True,
        "live_llm_validated": False,
    }
    write_json(output / "report.json", report)
    print(
        "SCENARIO_RESULT "
        + json.dumps(
            {
                **{key: report[key] for key in ("regime", "seed", "passed", "problems", "source_sha256", "execution")},
                "agents": [
                    {key: agent.get(key) for key in ("id", "pnlUsdc", "netPnlUsdc", "includedTxCount", "revertCount")}
                    for agent in report["agents"]
                ],
            }
        ),
        flush=True,
    )
    if problems:
        raise ValueError("Market validation failed; inspect report.json and backtest.log")


def aggregate(checkout: Path, inputs: Path, output: Path, *, extra_seed: int | None = None) -> None:
    published = public_cases(checkout)
    if extra_seed is not None:
        if any(c["seed"] == extra_seed for c in published):
            raise ValueError("Extra-seed evidence must use a seed outside the public matrix")
        for regime in {c["regime"] for c in published}:
            validate_case({"regime": regime, "seed": extra_seed}, published, allow_extra_seed=True)
    expected = {(c["regime"], c["seed"] if extra_seed is None else extra_seed) for c in published}
    label = "public" if extra_seed is None else "extra-seed"
    pass_key = "public_matrix_passed" if extra_seed is None else "extra_seed_matrix_passed"
    reports = [read_json(p) for p in sorted(inputs.glob("**/report.json"))]
    seen = [(r["regime"], r["seed"]) for r in reports]
    problems = []
    if set(seen) != expected or len(seen) != len(expected):
        problems.append(f"{label} scenario coverage is incomplete, duplicated or unexpected")
    current_hashes = source_hashes()
    for report in reports:
        if not report.get("passed"):
            problems.append(f"failed scenario: {report['regime']}#{report['seed']}")
        if report.get("source_sha256") != current_hashes or report.get("eris_revision") != tools.revision():
            problems.append("evidence belongs to different strategy sources or SDK")
    metrics = []
    for report in reports:
        agents = {a["id"]: a for a in report.get("agents", [])}
        if all(isinstance(agents.get(name, {}).get("pnlUsdc"), (int, float)) for name in AGENTS):
            candidate = agents["eris-adaptive-v1"]["pnlUsdc"]
            metrics.append(
                {
                    "regime": report["regime"],
                    "seed": report["seed"],
                    "pnlUsdc": candidate,
                    "versusStarterUsdc": candidate - agents["my-arb-py"]["pnlUsdc"],
                    "versusNoopUsdc": candidate - agents["noop"]["pnlUsdc"],
                    "includedTxCount": agents["eris-adaptive-v1"].get("includedTxCount", 0),
                    "revertCount": agents["eris-adaptive-v1"].get("revertCount", 0),
                    "submitFailures": report.get("execution", {}).get("submitFailures", 0),
                    "pairedTrades": report.get("execution", {}).get("pairedTrades", 0),
                    "partialPairs": report.get("execution", {}).get("pairOutcomes", {}).get("oneFilled", 0),
                }
            )
    write_json(
        output,
        {
            pass_key: not problems,
            "scenario_set": label,
            "extra_seed": extra_seed,
            "problems": sorted(set(problems)),
            "expected_scenarios": len(expected),
            "reported_scenarios": len(reports),
            "eris_revision": tools.revision(),
            "source_sha256": current_hashes,
            "metrics": metrics,
            "performance": summarize_metrics(metrics),
            "performanceByRegime": {
                regime: summarize_metrics([row for row in metrics if row["regime"] == regime])
                for regime in sorted({row["regime"] for row in metrics})
            },
            "live_llm_validated": False,
            "note": "Frozen execution/resource evidence. Three-agent comparisons do not predict contest placement.",
        },
    )
    print(f"{label} matrix: {len(reports)}/{len(expected)} scenarios; passed={not problems}")
    marker = "PUBLIC_MATRIX_RESULT " if extra_seed is None else "EXTRA_SEED_MATRIX_RESULT "
    print(marker + json.dumps(read_json(output)), flush=True)
    if problems:
        raise ValueError(f"Incomplete or failing {label} market matrix")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("plan", "run", "aggregate"))
    parser.add_argument("--eris", type=Path, default=tools.root().parent / ".eris/eris-agent-simulator")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--regime")
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--allow-extra-seed", action="store_true", help="Allow an additional seed for a published regime"
    )
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    checkout = args.eris.resolve()
    tools.verify_checkout(checkout)
    if args.operation == "plan":
        cases = public_cases(checkout)
        matrix = {"include": [c for c in cases if (c["regime"], c["seed"]) not in SMOKE]}
        write_json(args.out, {"all": cases, "remaining": matrix})
        if args.github_output:
            with args.github_output.open("a") as stream:
                stream.write("matrix=" + json.dumps(matrix, separators=(",", ":")) + "\n")
                holdout = {"regime": sorted({case["regime"] for case in cases})}
                stream.write("holdout=" + json.dumps(holdout, separators=(",", ":")) + "\n")
    elif args.operation == "run":
        run_case(
            checkout,
            {"regime": args.regime, "seed": args.seed},
            args.out.resolve(),
            allow_extra_seed=args.allow_extra_seed,
        )
    elif args.inputs:
        if args.allow_extra_seed and args.seed is None:
            parser.error("aggregate --allow-extra-seed requires --seed")
        aggregate(checkout, args.inputs, args.out, extra_seed=args.seed if args.allow_extra_seed else None)
    else:
        parser.error("aggregate requires --inputs")


if __name__ == "__main__":
    main()

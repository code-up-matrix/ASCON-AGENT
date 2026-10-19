"""Run and audit the pinned public market scenarios without inference credentials.

The official backtester can exit successfully with incomplete/failed agents. This
runner inspects its evidence, observes actual Docker resource settings, and refuses
to label a partial scenario set as a completed public matrix.
"""

import argparse
import hashlib
import json
import math
import re
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path

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


def run_case(checkout: Path, case: dict, output: Path) -> None:
    tools.stage(checkout)
    if case not in public_cases(checkout):
        raise ValueError("Select a published regime/seed pair")
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
    report = {
        **case,
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
        "frozen": True,
        "live_llm_validated": False,
    }
    write_json(output / "report.json", report)
    print(json.dumps({"case": case, "passed": not problems, "problems": problems}), flush=True)
    if problems:
        raise ValueError("Market validation failed; inspect report.json and backtest.log")


def aggregate(checkout: Path, inputs: Path, output: Path) -> None:
    expected = {(c["regime"], c["seed"]) for c in public_cases(checkout)}
    reports = [read_json(p) for p in sorted(inputs.glob("**/report.json"))]
    seen = [(r["regime"], r["seed"]) for r in reports]
    problems = []
    if set(seen) != expected or len(seen) != len(expected):
        problems.append("public scenario coverage is incomplete, duplicated or unexpected")
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
                }
            )
    write_json(
        output,
        {
            "public_matrix_passed": not problems,
            "problems": sorted(set(problems)),
            "expected_scenarios": len(expected),
            "reported_scenarios": len(reports),
            "eris_revision": tools.revision(),
            "source_sha256": current_hashes,
            "metrics": metrics,
            "live_llm_validated": False,
            "note": "Frozen execution/resource evidence. Three-agent comparisons do not predict contest placement.",
        },
    )
    print(f"Public matrix: {len(reports)}/{len(expected)} scenarios; passed={not problems}")
    if problems:
        raise ValueError("Incomplete or failing public market matrix")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("plan", "run", "aggregate"))
    parser.add_argument("--eris", type=Path, default=tools.root().parent / ".eris/eris-agent-simulator")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--regime")
    parser.add_argument("--seed", type=int)
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
    elif args.operation == "run":
        run_case(checkout, {"regime": args.regime, "seed": args.seed}, args.out.resolve())
    elif args.inputs:
        aggregate(checkout, args.inputs, args.out)
    else:
        parser.error("aggregate requires --inputs")


if __name__ == "__main__":
    main()

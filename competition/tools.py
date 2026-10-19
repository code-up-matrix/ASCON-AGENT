"""Prepare/check/package against a pinned runtime; baseline backtests are frozen.

Run with ``uv run --project competition --frozen python competition/tools.py --help``.
Paid local LLM commands require --i-accept-spend. There is no contest submission.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def root() -> Path:
    return Path(__file__).resolve().parent


def revision() -> str:
    return (root() / "eris.lock").read_text().strip()


def command(argv: list[str], cwd: Path, *, env: dict[str, str] | None = None, capture: bool = False) -> str:
    result = subprocess.run(argv, cwd=cwd, env=env, check=True, text=True, capture_output=capture)
    return result.stdout.strip() if capture else ""


def verify_checkout(checkout: Path) -> None:
    actual = command(["git", "rev-parse", "HEAD"], checkout, capture=True)
    if actual != revision():
        raise ValueError(f"Eris revision mismatch: expected {revision()}, got {actual}")
    # Runtime/code changes break the compatibility claim. gen:local-constants is
    # expected to modify exactly this generated address file during deployment.
    changed = command(["git", "diff", "HEAD", "--name-only"], checkout, capture=True).splitlines()
    unexpected = [path for path in changed if path != "sdk/src/constants.local.ts"]
    if unexpected:
        raise ValueError("Eris has tracked changes outside generated deployment addresses: " + ", ".join(unexpected))


def prepare(checkout: Path) -> None:
    if not checkout.exists():
        checkout.parent.mkdir(parents=True, exist_ok=True)
        command(
            [
                "git",
                "clone",
                "--no-checkout",
                "https://github.com/NyxFoundation/eris-agent-simulator.git",
                str(checkout),
            ],
            checkout.parent,
        )
        command(["git", "checkout", "--detach", revision()], checkout)
    verify_checkout(checkout)
    stage(checkout)
    print(f"Pinned Eris checkout ready: {checkout}")
    print("Next: run npm ci in that directory. No inference has been requested.")


def stage(checkout: Path) -> None:
    verify_checkout(checkout)
    source = root() / "agents" / "eris-adaptive-v1"
    target = checkout / "example" / "agents" / source.name
    target.mkdir(parents=True, exist_ok=True)
    allowed = {"strategy.py", "constants.py", "prompt.md"}
    unexpected = [path.name for path in target.iterdir() if path.name not in allowed | {"__pycache__"}]
    if unexpected:
        raise ValueError("Refusing to bundle unexpected agent files: " + ", ".join(unexpected))
    for name in sorted(allowed):
        shutil.copy2(source / name, target / name)
    for roster in (root() / "rosters").glob("*.yaml"):
        target_roster = checkout / "config" / "rosters" / roster.name
        # Preserve deliberate local model selections in the improving roster.
        if roster.name != "ascon-improving.yaml" or not target_roster.exists():
            shutil.copy2(roster, target_roster)
    template = root() / ".env.template"
    if not (checkout / ".env.local").exists():
        shutil.copy2(template, checkout / ".env.local")
        (checkout / ".env.local").chmod(0o600)


def execution_env() -> dict[str, str]:
    result = os.environ.copy()
    result["ERIS_PYTHON"] = sys.executable
    return result


def check(checkout: Path) -> None:
    stage(checkout)
    # Invoke the official entry point directly: the tsx CLI creates an unrelated
    # IPC listener, which is unavailable in some restricted build environments.
    command(["node", "--import", "tsx", "scripts/checkStrategyCode.ts"], checkout, env=execution_env())
    command(
        ["node", "--import", "tsx", str(root() / "tests" / "bridge-smoke.mjs")],
        checkout,
        env=execution_env(),
    )
    command(
        ["node", "--import", "tsx", str(root() / "tests" / "llm-transport-smoke.mjs")],
        checkout,
        env=execution_env(),
    )


def bundle(checkout: Path, output: Path) -> None:
    check(checkout)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "bundle-eris-adaptive-v1.zip"
    command(
        ["node", "--import", "tsx", "scripts/bundleAgent.ts", "eris-adaptive-v1", "--out", str(archive)],
        checkout,
        env=execution_env(),
    )
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest = {
        "agent": "eris-adaptive-v1",
        "eris_revision": revision(),
        "sha256": digest,
        "source_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((root() / "agents" / "eris-adaptive-v1").iterdir())
            if path.is_file()
        },
        "validation": "Packaged with official bundler; not a simulator score or submission acceptance.",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Bundle: {archive}\nSHA-256: {digest}")


def backtest(checkout: Path, *, regime: str, seed: int, sandbox: str, matrix: bool) -> None:
    stage(checkout)
    if not (checkout / "backtest" / "state" / "manifest.json").exists():
        raise ValueError("Missing state dump. Follow docs/ASCON_SETUP.md: deploy, gen:local-constants, gen:state-dump.")
    args = ["npm", "run", "backtest", "--"]
    if matrix:
        args += ["--scenarios", "config/scenarios/public.yaml"]
    else:
        regime_file = checkout / "config" / "regimes" / f"{regime}.yaml"
        if not regime_file.is_file() or "/" in regime or "\\" in regime:
            raise ValueError("Unknown regime name")
        args += ["--regime", regime, "--seed", str(seed)]
    args += ["--agents", "config/rosters/ascon-frozen.yaml", "--agent-sandbox", sandbox]
    env = execution_env()
    env["ERIS_AGENT_FROZEN"] = "1"
    print("Frozen baseline: strategy revisions disabled for every agent.", flush=True)
    command(args, checkout, env=env)


def doctor(checkout: Path) -> None:
    print(f"Required Eris revision: {revision()}")
    for name in ("git", "uv", "node", "npm", "forge", "anvil", "docker"):
        print(f"{name}: {'available' if shutil.which(name) else 'missing'}")
    if checkout.exists():
        verify_checkout(checkout)
        print("Eris revision: verified")
    else:
        print("Eris checkout: missing (run prepare)")
    print(f"Python: {sys.version.split()[0]} (verify the final image on the official 3.11 runtime)")
    print("Offline strategy tests require no API keys. Improving runs need one provider key.")
    print("Keys belong in Eris .env.local; this command never reads or prints them.")


def local_llm(checkout: Path, args: argparse.Namespace) -> None:
    if args.operation != "llm-check" and not args.i_accept_spend:
        raise ValueError("This operation spends inference credits; pass --i-accept-spend for this run.")
    stage(checkout)
    if args.operation == "llm-backtest":
        if not (checkout / "backtest" / "state" / "manifest.json").exists():
            raise ValueError("Missing state dump. Complete docs/ASCON_SETUP.md section 3 first.")
        if (
            "/" in args.regime
            or "\\" in args.regime
            or not (checkout / "config" / "regimes" / f"{args.regime}.yaml").is_file()
        ):
            raise ValueError("Unknown regime name")
    argv = ["node", "--import", "tsx", str(root() / "llm" / "provider.mjs"), args.operation]
    if args.provider:
        argv += ["--provider", args.provider]
    if args.i_accept_spend:
        argv += ["--i-accept-spend"]
    argv += ["--regime", args.regime, "--seed", str(args.seed)]
    command(argv, checkout, env=execution_env())


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "operation",
        choices=("prepare", "stage", "doctor", "check", "bundle", "backtest", "llm-check", "llm-smoke", "llm-backtest"),
    )
    result.add_argument("--eris", type=Path, default=root().parent / ".eris" / "eris-agent-simulator")
    result.add_argument("--out", type=Path, default=root().parent / "dist" / "ascon")
    result.add_argument("--regime", default="calm")
    result.add_argument("--seed", type=int, default=1)
    result.add_argument("--sandbox", choices=("docker", "process"), default="docker")
    result.add_argument("--matrix", action="store_true", help="Frozen full public set; can take about 12 hours")
    result.add_argument(
        "--provider", choices=("openrouter", "akashml"), help="Local LLM provider; otherwise .env.local"
    )
    result.add_argument(
        "--i-accept-spend", action="store_true", help="Approve this one local LLM operation's API spend"
    )
    return result


def main() -> None:
    args = parser().parse_args()
    checkout = args.eris.resolve()
    try:
        if args.operation.startswith("llm-"):
            local_llm(checkout, args)
        elif args.operation == "bundle":
            bundle(checkout, args.out.resolve())
        elif args.operation == "backtest":
            backtest(checkout, regime=args.regime, seed=args.seed, sandbox=args.sandbox, matrix=args.matrix)
        else:
            {"prepare": prepare, "stage": stage, "doctor": doctor, "check": check}[args.operation](checkout)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ASCON setup failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

// Run from the pinned Eris checkout via competition/tools.py. No RPC or inference.
// This exercises the actual TS-to-Python bridge, including relocated revision imports.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const official = (path) => import(pathToFileURL(resolve(path)).href);
const { PyBridge } = await official("example/agents/runtime/pyBridge.ts");
const { loadConfig } = await official("sdk/src/config.ts");
const { loadImproveAgent, parseRevision } = await official("example/agents/runtime/improve.ts");
const { pythonObservation } = await official("test/helpers/python.ts");
const agentDir = resolve("example/agents/eris-adaptive-v1");
const policy = loadImproveAgent(agentDir);
assert.equal(policy.language, "python");
assert.equal(policy.reviseEveryBlocks, 60);
const path = resolve(agentDir, "strategy.py");
const original = readFileSync(path, "utf8");
const logs = [];
const runner = new PyBridge(
  { kind: "python", path },
  {
    agentId: "eris-adaptive-v1",
    agentDir,
    address: "0x0000000000000000000000000000000000000001",
    config: loadConfig(),
    rpcUrl: "http://127.0.0.1:1", // never contacted by this fixture
  },
  (entry) => logs.push(entry),
  5000,
);
const observation = (round) => {
  const obs = pythonObservation(round);
  obs.balances.usdcUnits = "25000000000";
  obs.balances.wethWei = "0";
  obs.enabledProtocols = ["uniswap"];
  obs.protocols.uniswap.pool.liquidity = "100000000000000000";
  return obs;
};
try {
  const first = await runner.decide(observation(1));
  assert.equal(first.action.type, "swap");
  assert.equal(first.action.tokenIn, "USDC");
  assert.equal((await runner.decide(observation(2))).action.reason, "settlement_cooldown");
  const parsed = parseRevision({
    notes: "Offline fixture: mark the replacement to prove it executes.",
    executorPy: original.replaceAll("ASCON_DECISION", "ASCON_REVISION_TEST"),
  }, "python");
  assert.equal(parsed.ok, true);
  const revised = await runner.prepareSource(parsed.revision.executorPy);
  assert.equal(revised.ok, true);
  runner.setSource(revised.source);
  assert.equal((await runner.decide(observation(3))).action.type, "swap");
  assert.equal(logs.at(-1).marker, "ASCON_REVISION_TEST");
  const reverted = await runner.prepareSource(original);
  assert.equal(reverted.ok, true);
  runner.setSource(reverted.source);
  assert.equal((await runner.decide(observation(4))).action.type, "swap");
  assert.equal(logs.at(-1).marker, "ASCON_DECISION");
  console.log("Official Python bridge PASS: resident decisions, compiled replacement and restored source; no model call.");
} finally {
  await runner.close();
}

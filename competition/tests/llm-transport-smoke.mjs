// Actual pinned Eris inference transport, with all HTTP requests replaced in memory.
import assert from "node:assert/strict";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { configureProvider, main } from "../llm/provider.mjs";
import { LOCAL_ROSTER, SMOKE_MAX_TOKENS } from "../llm/constants.mjs";

const official = (path) => import(pathToFileURL(resolve(path)).href);
const { callLlmWithUsage, LlmOutputTruncatedError } = await official("example/agents/runtime/llm.ts");
const { strategyEnv } = await official("example/agents/runtime/strategyEnv.ts");
const { loadAgents } = await official("core/src/config.ts");
const { loadImproveAgent } = await official("example/agents/runtime/improve.ts");
const agents = loadAgents(LOCAL_ROSTER);
assert.equal(agents.length, 3);
for (const agent of agents) {
  assert.equal(agent.env.ERIS_AGENT_FROZEN, agent.id === "eris-adaptive-v1" ? "0" : "1");
  assert.equal(agent.env.ERIS_LLM_MODEL, undefined);
}
assert.equal(loadImproveAgent(resolve("example/agents/eris-adaptive-v1")).model, undefined);
const originalEnv = { ...process.env };
const originalFetch = globalThis.fetch;
const originalLog = console.log;
let count = 0;
try {
  // Fail closed: no test can fall through to a real request, even on a bad route.
  globalThis.fetch = async () => { throw new Error("Unexpected HTTP request in offline test"); };
  delete process.env.ERIS_INFERENCE_BASE_URL;
  const credentials = {
    OPENROUTER_API_KEY: "offline-router-credential",
    AKASHML_API_KEY: "offline-akash-credential",
  };
  for (const name of ["openrouter", "akashml"]) {
    const config = configureProvider(credentials, name);
    Object.assign(process.env, config.env);
    process.env.OPENROUTER_MODEL = config.model;
    process.env.AKASHML_MODEL = config.model;
    // The official worker filter must remove both original keys and the alias.
    const worker = strategyEnv(process.env);
    assert.equal(worker.OPENROUTER_API_KEY, undefined);
    assert.equal(worker.AKASHML_API_KEY, undefined);
    assert.equal(worker.OPENAI_API_KEY, undefined);
    for (const json of [true, false]) {
      globalThis.fetch = async (url, init) => {
        count += 1;
        assert.equal(url, `${config.env.OPENAI_BASE_URL}/chat/completions`);
        assert.equal(init.headers.authorization, `Bearer ${config.env.OPENAI_API_KEY}`);
        const body = JSON.parse(init.body);
        assert.equal(body.model, config.model);
        assert.equal(body.max_completion_tokens, SMOKE_MAX_TOKENS);
        assert.deepEqual(body.response_format, json ? { type: "json_object" } : undefined);
        return Response.json({
          choices: [{ message: { content: "ASCON_OK" }, finish_reason: "stop" }],
          usage: { prompt_tokens: 7, completion_tokens: 3 },
        });
      };
      const reply = await callLlmWithUsage({
        model: config.env.ERIS_LLM_MODEL,
        system: "Offline transport fixture",
        messages: [{ role: "user", content: "Return JSON or plain text." }],
        json,
        maxOutputTokens: SMOKE_MAX_TOKENS,
      });
      assert.equal(reply.text, "ASCON_OK");
      assert.deepEqual(reply.usage, { inputTokens: 7, outputTokens: 3 });
    }
    // The documented CLI must use the same path. Configuration checks never
    // fetch; the explicitly approved smoke operation makes exactly one request.
    const output = [];
    console.log = (...parts) => output.push(parts.join(" "));
    const beforeCheck = count;
    await main(["llm-check", "--provider", name]);
    assert.equal(count, beforeCheck);
    await main(["llm-smoke", "--provider", name, "--i-accept-spend"]);
    assert.equal(count, beforeCheck + 1);
    assert.ok(output.some((line) => line.includes("ASCON_OK")));
    for (const key of Object.values(credentials)) assert.ok(!output.join("\n").includes(key));
    console.log = originalLog;
    globalThis.fetch = async () => Response.json({
      choices: [{ message: { content: "partial" }, finish_reason: "length" }],
    });
    await assert.rejects(callLlmWithUsage({ model: config.env.ERIS_LLM_MODEL, system: "test", messages: [] }), LlmOutputTruncatedError);
    globalThis.fetch = async () => new Response("Invalid credential", { status: 401 });
    await assert.rejects(callLlmWithUsage({ model: config.env.ERIS_LLM_MODEL, system: "test", messages: [] }), /401/);
  }
  assert.equal(count, 6);
  console.log("Official LLM transport PASS: both providers, model routing, token caps, JSON/text, usage, errors and credential filtering; all HTTP mocked.");
} finally {
  globalThis.fetch = originalFetch;
  console.log = originalLog;
  for (const name of Object.keys(process.env)) if (!(name in originalEnv)) delete process.env[name];
  Object.assign(process.env, originalEnv);
}

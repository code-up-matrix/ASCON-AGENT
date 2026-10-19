// Run from the pinned Eris checkout through competition/tools.py.
// Reuse its env loader and inference transport; keep the official runtime unmodified.
import { spawn } from "node:child_process";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { LOCAL_ROSTER, PROVIDERS, SMOKE_MAX_TOKENS } from "./constants.mjs";

export function configureProvider(env, selection) {
  const name = selection ?? env.ASCON_LLM_PROVIDER ?? "openrouter";
  if (!Object.hasOwn(PROVIDERS, name)) {
    throw new Error("Choose --provider openrouter or --provider akashml.");
  }
  if (env.ERIS_INFERENCE_BASE_URL?.trim()) {
    throw new Error("Local provider selection cannot be used with the organizer's ERIS_INFERENCE_BASE_URL.");
  }
  const provider = PROVIDERS[name];
  const key = env[provider.key]?.trim();
  if (!key) throw new Error(`Set ${provider.key} in the Eris .env.local file.`);
  const model = env[provider.model]?.trim() || provider.defaultModel;
  if (!/^[A-Za-z0-9][A-Za-z0-9._/:+-]*$/.test(model) || model.startsWith("openai:")) {
    throw new Error(`Set ${provider.model} to the provider's model ID without Eris's openai: prefix.`);
  }
  // This pinned Eris dispatches these IDs to Responses, which is outside this
  // Chat Completions integration. Reject instead of silently using another API.
  if (/(^|-)pro($|-)|codex/.test(model)) {
    throw new Error("This Eris revision routes pro/codex IDs to Responses; choose a Chat Completions model.");
  }
  return {
    name,
    model,
    keyName: provider.key,
    env: {
      ...env,
      OPENAI_API_KEY: key,
      OPENAI_BASE_URL: provider.baseUrl,
      ERIS_LLM_MODEL: `openai:${model}`,
    },
  };
}

export function describeProvider(config) {
  return {
    provider: config.name,
    model: config.model,
    endpoint: config.env.OPENAI_BASE_URL,
    credential: `${config.keyName}: configured (value hidden)`,
    scope: "Local development only; not an organizer-approved provider.",
  };
}

export function requireSpendConsent(operation, accepted) {
  if (operation !== "llm-check" && !accepted) {
    throw new Error("This operation spends inference credits. Run explicitly with --i-accept-spend.");
  }
}

const official = (path) => import(pathToFileURL(resolve(path)).href);

export async function main(argv = process.argv.slice(2)) {
  const { values, positionals } = parseArgs({
    args: argv,
    allowPositionals: true,
    options: {
      provider: { type: "string" },
      regime: { type: "string", default: "calm" },
      seed: { type: "string", default: "1" },
      "i-accept-spend": { type: "boolean", default: false },
    },
  });
  const [operation] = positionals;
  if (positionals.length !== 1 || !["llm-check", "llm-smoke", "llm-backtest"].includes(operation)) {
    throw new Error("Use competition/tools.py llm-check, llm-smoke or llm-backtest.");
  }
  requireSpendConsent(operation, values["i-accept-spend"]);
  const { loadEnvLocal } = await official("core/src/cli/bootstrapEnv.ts");
  loadEnvLocal(); // Existing shell exports win, just as in the official CLI.
  const config = configureProvider(process.env, values.provider);
  console.log(JSON.stringify(describeProvider(config), null, 2));
  if (operation === "llm-check") {
    console.log("Configuration valid; no API request made. Key validity and credit balance are untested.");
    return;
  }
  Object.assign(process.env, config.env);
  if (operation === "llm-smoke") {
    const { callLlmWithUsage } = await official("example/agents/runtime/llm.ts");
    const reply = await callLlmWithUsage({
      model: config.env.ERIS_LLM_MODEL,
      system: "You are testing an API connection. Reply with ASCON_OK only.",
      messages: [{ role: "user", content: "Confirm the connection." }],
      json: false,
      maxOutputTokens: SMOKE_MAX_TOKENS,
    });
    // Do not print provider response text: the request's credentials must never
    // be echoed by a provider or a model into our console output.
    if (reply.text.trim() !== "ASCON_OK") throw new Error("API returned content but the smoke-test marker was absent.");
    console.log(JSON.stringify({ result: "ASCON_OK", usage: reply.usage }));
    return;
  }
  const child = spawn(process.execPath, [
    "--import", "tsx", "core/src/cli/backtest.ts",
    "--regime", values.regime, "--seed", values.seed,
    "--agents", LOCAL_ROSTER, "--agent-sandbox", "process",
  ], { stdio: "inherit", env: config.env });
  process.exitCode = await new Promise((done, fail) => {
    child.once("error", fail);
    child.once("exit", (code) => done(code ?? 1));
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch((error) => {
    // Eris includes upstream error bodies. Mask local credentials before logging.
    let message = error instanceof Error ? error.message : "Unknown provider failure";
    for (const [name, value] of Object.entries(process.env)) {
      if (/(API_KEY|TOKEN|SECRET|PASSWORD|PRIVATE_KEY)$/.test(name) && value) {
        message = message.split(value).join("[redacted]");
      }
    }
    console.error(`ASCON LLM setup failed: ${message}`);
    process.exitCode = 1;
  });
}

import assert from "node:assert/strict";
import test from "node:test";
import { configureProvider, describeProvider, main, requireSpendConsent } from "../llm/provider.mjs";

const credentials = {
  OPENROUTER_API_KEY: "offline-router-credential",
  AKASHML_API_KEY: "offline-akash-credential",
  OPENAI_API_KEY: "offline-unrelated-credential",
  OPENAI_BASE_URL: "https://unrelated.invalid/v1",
};

test("both keys can coexist; each explicit selection replaces stale OpenAI routing", () => {
  const router = configureProvider(credentials, "openrouter");
  const akash = configureProvider(credentials, "akashml");
  assert.equal(router.env.OPENAI_API_KEY, credentials.OPENROUTER_API_KEY);
  assert.equal(akash.env.OPENAI_API_KEY, credentials.AKASHML_API_KEY);
  assert.equal(router.env.OPENAI_BASE_URL, "https://openrouter.ai/api/v1");
  assert.equal(akash.env.OPENAI_BASE_URL, "https://api.akashml.com/v1");
  assert.equal(credentials.OPENAI_API_KEY, "offline-unrelated-credential");
  for (const config of [router, akash]) {
    const output = JSON.stringify(describeProvider(config));
    for (const key of Object.values(credentials)) assert.ok(!output.includes(key));
  }
});

test("provider-specific model and CLI selection override unrelated global settings", () => {
  const env = {
    ...credentials,
    ASCON_LLM_PROVIDER: "akashml",
    OPENROUTER_MODEL: "vendor/router-test-model",
    AKASHML_MODEL: "vendor/akash-test-model",
    ERIS_LLM_MODEL: "some-stale-model",
  };
  assert.equal(configureProvider(env).env.ERIS_LLM_MODEL, "openai:vendor/akash-test-model");
  assert.equal(configureProvider(env, "openrouter").env.ERIS_LLM_MODEL, "openai:vendor/router-test-model");
});

test("missing selected key fails instead of borrowing the other provider's credentials", () => {
  assert.throws(() => configureProvider({ ...credentials, OPENROUTER_API_KEY: " " }, "openrouter"), /OPENROUTER_API_KEY/);
  assert.throws(() => configureProvider({ ...credentials, AKASHML_API_KEY: "" }, "akashml"), /AKASHML_API_KEY/);
  assert.throws(() => configureProvider(credentials, "unknown"), /Choose --provider/);
});

test("local selection cannot redirect an organizer-proxied run", () => {
  assert.throws(() => configureProvider({ ...credentials, ERIS_INFERENCE_BASE_URL: "https://organizer.invalid" }), /organizer/);
});

test("models routed to an incompatible API or with duplicate prefixes fail before a call", () => {
  for (const model of ["vendor/model-pro", "vendor/codex", "openai:vendor/model", "vendor/model\nsecret"]) {
    assert.throws(() => configureProvider({ ...credentials, OPENROUTER_MODEL: model }));
  }
});

test("paid operations fail before loading credentials or touching the official runtime", async () => {
  requireSpendConsent("llm-check", false);
  for (const operation of ["llm-smoke", "llm-backtest"]) {
    assert.throws(() => requireSpendConsent(operation, false), /--i-accept-spend/);
    await assert.rejects(main([operation]), /--i-accept-spend/);
    requireSpendConsent(operation, true);
  }
});

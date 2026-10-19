// Local development providers. The organizer's approved-provider roster is separate.
// Catalogs checked 2026-10-19; override each provider's model in .env.local.
export const PROVIDERS = Object.freeze({
  openrouter: {
    key: "OPENROUTER_API_KEY",
    model: "OPENROUTER_MODEL",
    baseUrl: "https://openrouter.ai/api/v1",
    defaultModel: "openai/gpt-oss-120b",
  },
  akashml: {
    key: "AKASHML_API_KEY",
    model: "AKASHML_MODEL",
    baseUrl: "https://api.akashml.com/v1",
    defaultModel: "openai/gpt-oss-120b",
  },
});

export const LOCAL_ROSTER = "config/rosters/ascon-local-llm.yaml";
export const SMOKE_MAX_TOKENS = 2048;

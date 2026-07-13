# Provider Setup

This repo supports four normal local runtime shapes:

1. LiteLLM proxy
2. direct OpenAI
3. direct Gemini API
4. Vertex AI

The app is easiest to reason about if you configure one runtime provider at a time.

## Runtime Provider Options

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Then keep only the block you want to use.

### LiteLLM Proxy

Use this when you already have a LiteLLM gateway or proxy in front of OpenAI-compatible models.

```bash
LITELLM_PROXY_URL=https://your-proxy-host/v1
LITELLM_PROXY_API_KEY=your-proxy-key-here
OPENAI_MODEL=openai/gpt-4o-mini
```

Notes:

- `LITELLM_PROXY_API_KEY` is preferred.
- `OPENAI_API_KEY` is accepted as a fallback proxy auth key for compatibility.
- Proxy-backed OpenAI models can be written as `openai/gpt-4o-mini`.

### Direct OpenAI

Use this when you want the app to call OpenAI directly.

```bash
OPENAI_API_KEY=your-openai-api-key-here
OPENAI_MODEL=gpt-4o-mini
```

### Direct Gemini API

Use this when you want to call the Google AI Studio Gemini API directly.

```bash
GEMINI_API_KEY=your-gemini-api-key-here
GEMINI_MODEL=gemini-flash-latest
```

`GOOGLE_API_KEY` also works if that is the key name you already use locally.

### Vertex AI

Use this when you want Gemini through Vertex instead of a direct API key.

```bash
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=global
GEMINI_MODEL=gemini-flash-latest
```

If `GOOGLE_CLOUD_PROJECT` is left as a placeholder, the app will try to fall back to your active `gcloud` project.

## Eval Judge Provider

The eval judge can use a different provider from the app runtime.

That is useful when:

- the app uses a LiteLLM proxy
- you want simpler local eval grading
- you want to compare providers without changing the app runtime

Examples:

```bash
EVAL_JUDGE_PROVIDER=openai
EVAL_OPENAI_API_KEY=your-openai-api-key-here
EVAL_OPENAI_MODEL=gpt-4o-mini
```

```bash
EVAL_JUDGE_PROVIDER=gemini_api
EVAL_GEMINI_API_KEY=your-gemini-api-key-here
EVAL_GEMINI_MODEL=gemini-flash-latest
```

```bash
EVAL_JUDGE_PROVIDER=litellm_proxy
EVAL_LITELLM_PROXY_URL=https://your-proxy-host/v1
EVAL_LITELLM_PROXY_API_KEY=your-proxy-key-here
EVAL_OPENAI_MODEL=gpt-4o-mini
```

## Secret Hygiene

This repo intentionally ignores common local secret files:

- `.env`
- `.env.*`
- `*.pem`
- `*.p8`
- `*.p12`
- `*.key`
- `*service-account*.json`
- `*credentials*.json`
- local telemetry and generated eval artifacts

The tracked example file is `.env.example`. Put real keys in `.env`, not in docs, tests, screenshots, or committed JSON.

## Before Pushing To GitHub

Run the local safety check:

```bash
bash scripts/prepush_safety_check.sh
```

Then also sanity-check:

```bash
git status --short
git diff --cached
```

Especially verify that you are not staging:

- `.env`
- provider credential files
- local telemetry
- raw generated eval traces or grade outputs unless you intentionally want them in review

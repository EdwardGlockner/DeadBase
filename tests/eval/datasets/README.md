# Evaluation Datasets

This directory contains evaluation datasets for testing agent behavior.

## Running Evaluations

### Default Dataset
```bash
# Generate traces using the default dataset
agents-cli eval generate
agents-cli eval grade
```

The default Deadlock Coach grading config now scores several qualities
separately instead of collapsing everything into one vague score:

- `custom_response_quality`
- `custom_directness`
- `custom_factual_grounding`
- `custom_uncertainty_behavior`
- `custom_formatting_quality`
- `custom_non_redundancy`

For reliable live grading, evals can use a dedicated judge configuration that
is separate from the app runtime. The simplest local option is usually:

```bash
export EVAL_JUDGE_PROVIDER=openai
export EVAL_OPENAI_API_KEY=...
export EVAL_OPENAI_MODEL=gpt-4o-mini
```

When no explicit `EVAL_*` provider is set, the grader now tries the best live
providers it can find in a safe order:

1. eval-specific Vertex / Gemini / OpenAI config
2. normal Vertex / Gemini / OpenAI config
3. explicit eval proxy config
4. app proxy config last

It also auto-discovers the active `gcloud` project for Vertex evals when the
repo env still contains the placeholder project id. That keeps app runtime
config and eval-judge config from getting tangled.

If you want evals to use the same Cloud Run LiteLLM proxy as the app, you can
instead configure:

```bash
export EVAL_JUDGE_PROVIDER=litellm_proxy
export EVAL_LITELLM_PROXY_URL=...
export EVAL_LITELLM_PROXY_API_KEY=...
export EVAL_OPENAI_MODEL=gpt-4o-mini
```

### Custom Dataset
```bash
# Generate traces for a custom dataset
agents-cli eval generate --dataset tests/eval/datasets/custom-dataset.json --output custom_traces/
agents-cli eval grade --metrics general_quality --traces custom_traces/
```

### Common Basic Questions Eval Set
```bash
agents-cli eval generate \
  --dataset tests/eval/datasets/common-basic-questions.json \
  --output artifacts/traces/common-basic-questions/

agents-cli eval grade \
  --traces artifacts/traces/common-basic-questions/
```

`common-basic-questions.json` is the starter regression set for the most common
coach interactions:

- greeting with active player context
- recent hero overview
- usual Billy build walkthrough
- late-game follow-up on a build thread
- boons definition
- spirit damage definition
- vitality definition
- spirit / vitality / weapon build-identity read
- spike / `4.8k` concept grounding
- clarifier follow-up like `what do you mean?`
- hero-specific win-rate question
- patch-anchor question using synced patch notes
- broad meta guardrail question
- missing-account behavior
- unsupported global popularity questions

### Stronger Regression Pack
```bash
agents-cli eval generate \
  --dataset tests/eval/datasets/coach-regression-pack.json \
  --output artifacts/traces/coach-regression-pack/

agents-cli eval grade \
  --traces artifacts/traces/coach-regression-pack/
```

`coach-regression-pack.json` is the heavier regression suite built from real
failure modes we have already seen in the app:

- global vs player-specific scope confusion when an active player is loaded
- rank-scoped meta questions
- full-history hero-pool questions
- concept answers for `3.2k`, `4.8k`, `6.4k`, investment bars, boons, and spirit damage
- generic hero build questions that should not silently pivot into the user's own sample
- player-specific late-game / T4 questions that must respect item tiers
- latest patch questions
- follow-up clarification recovery after a bad first interpretation
- no-account guardrails for first-person telemetry questions
- no generic coaching outro on narrow factual answers

### Multi-Turn Regression Pack
```bash
agents-cli eval generate \
  --dataset tests/eval/datasets/coach-multiturn-regression.json \
  --output artifacts/traces/coach-multiturn-regression/

agents-cli eval grade \
  --traces artifacts/traces/coach-multiturn-regression/
```

`coach-multiturn-regression.json` is the follow-up and repair suite:

- user corrections like `no i mean for everyone`
- rank-scope follow-ups like `how does it look in Eternus?`
- narrowing from late-game items to true `T4` items
- concept clarifiers like `what do you mean?`
- patch follow-ups like `what happened to Shiv?`
- scope switches from generic hero theory to player-specific telemetry
- blocked player-specific questions that then switch to a generic hero question

## Dataset Format

Each dataset file follows the Gemini Enterprise Agent Platform Evaluation
dataset format. An eval case may use **either** of two shapes — both are
valid input to `agents-cli eval generate`:

**Shape A — single-prompt case:**

```json
{
  "eval_cases": [
    {
      "eval_case_id": "unique_case_id",
      "prompt": {
        "role": "user",
        "parts": [{"text": "User message"}]
      }
    }
  ]
}
```

**Shape B — continued-conversation case (the "N+1" pattern):**
The case carries prior turns in `agent_data` and the last turn ends with a
user message; `eval generate` appends the next agent response.

```json
{
  "eval_cases": [
    {
      "eval_case_id": "unique_case_id",
      "agent_data": {
        "turns": [
          {
            "turn_index": 0,
            "events": [
              {"author": "user",  "content": {"role": "user",  "parts": [{"text": "First user message"}]}},
              {"author": "agent", "content": {"role": "model", "parts": [{"text": "First agent reply"}]}},
              {"author": "user",  "content": {"role": "user",  "parts": [{"text": "Follow-up user message"}]}}
            ]
          }
        ]
      }
    }
  ]
}
```

## Key Fields

- `eval_cases`: Array of evaluation cases.
- `eval_case_id`: Unique identifier for the evaluation case (optional).
- `prompt`: A single user message — Shape A.
- `agent_data.turns`: Prior conversation turns ending with a user message — Shape B.
- `rubrics`: Optional structured expectations for the case. We use this to carry the
  expected response shape or grounding notes that our custom grader reads.

Example rubric payload:

```json
{
  "rubrics": [
    {
      "rubricId": "expected_response",
      "rubricContent": {
        "textProperty": "Short, grounded answer that stays on the user's actual question."
      }
    }
  ]
}
```

## Creating Custom Datasets

You can create custom datasets in two ways:

1. **By Hand**: Copy `basic-dataset.json` as a template and manually add evaluation cases.
2. **Synthesize**: Use the synthetic dataset generation command to generate conversation scenarios:
   ```bash
   agents-cli eval dataset synthesize --count 10
   ```

## Discovering Metrics

You can discover available out-of-the-box evaluation metrics by running:

```bash
agents-cli eval metric list
```

## Beyond Generate and Grade

Once you have a baseline, the eval surface has a few more commands worth knowing about:

- `agents-cli eval compare BASE CAND` — diff two grade-results files (regression check).
- `agents-cli eval analyze RESULTS` — cluster failure modes from a grade-results file.
- `agents-cli eval optimize` — auto-tune your agent's prompts using eval data.

See the [Evaluation Guide](https://google.github.io/agents-cli/guide/evaluation/) for the full surface and metric reference.

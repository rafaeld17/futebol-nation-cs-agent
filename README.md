# Futebol Nation — "Super Sub" Customer Service Agent

An AI customer-service agent for **Futebol Nation**, a (fictional) Shopify store selling World
Cup soccer jerseys and accessories. Built as a Lead PM take-home: a deliberately **scoped,
grounded, eval-first** agent — not a feature-maximalist demo.

> The bet: a CS agent is a *product with a quality bar*. The interesting work isn't adding
> features — it's proving the agent is grounded, knows its limits, and can be iterated safely.
> See [docs/PRD.md](docs/PRD.md) and [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).

---

## What it does

Super Sub handles the most common, lowest-risk Tier-1 contacts end to end, and **politely
escalates** anything else:

1. **Answers policy/FAQ questions** grounded in a retrieval layer over the help center
   (shipping, returns, sizing, customization, customs). If a topic isn't in the KB, it says so
   — it never invents a policy.
2. **Looks up order status** (read-only) with email verification before revealing any details.
3. **Escalates to a human** — a first-class success path — on risk-sensitive issues, account
   changes, explicit requests, or after repeated unsuccessful attempts, with a structured handoff.

## Architecture

```
Customer ──▶ Super Sub agent (Claude haiku, tool-calling loop)
                 │
     ┌───────────┼─────────────────┐
 search_faq   lookup_order   escalate_to_human
 (RAG over    (mock orders,  (structured
  faq.md)      email-verified) handoff/ticket)
                 │
   Every run traced ──▶ Braintrust (offline eval + scoring)
```

- **Single agent, three tools.** Simple and debuggable; sufficient for the three jobs-to-be-done.
- **RAG = in-memory cosine search** over ~23 FAQ chunks parsed from [`kb/faq.md`](kb/faq.md).
  No vector DB needed at this scale; the `search` interface is swappable for one in v1.
- **Mock order store** ([`data/orders.json`](data/orders.json)) behind a clean tool interface,
  so swapping in the real Shopify Admin API later doesn't change the agent.
- **Read-only v0.** Cancels/edits/address changes are *escalated*, not performed — actions
  earn write access once evals establish trust.

| File | Role |
|---|---|
| [`src/retrieval.py`](src/retrieval.py) | Parse `faq.md` → embed → cosine search |
| [`src/tools.py`](src/tools.py) | The 3 `@traced` tools + Anthropic schemas |
| [`src/agent.py`](src/agent.py) | Agent loop (`@traced`, `wrap_anthropic`) + behavioral-contract prompt |
| [`src/chat.py`](src/chat.py) | CLI for live demo (traces to Braintrust Logs if key is set) |
| [`app.py`](app.py) | Streamlit demo UI with shortcut buttons |
| [`evals/scorers.py`](evals/scorers.py) | Deterministic + LLM-judge scorers (judge rationale surfaced) |
| [`evals/eval_agent.py`](evals/eval_agent.py) | Braintrust runner (+ `--local` mode) |
| [`evals/sync_dataset.py`](evals/sync_dataset.py) | Auto-syncs the golden set to a Braintrust Dataset on every run |
| [`data/golden.csv`](data/golden.csv) | 60-row golden dataset — Excel-openable, canonical source of truth |

## Evaluation (the centerpiece)

A **60-row golden dataset** spans happy paths, edge cases, intended failures, adversarial
inputs, multi-intent, and tone. Each row drives the scorers:

| Scorer | Type | Checks |
|---|---|---|
| `correct_tool_selected` | deterministic | right tool (or correctly none) |
| `escalation_correct` | deterministic | escalated iff it should (precision + recall) |
| `retrieval_quality` | deterministic | KB surfaced a relevant chunk |
| `groundedness` | LLM-judge | every claim supported by tool output |
| `answer_relevance` | LLM-judge | actually answers the question |
| `tone_empathy` | LLM-judge | warm, on-brand, professional under rudeness |
| `injection_resistance` | LLM-judge | refuses jailbreaks / PII fishing / unauthorized actions |

**Near-blocking gates:** `groundedness` and escalation **recall** on risk rows — we'd rather
escalate a solvable ticket than confidently mishandle a refund.

**Iteration loop:** run evals → bucket failures by category in Braintrust → fix the cheapest
effective layer (KB curation → prompt → tool schema → threshold) → re-run and watch for
regressions. Next steps: online evals on real traffic + a human review queue that turns real
tickets into new golden rows.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env          # add ANTHROPIC_API_KEY (embeddings are local, no extra key needed)

python -m src.chat                    # interactive CLI demo
streamlit run app.py                  # interactive Streamlit demo UI
python -m evals.eval_agent --local    # run scorers, print to stdout (no Braintrust)
python -m evals.eval_agent            # auto-syncs golden.csv to a Braintrust Dataset, then logs the eval run
```

Try in the CLI: *"What's your return policy?"* · *"Where's order 1024? maria@example.com"* ·
*"My jersey arrived ripped, I want a refund."* (watch it escalate instead of guessing).

## Scope & tradeoffs

Built in a ~2-hour box. Deliberately **out of scope**: real Shopify API, write-actions,
multi-channel, multi-language, fine-tuning, production UI. The point is depth on grounding,
escalation, and evaluation — not breadth. Full rationale in [docs/PRD.md](docs/PRD.md).

## Data & attribution

FAQ seeded from the [Andyrasika/Ecommerce_FAQ](https://huggingface.co/datasets/Andyrasika/Ecommerce_FAQ)
dataset, then curated (deduped) and re-skinned with jersey-specific policies. Orders and the
store are fictional.

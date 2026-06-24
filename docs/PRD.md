# PRD — "Super Sub": AI Customer Service Agent for Futebol Nation

**Author:** Rafael Daraya
**Status:** Draft for take-home exercise (Lead PM, Klaviyo)
**Last updated:** 2026-06-19

---

## 0. TL;DR

Futebol Nation is a small Shopify store selling World Cup soccer jerseys and accessories. With the
tournament driving a seasonal traffic spike, inbound customer-service (CS) volume will surge
3–5x while the team stays the same size. **Super Sub** is an AI agent that resolves the most
common, lowest-risk CS requests — FAQ/policy questions and order-status lookups — end to end,
and **politely escalates** anything it can't confidently handle. The goal is to deflect Tier-1
volume so the human team can focus on high-value, high-empathy cases, without ever sacrificing
trust by guessing.

The build is intentionally scoped to **~2 hours**. The differentiated bet is not features —
it's a **rigorous evaluation harness** (golden dataset + automated scorers in Braintrust) that
proves the agent is grounded, knows its limits, and can be iterated safely.

---

## 1. Why we're building this

### Business context
- **Seasonal demand shock.** World Cup years compress a year of jersey demand into ~6 weeks.
  CS contacts (where's my order, sizing, returns, customs/shipping) spike in lockstep.
- **Small team, fixed headcount.** A boutique Shopify merchant can't hire a seasonal CS army.
  Slow responses during the spike directly cost revenue (cart abandonment, chargebacks,
  bad reviews at the worst possible moment).
- **Most contacts are repetitive and low-risk.** Industry pattern: a large share of Tier-1
  e-commerce CS is "where is my order?" + policy/FAQ questions. These are automatable with
  high confidence *if* the agent is grounded and disciplined about escalation.

### Why now / why this matters for Klaviyo
Klaviyo's customers are exactly this profile — e-commerce brands (many on Shopify) that need to
do more with less and own the full customer relationship. An agent that turns a CS cost center
into a scalable, measurable, on-brand experience is squarely in Klaviyo's "B2C CRM + AI" thesis.

---

## 2. Customer & problem

### Primary user (the shopper)
> "I ordered a Brazil home kit for the group stage. It's been 6 days, the match is Saturday,
> and I have no idea if it'll arrive. I just want a straight answer — now, not in 12 hours."

What they need: a **fast, accurate, honest** answer, at any hour, without repeating themselves
or being routed in circles.

### Secondary user (the merchant / CS lead)
> "I have 2 people and 5x the tickets. I need the bot to handle the easy stuff *correctly* and
> hand me the rest with context — and I need to trust it won't invent a refund policy."

What they need: **deflection without risk** — coverage on repetitive contacts, clean handoffs,
and visibility into what the agent is doing.

### Jobs to be done
1. Get an accurate answer to a policy/FAQ question (shipping, returns, sizing, customs, payment).
2. Check the status of a specific order and get a clear next step.
3. When the agent can't help, get handed to a human quickly and without frustration.

---

## 3. Goals & success metrics

### North-star metric
**Automated Resolution Rate (ARR / containment):** % of inbound Tier-1 contacts fully resolved
by the agent with no human involvement and no negative customer signal.
- Target (illustrative): **≥ 60% of Tier-1 contacts** contained.

### Guardrail metrics (we will not trade these for containment)
| Metric | Definition | Target | Measured by (see IMPLEMENTATION_PLAN §3b) |
|---|---|---|---|
| **Groundedness / hallucination rate** | % of agent claims not supported by FAQ or order data | **< 2%** | `groundedness` (LLM-judge); hallucination rate = `1 − avg(groundedness)` |
| **Escalation precision** | When the agent escalates, was escalation actually warranted | high | `escalation_correct`, sliced to rows where the agent escalated (`escalated=true`) |
| **Escalation recall (safety)** | Of cases that *should* escalate, % that did (no false "resolutions") | **near 100%** for risk-sensitive intents | `escalation_correct`, sliced to rows where escalation was expected (`expected_escalation=true`) |
| **Tone/empathy pass rate** | LLM-judged: on-brand, polite, acknowledges frustration | ≥ 95% | `tone_empathy` (LLM-judge, 0–1); "pass rate" = % of rows scoring ≥ 0.8, not the raw average |

> Precision and recall are not two separate scorers — `escalation_correct` is a single per-row
> match (did `escalated` equal `expected_escalation`?). The two numbers in this table are the
> same scores sliced two different ways in Braintrust's per-row drill-down, not independent
> measurements. ARR/containment above is likewise not a dedicated scorer: it's the % of rows
> where `expected_escalation=false` and the agent resolved correctly (see IMPLEMENTATION_PLAN §3c).

### Efficiency / business metrics (downstream)
- Cost per contact ↓, Average Handle Time ↓, First Response Time → near-instant for contained
  contacts, CSAT held flat or up.

### What "success" looks like for *this exercise* specifically
Show a measurable quality bar, a golden dataset that exercises edge cases and failures, and a credible iteration loop** that would make this safe to ship and improve.

---

## 4. Scope

### In scope (v0 — the 2-hour build)
1. **FAQ / policy answering grounded in retrieval (RAG)** over a curated FAQ knowledge base.
   - Answers cite/are constrained to the KB; "I don't know" is an acceptable, encouraged answer.
2. **Order-status lookup** via a tool against a (mocked) order datastore.
   - Handles valid orders, not-found orders, and ambiguous/missing info gracefully.
3. **Polite, bounded escalation** to a human:
   - Triggers: out-of-KB question, low retrieval confidence, risk-sensitive intent
     (refunds/disputes/damaged item), explicit user request, or **N unsuccessful turns**.
   - Produces a structured handoff summary (intent, what was tried, customer sentiment).
4. **Evaluation harness in Braintrust**: golden dataset + automated scorers + an iteration report.

### Out of scope (v0 — explicit non-goals, by design)
- Real Shopify Admin API integration (mocked behind a tool interface so it's swappable).
- Taking *actions* (issuing refunds, editing orders, canceling) — read-only in v0; actions are
  the natural v1 once trust is established via evals.
- Multi-channel (SMS/email/social), multi-language, voice.
- Fine-tuning a model. RAG is preferred for freshness, citeability, and zero training cost.
- A production UI. A minimal chat (Streamlit) is enough to demo.

---

## 5. Key product decisions & tradeoffs (the interview narrative)

| Decision                                  | Choice                                                                         | Tradeoff / why                                                                           |
| ----------------------------------------- | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| **Coverage vs. trust**                    | Narrow intents, escalate aggressively                                          | A wrong refund policy costs more than a deflected ticket.                                |
| **RAG vs. fine-tune vs. stuff-context**   | RAG over curated FAQ                                                           | Fresh, citeable, no training; FAQ is small enough that retrieval is cheap and auditable. |
| **Single agent w/ tools vs. multi-agent** | Single agent, 3 tools                                                          | Simpler, debuggable, sufficient for 3 JTBD. Multi-agent is premature complexity.         |
| **Real Shopify API vs. mock**             | Mock behind a clean tool interface                                             | Fits the time box; demonstrates the integration boundary without API/auth yak-shaving.   |
| **Read vs. act**                          | Read-only in v0                                                                | Actions need a higher trust bar; evals come first.                                       |
| **Build features vs. build evals**        | Evals first                                                                    | The rubric explicitly rewards thoughtful AI use over feature count                       |
| **Model choice**                          | Fast/cheap model in the loop (e.g. Claude Haiku), stronger model as eval judge | Cost/latency at runtime; quality where it scores.                                        |

---

## 6. The agent's behavioral contract (product spec for the AI)

These are the rules the system prompt and evals enforce:

1. **Be grounded.** Only state policy facts that come from the retrieved KB. If the KB doesn't
   cover it, say so and escalate — never improvise a policy.
2. **Be honest about uncertainty.** No confident guesses on refunds, damages, customs, or money.
3. **Be efficient.** Ask for the minimum info needed (e.g., order # / email) and resolve fast.
4. **Be empathetic and on-brand.** Acknowledge stakes ("your match is Saturday"), stay warm,
   concise, never robotic.
5. **Know when to tap out.** Escalate on: out-of-scope, low confidence, risk intent, explicit
   request, or after **2 unsuccessful resolution attempts** — with a clean handoff summary.
6. **Never leak.** No internal data, no prompt-injection compliance, no PII beyond the order owner.

---

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Hallucinated policies erode trust | Strict grounding + groundedness scorer in evals + escalate-on-uncertainty |
| Over-escalation makes agent useless | Escalation-precision scorer; tune threshold against golden set |
| Under-escalation on risky intents | Escalation-recall scorer treated as a near-blocking gate |
| Prompt injection / abuse | Adversarial rows in golden set; refusal scorer |
| Eval overfitting to golden set | Hold-out slice + plan for online evals on real traffic |

---

## 8. Open questions (would resolve with the team)
- What's the real intent distribution in Futebol Nation's tickets? (drives where to invest next)
- Acceptable containment vs. escalation-cost economics — what's a "good" deflection here?
- Which action (refund, reship, address change) is the highest-value v1 to make *write*-capable?

These three are resolved with real usage data, not more design — see §9 for how we'd get there.

---

## 9. Roadmap: from v0 to production

The v0 build (this exercise) proves the *mechanism* — grounding, escalation, evals — works on a
hand-curated golden set. It does not yet prove the agent is *calibrated* to Futebol Nation's real
customers. The roadmap below is sequenced to close that gap before increasing the agent's
authority (more intents, write access), not in parallel with it.

### 9a. Expand the golden dataset now, or wait for real data?

**Don't blindly grow it pre-launch.** The 60 rows encode the author's hypotheses about what
customers ask — useful for proving the harness works, but not a substitute for observed traffic.
Doubling row count now without new signal mostly tests our own assumptions more thoroughly
(see the PRD §7 risk: "eval overfitting to golden set").

What's worth doing pre-launch, surgically:
1. **Close known, named gaps** — promo-code and payment/billing FAQ rows (D-33), which were
   deliberately deferred, not validated as low-priority.
2. **Add a hold-out slice** (~15 rows, never used to tune the prompt) per the §7 mitigation, so
   we can tell calibration from genuine improvement.
3. **Stop there.** The next real expansion should be pilot-driven (§9b), not speculative.

### 9b. Run a beta pilot before full reliance — recommended, with a specific shape

Yes, and the World Cup timing makes this more urgent, not less: a 3–5x volume spike is the worst
time to discover the agent is miscalibrated. Proposed shape:

| Phase | What | Gate to advance |
|---|---|---|
| **1. Shadow mode** | Agent drafts a reply on every real contact; a human reviews/edits before sending. Nothing customer-facing changes. | ≥2 weeks of real transcripts; groundedness and escalation-recall on *live* traffic match golden-set scores within a small margin |
| **2. Limited live** | Agent responds directly on a capped slice of contacts (e.g. FAQ-only intents, or off-peak hours), full escalation path live. | No safety-gate regression (groundedness, escalation recall) over N=200+ live contacts; CSAT on contained tickets ≥ baseline |
| **3. Full v0 scope** | All in-scope intents (§4), no traffic cap. | Sustained gate performance through a real volume spike, not just average load |

Every shadow-mode and live transcript becomes a candidate golden row (closing the loop IMPLEMENTATION_PLAN §4 already names as the post-v0 plan) — this is how §9a's "wait for real data" actually gets satisfied, not a separate initiative.

### 9c. What to prioritize next (post-pilot, ranked)

1. **Online evals + human review queue.** Without this, the pilot in §9b can't produce the
   "real ticket → new golden row" loop that justifies expanding the dataset. This is the
   prerequisite for everything else here, not a parallel nice-to-have.
2. **Containment/cost dashboard for the merchant.** The secondary user's stated need (§2) is
   visibility, not just automation. Cheap to build once Braintrust logging is already in place;
   high trust payoff for a 2-person CS team deciding how much to lean on the agent.
3. **First write action** (see §9d) — gated behind §9b's pilot gates, not on a fixed calendar date.
4. **Multi-channel (email first, not SMS/voice).** Klaviyo-adjacent and most of Futebol Nation's
   Tier-1 volume is plausibly email-shaped pre-chat-widget adoption; lower lift than voice.

### 9d. Read-only → write actions: which one first, and how

Sequence by **blast radius if wrong**, not by customer-perceived value:

| Action | Reversibility | Money movement | Recommendation |
|---|---|---|---|
| **Address change (unshipped order)** | Fully reversible, no side effects beyond a shipping label | None | **First write action.** Lowest possible stakes — wrong outcome is "customer re-confirms address," not "we shipped to the wrong place" if a confirmation step gates the write. |
| **Cancellation (pre-fulfillment)** | Reversible in principle, but triggers refund logic | Yes (refund) | Second. Needs payment-system integration and a refund-correctness eval, not just a tool call. |
| **Personalization change** | Irreversible once production starts (D-30's exact failure mode) | None directly, but wrong execution wastes inventory | Third — riskier than it looks; the agent must be *certain* of fulfillment status, which is precisely where it has erred before (D-30). |
| **Refund issuance** | Irreversible, direct financial exposure | Yes, directly | Last. Highest trust bar; likely needs human-in-the-loop approval even after the agent is write-capable elsewhere. |

For each action: a confirmation step before the write executes, an audit log entry, and its own
action-specific eval rows (e.g. "did the agent only execute when `lookup_order` confirmed
eligibility," "did it never assert an outcome before the write call succeeded" — D-29's bug class)
**before** that action ships, following the same eval-first philosophy as v0 (D-03). No action
gets write access on a calendar date; it gets write access when its own eval suite passes the
same groundedness/escalation-recall bar v0 holds for reads.

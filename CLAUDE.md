# Futebol Nation — Super Sub CS Agent
## Claude context file — read this at session start to avoid re-deriving state

### What this is
A Klaviyo Lead PM take-home: a scoped AI customer-service agent for **Futebol Nation**, a
fictional Shopify soccer jersey store. The differentiator is **eval-first design** (Braintrust,
60-row golden dataset, 7 scorers) over feature breadth.

### Repo layout (all files exist)
```
futebol-nation-cs-agent/
├── CLAUDE.md                   ← you are here
├── README.md
├── app.py                      ← Streamlit demo UI (World Cup themed, shortcut buttons)
├── requirements.txt            ← anthropic, sentence-transformers, numpy, braintrust, streamlit, python-dotenv
├── .env.example                ← only ANTHROPIC_API_KEY needed (+ BRAINTRUST_API_KEY for logged runs/tracing)
├── kb/faq.md                   ← 23-chunk Q&A, single source of truth, human-editable
├── data/
│   ├── orders.json             ← 5 mock orders (shipped, processing, delivered, customs-hold, personalized)
│   └── golden.csv               ← 60-row eval dataset, 11 categories. Excel-openable; canonical (edit here, not in Braintrust)
├── docs/
│   ├── PRD.md
│   ├── IMPLEMENTATION_PLAN.md
│   └── DECISIONS.md            ← full decision log with rationale (use for presentation)
├── src/
│   ├── retrieval.py            ← parse faq.md → sentence-transformers embed → cosine search
│   ├── tools.py                ← 3 @traced tool schemas + handlers: search_faq, lookup_order, escalate_to_human
│   ├── agent.py                ← Claude haiku-4-5 loop (@traced, wrap_anthropic), behavioral-contract prompt, PROJECT_NAME constant
│   └── chat.py                 ← multi-turn CLI (init_logger for live trace -> Braintrust Logs tab)
└── evals/
    ├── scorers.py              ← 3 deterministic + 4 LLM-judge scorers (judge rationale surfaced as metadata)
    ├── eval_agent.py           ← Braintrust Eval() runner (+ --local mode, no BT needed)
    └── sync_dataset.py         ← pushes golden.csv to a Braintrust Dataset; called automatically by eval_agent.run_braintrust()
```

### Run commands
```bash
pip install -r requirements.txt
cp .env.example .env && # add ANTHROPIC_API_KEY
python -m src.chat                   # live CLI demo
streamlit run app.py                 # live Streamlit demo UI
python -m evals.eval_agent --local   # full eval, scores to stdout, zero Braintrust calls
python -m evals.eval_agent           # auto-syncs golden.csv to Braintrust Dataset, then logs the eval run
python -m evals.sync_dataset         # manual one-off dataset sync (not required -- eval_agent does this automatically)
```

### Architecture (settled — don't re-propose)
- **Single agent, 3 tools**: search_faq (RAG), lookup_order (read-only), escalate_to_human
- **RAG**: faq.md parsed on `###` boundaries → 23 chunks → sentence-transformers
  `all-MiniLM-L6-v2` embeddings → in-memory numpy cosine search. No vector DB.
- **Retrieval threshold**: `0.50` (calibrated for MiniLM; was 0.35 for OpenAI — denser space)
- **Two-layer grounding**: threshold (layer 1) → agent reasoning + groundedness scorer (layer 2)
- **Models**: Claude haiku-4-5 in the agent loop; claude-sonnet-4-6 as eval judge
- **Read-only v0**: no write actions (cancel/refund/edit) — escalate instead. Actions earn
  write access once evals establish trust.
- **Email verification** before any order data is returned (prevents PII enumeration)
- **Escalation = first-class success path**, not failure. Returns structured handoff ticket.
- **Tracing**: `wrap_anthropic` (agent + judge clients) + bare `@traced` on `agent.run()` and
  the 3 tool handlers — auto-nests under whatever's active (Eval-row span, or `init_logger`'s
  Logs context in live chat/Streamlit), no manual span code, silent no-op with no Braintrust key.
- **Dataset hosting**: `evals/sync_dataset.py` auto-syncs `data/golden.csv` to a Braintrust
  Dataset on every `eval_agent.run_braintrust()` call (idempotent upsert by row `id`) — zero
  drift between what's scored and what's visible in the UI, no separate step to remember.

### Settled decisions (do NOT revisit unless user asks)
- No OpenAI dependency. Only Anthropic API key needed.
- No ChromaDB. In-memory numpy is exact and dependency-free at 23 docs.
- KB: 23 curated chunks from 79 HF source rows (collapsed ~50 near-identical duplicates).
  Gift wrap, loyalty, price match deliberately omitted to test "don't hallucinate" behavior.
  Promo-code and payment/billing FAQs are a known, *unintentional* gap (D-33) — not test cases
  like the above, just deferred for scope; mention in presentation, don't silently ignore.
- Golden dataset: 60 rows, 11 categories. 2 near-blocking gates: groundedness + escalation
  recall on risk rows. Lives in `data/golden.csv` (not JSONL) so it's Excel-reviewable — the
  CSV is canonical; the synced Braintrust Dataset is a one-way mirror, not editable source.
- No `autoevals` dependency — bespoke scorer rubrics encode this store's specific business
  rules (e.g. "I don't know" = fully grounded) and stay reviewer-readable in the repo.
- Single-agent architecture reaffirmed (D-32) — explicitly considered and declined adding a
  second agent (router/planner) just to "look more agentic"; the existing tool-calling loop
  already satisfies the definition. The one credible v2 idea (a runtime self-critique/guardrail
  pass before sending a reply) was named but deliberately not built now.
- Write actions (cancel/modify orders) stay read-only-only (D-04, reaffirmed). Same logic
  extended to promo-code/payment gaps (D-33): named as deliberate scope boundaries for the
  video, not silently missing.
- Store name: Futebol Nation. Agent name: Super Sub.

### Real bugs found and fixed via systematic trace audit (D-27–D-31)
After the first full 60-row Braintrust run, several scores looked off on a skim of the UI. Every
flagged row's full nested trace (not just the final `reply` shown in the experiment table) was
pulled via the Braintrust REST API and diffed against what the scorers actually saw. Found and
fixed real product bugs, not just eval artifacts:
- **D-27 (highest impact):** `agent.py`'s loop *overwrote* `reply` each turn instead of
  accumulating it — on any multi-tool conversation, every turn's customer-facing text except the
  last was silently dropped from both the eval and the live `chat.py`/`app.py` output. Fixed by
  joining all turns' text instead of overwriting.
- **D-28:** `escalate_to_human` was being gated behind order verification (rule 3) when it
  shouldn't be — chargeback threats and repeated-frustration cases were stuck asking for an
  order number instead of escalating immediately. Fixed in the system prompt.
- **D-29:** Order-action escalations (cancel/edit requests) skipped calling `lookup_order`
  entirely and overpromised outcomes ("it's submitted") the agent has no authority to guarantee.
  Fixed: require `lookup_order` first, never assert the action itself is guaranteed.
- **D-30:** A genuine reasoning error — the agent said personalization "might still be possible"
  on an order its own tool output showed had already shipped. Fixed with a worked example in the
  system prompt.
- **D-31:** `groundedness`'s judge payload never included `lookup_order` results (only FAQ
  chunks) — order-status rows were being judged as "ungrounded" even when the agent correctly
  reported real order data. Fixed by threading `lookup_order` output into the trace.
- All 60-row scores from before these fixes should be treated as stale/unreliable — re-run the
  full eval after pulling this state to get a trustworthy current score.

### What's NOT done yet (as of last session)
- [ ] Re-run the full 60-row Braintrust eval after the D-27–D-31 fixes to get a clean v2 score
  (everything before these fixes used a buggy agent/scorer pipeline)
- [ ] Add promo-code + payment/billing FAQ entries (D-33) — deliberately deferred, not done
- [ ] pytest for offline logic (parsing, order lookup, email-mismatch, escalation shape)
- [ ] GitHub repo initialized + pushed
- [ ] Video script / presentation

### Threshold calibration notes
MiniLM score distribution (from calibration run):
- In-KB queries: 0.518 (return policy, lowest) to 0.871 (refunds)
- Out-of-KB: 0.289 (loyalty) to 0.518 (resale value, borderline)
- Threshold 0.50 → 9/11 correctly classified at filter level; 2 borderline cases rely on
  agent reasoning (retrieved chunk clearly doesn't answer the question → agent says "I don't know")
- "Signed shirts" (prev. problem case at 0.501 below threshold) → correctly in_kb=False

### Good presentation moments to highlight
1. "I didn't just look at scores — I pulled the raw trace and found the bot was telling
   customers the right thing, then erasing it before they saw it." (D-27, the reply-accumulation
   bug.) This is the strongest "found a failure → root-caused it → fixed it" story in the repo.
2. "Dropped OpenAI mid-build → recalibrated threshold → evals confirmed the fix." Shows iteration.
3. "Deliberate KB omissions as out-of-KB test cases — testing what the agent WON'T say." (D-08)
4. "Escalation is a product feature, not a failure mode — structured handoff ticket, sentiment flag."
5. "Two-layer grounding: threshold is first-pass; agent reasoning + groundedness scorer is the gate."
6. "Read-only v0 enforced in code, not just prose — no write tool exists." Trust-before-capability.
   Extended the same logic to two real KB gaps (promo codes, payment/billing) I found but
   deliberately didn't rush in — named as scope decisions, not hidden. (D-33)
7. "Single agent, not multi-agent — a router on top of tool-calling would just re-implement what
   tool-calling already does." Direct answer to "is this agentic enough." (D-32)

# Retrieval approaches for a mixed prose and stats corpus

Research for [#15](https://github.com/EdwardGlockner/DeadBase/issues/15). Measured 2026-09-07.

**This document does not pick an approach.** That is [#17](https://github.com/EdwardGlockner/DeadBase/issues/17)'s
job, and it also depends on where the knowledge ends up living. What follows is the measured
shape of the corpus, an honest account of what the current retriever does and does not do,
and a survey of the options with costs attached.

Every number in the "measured" sections was produced on this machine (Windows 11, 8 logical
cores, no GPU) against the corpus in this repo. Numbers taken from vendors or papers are
cited inline.

---

## 1. The corpus, measured

### 1.1 The prose half

`docs/knowledge/_imports/wiki/`, measured with `find`/`wc`:

| Metric | Value |
| --- | --- |
| Markdown files | **2,226** |
| Bytes of Markdown | **9,306,769 B = 8.88 MiB** |
| Manifest JSON alongside it (3 files) | 436,091 B |
| Lines | 323,596 |
| Words | 1,583,011 |
| Heroes / items / general pages | 57 / 178 / 1,991 |
| Curated (hand-written, non-imported) notes | **0** |

> The ticket says "~14MB". `du -sh` does report `14M`, but that is block allocation over 2,226
> small files on NTFS. The actual content is **8.88 MiB**. Cost math below uses the content size.

There are no curated notes at all: `iter_knowledge_files(curated_root, include_internal=False)`
returns 0 files. Everything indexed today is imported wiki text.

### 1.2 Chunks, under the current chunker

Produced by calling the project's own `_section_chunks` over the real corpus:

| Metric | Value |
| --- | --- |
| **Total chunks** | **27,606** |
| Distinct (file, section) pairs | 7,373 |
| Chunk body characters | 7,775,937 |
| Chunk body words | 1,506,020 |
| Mean / median chars per chunk | 281.7 / 217 |
| p90 / p99 / max chars | 566 / 1,497 / 4,823 |
| Chunks under 200 chars | 13,067 (**47.3%**) |
| Chunks over 1,024 chars (~256 tok) | 694 |
| Chunks over 2,048 chars (~512 tok) | 117 |
| Chunks containing a `\|` (table rows) | 20,065 (**72.7%**) |
| **Estimated tokens (chars / 4)** | **~1.94 M** |
| Estimated tokens (words × 1.3) | ~1.96 M |

Two facts here drive everything downstream.

**The chunk size distribution is bimodal and unmanaged.** `_chunk_text` packs a fixed 6 *lines*
per chunk with no overlap. A line is a table row in a stat card or a paragraph in a lore page,
so "6 lines" spans 217 chars at the median and 4,823 at the max. Nearly half of all chunks are
under 200 characters — often a fragment of a table with no header attached.

**This is not really a prose corpus.** 72.7% of chunks contain a pipe character. The imported
wiki is overwhelmingly stat tables that have been flattened into text. Framing the problem as
"half prose, half stats" understates it: the prose half is *itself* mostly stats, just stats
that lost their schema on the way in.

### 1.3 What the 27,606 chunks actually are

Bucketing by page title suffix:

| Bucket | Files | Chunks | % of chunks |
| --- | --- | --- | --- |
| Non-English translation subpages (`/ru`, `/zh-hans`, `/cs`, …) | 506 | 7,233 | 26.2% |
| Hero & NPC voice-line `/Quotes` pages | 63 | **8,215** | **29.8%** |
| `/Update history` changelog subpages | 271 | 799 | 2.9% |
| `/Movement` tech subpages | 23 | 143 | 0.5% |
| Everything else | 1,363 | 11,216 | 40.6% |

**59.4% of the index is translations, voice lines, or changelogs.** The Russian and
Simplified-Chinese mirrors alone are 2.2 MiB and 6,470 chunks. Only ~11,200 chunks
(roughly 0.8 M tokens) are plausibly coaching-relevant English content.

This matters more than the choice of retrieval algorithm. Every cost figure in this document —
embedding spend, index size, rerank latency — scales with chunk count, and 59% of that count
is material no coaching question will ever want. Section 6 revisits this.

### 1.4 The stats half

`src/deadlock_coach/warehouse_schema.sql` — 275 lines, **17 tables**:

`source_snapshot`, `patch_event`, `player_match`, `match_metadata`, `match_participant`,
`item_purchase`, `stat_bucket`, `leaderboard_snapshot_entry`, `analytics_snapshot`,
`hero_analytics_stat`, `item_analytics_stat`, `item_flow_summary`, `item_flow_reach`,
`item_flow_node`, `item_flow_edge`, `player_performance_curve_point`, `artifact_run`.

Every fact table carries `raw_json TEXT NOT NULL` alongside typed columns, and indexes exist
for the obvious access paths (`player_match(account_id, start_time DESC)`,
`item_purchase(account_id, item_id, bought_at_s)`).

`data/warehouse/coach.sqlite3` **does not exist in a fresh checkout** — the schema is defined,
the database is not materialised. So there are no row counts to report; the stats half is
currently a schema and an ingestion path, not data on disk. Any sizing for the structured
options below is therefore schema-shaped, not volume-grounded.

Upstream, `https://api.deadlock-api.com/v1/sql/tables` currently lists 13 queryable tables
(`active_matches`, `demo_player`, `heroes`, `item_cohort_stats_net_worth_agg_v2`,
`item_cohort_stats_time_agg_v2`, `items`, `match_player`, `match_salts`, `player_card`,
`player_match_by_match`, `player_match_history`, `player_match_roster`, `player_match_stats`)
and exposes an arbitrary-SQL endpoint at `/v1/sql`.

---

## 2. What `knowledge_base.py` does today, honestly

### 2.1 The pipeline

- **Chunking** — `_section_chunks` (line 361) splits on Markdown headings, drops boilerplate
  lines via `_clean_knowledge_content_line` (line 222), then `_chunk_text` (line 350) joins
  **6 cleaned lines per chunk with no overlap**. Chunks carry `title`, `section_title`,
  `relative_path`, `group_name`, `chunk_position`.
- **Indexing** — `_ensure_knowledge_index` (line 436) writes a `knowledge_chunk` table plus a
  contentless FTS5 virtual table `knowledge_chunk_fts` (line 458) over
  `(title, section_title, body, relative_path)` with `tokenize='porter unicode61'`.
- **Retrieval** — `search_local_knowledge` (line 679) builds an OR of quoted terms, ranks with
  `bm25(knowledge_chunk_fts, 8.0, 4.0, 1.0, 6.0)`, pulls `max(limit*12, 24)` candidates, then
  applies roughly 90 lines of hand-tuned Python re-scoring: exact-phrase bonuses per field,
  per-term word-boundary regex hits, **numeric terms weighted 2×**, `3.2k`↔`3,200` numeric
  variant expansion, a table-row bonus, an `index.md` penalty.
- **Two more retrievers exist alongside it.** `extract_knowledge_entities` (557) +
  `_lookup_entity_chunks` (620) match the query against chunk *titles*;
  `search_local_knowledge_tables` (954) and `query_local_knowledge_tables` (1070) parse
  Markdown tables back into headers/rows and can pick a max/min value column when the query
  says "best"/"highest"/"lowest". `retrieve_grounded_knowledge_context` (1165) merges all
  three with additive hand-written weights.

That last point is worth stating plainly: **the system already runs three retrievers and fuses
them.** The fusion is just additive constants rather than a principled rank fusion, and the
"semantic" layer is `SEMANTIC_QUERY_ALIASES` (line 42) — a **six-entry** hand-written synonym
dict (`weapon`→`bullet`, `vitality`→`health`, …).

### 2.2 What it does well — measured

Cold index build over all 2,226 files: **6.44 s**. Resulting `knowledge.sqlite3`: **19.3 MiB**.

Raw FTS5 `MATCH` + `bm25()` + join, 60 candidates, no Python re-ranking:

| Query | Time |
| --- | --- |
| `warp stone` | 2.4 ms |
| `mid boss spawn` | 3.7 ms |
| `metal skin cost` | 6.2 ms |
| `spirit lifesteal` | 8.7 ms |
| `infernus items` | 12.1 ms |

On **named-entity lookup it is genuinely good**, and the numeric handling earns its keep:

- *"how much does Metal Skin cost"* → top-1 is the Metal Skin item card, containing
  `| Cost | 3,200 |`. Correct.
- *"what does Warp Stone do"* → top-1 Warp Stone card, top-2 Warp Dashing tech. Correct.
- *"when does the mid boss spawn"* → top-1 Mid-Boss update history, top-3 the Mid-Boss page. Usable.
- *"soul urn objective timer"* → top-1 the Soul Urn spawn-interval changelog entry. Usable.

It is deterministic, has no query-time network dependency, no model to host, no embedding to
version, and the whole index fits in a file you can delete and rebuild in six seconds. For a
two-person team that is a real asset, not a consolation prize.

### 2.3 What it does not do — measured

**No semantics, and the failure is total, not graceful.** Same probe set:

- *"best items against Infernus"* → top 3 are `Infernus/Update history`, `Infernus/Quotes`,
  `Infernus/Quotes`. Nothing about items. "Infernus" appears in hundreds of chunks and nothing
  in the ranking distinguishes advice from a changelog or a voice line.
- *"how do I stop losing lane as Seven"* → top 3 are all `Seven/Quotes` voice lines
  ("I'm a fan of your work, Professor"). Zero laning content retrieved.
- *"what counters Lash ultimate"* → top-1 is `Strategy :: Counters` (good), then two
  `Lash/Quotes` pages.

**Ranking is dominated by entity-name frequency.** `/Quotes` pages repeat the hero name on
every line, so they out-hit real content pages for any hero-named query. Those pages are 29.8%
of the index. This is the single largest observed source of bad results, and it is a corpus
problem that no amount of BM25 weight tuning fixes.

**No cross-language handling.** A `/ru` duplicate ranked #3 for *"which items give spirit
lifesteal"*. 26.2% of the index is non-English.

**The synonym table cannot scale.** Six entries stand in for an embedding model. Every new
paraphrase a player uses is a new dict entry someone has to think of first.

**No chunk overlap.** A fact split across a 6-line boundary is not retrievable as a unit.

**Text is stored twice.** FTS5 is declared `content=''` (contentless — per the
[FTS5 docs](https://sqlite.org/fts5.html) it stores index entries only and returns NULL for
column values), but the bodies are also kept in the `knowledge_chunk` table for retrieval.
Hence 19.3 MiB on disk for 7.4 MiB of chunk text.

### 2.4 A performance defect that is not an approach problem

`search_local_knowledge` calls `_ensure_knowledge_index` on **every** query.
`_knowledge_index_signature` (line 423) `stat()`s all 2,226 files and SHA-256s the result.

**Measured: 1,235 ms, on every single search call.**

End-to-end query latency in the probe set was 1,085–1,909 ms. The actual FTS5 work is 2–12 ms.
**~99% of observed query latency is the freshness check.**

This matters for ticket #17 specifically: any comparison that treats "FTS5 is fast, vector
search is slow" is using the wrong baseline. The honest FTS5 baseline is **~10 ms**, and a
1.2 s fixed overhead currently sits in front of it that a cached mtime check would remove.

---

## 3. The approaches

### 3.1 Keyword / BM25 / FTS5 — the status quo

**What it is.** Sparse lexical matching. SQLite's FTS5 `bm25()` uses the standard Okapi BM25
with hardcoded `k1=1.2`, `b=0.75`, and per-column weights passed as trailing arguments
([FTS5 docs](https://sqlite.org/fts5.html)). Already in place.

**Build cost.** 6.44 s measured, full corpus. Zero dependencies beyond stdlib `sqlite3`.

**Run cost.** $0. 2–12 ms per query measured.

**Query-time deps.** None. Pure local SQLite.

**Free and fully local in dev?** Yes, completely.

**Ops burden.** Lowest available. One file, rebuildable in seconds, no model versioning, no
embedding drift, no service to run. Reindexing on patch day is trivial.

**Wins on.** Exact names, item and ability names, numbers, stat lookups, anything where the
user's words are the corpus's words. Measured strong on all four entity queries in §2.2.

**Loses on.** Paraphrase, intent ("how do I stop losing lane"), synonymy, anything requiring
the retriever to know that "counter" and "matchup" are related. Measured total failure on
2 of 8 probe queries and partial on 2 more.

**Evidence it is not a strawman.** [BEIR (Thakur et al., 2021)](https://arxiv.org/abs/2104.08663)
evaluated 10 retrieval systems over 18 datasets and concluded "BM25 is a robust baseline",
with dense retrievers "often underperform[ing] other approaches" out of domain. Deadlock wiki
content is squarely out-of-domain for any off-the-shelf embedding model. BM25 should not be
discarded; it should be complemented.

---

### 3.2 Dense embeddings + vector search

**What it is.** Encode each chunk into a fixed-length vector; encode the query the same way;
retrieve nearest neighbours by cosine distance.

**Build cost — measured locally, no GPU.** `all-MiniLM-L6-v2` (22.7 M params, 384-d, 256
word-piece max, Apache 2.0 —
[model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)) via ONNX on 8 CPU
cores:

- **51.5 chunks/second**
- Full 27,606-chunk corpus: **536 s ≈ 8.9 minutes, one time, $0.**

Note the 256-token truncation limit against our p99 of 1,497 chars (~370 tokens) and max of
4,823 chars — 694 chunks would be silently truncated. `BAAI/bge-m3` (1024-d, 8192-token
window, 100+ languages, MIT — [model card](https://huggingface.co/BAAI/bge-m3)) avoids that
but is far heavier to run on CPU.

**Build cost — hosted, for the full 1.94 M chunk tokens:**

| Provider / model | Price per 1M tokens | Full index build | Source |
| --- | --- | --- | --- |
| Local MiniLM on CPU | — | **$0.00** (8.9 min) | measured |
| OpenAI `text-embedding-3-small` | $0.02 | **$0.04** | [OpenAI docs](https://developers.openai.com/api/docs/models/text-embedding-3-small) |
| Voyage `voyage-4-lite` | $0.02 | **$0.04** (first 200 M tokens free) | [Voyage pricing](https://docs.voyageai.com/docs/pricing) |
| OpenAI `text-embedding-3-large` | $0.13 | **$0.25** | OpenAI docs |
| Gemini `gemini-embedding-001` | $0.15 | **$0.29** (free tier exists) | [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| Gemini Embedding 2 | $0.20 ($0.10 batch) | **$0.39** ($0.19 batch) | Gemini pricing |

**The single most important cost finding in this document: embedding this corpus costs under
$0.40 even at the most expensive hosted rate.** Build cost is not the constraint on dense
retrieval here. Operational burden and recurring re-embedding on patch days are.

**Run cost / storage — measured with `sqlite-vec` v0.1.9** (pure C, no dependencies, dual
Apache-2.0/MIT, `pip install sqlite-vec`, pre-v1 so breaking changes expected —
[repo](https://github.com/asg017/sqlite-vec)), 27,606 × 384-d:

| Vector type | DB size | Insert | KNN k=20 latency (median / p95) |
| --- | --- | --- | --- |
| float32 | 41.2 MiB | 0.82 s | **58.0 ms** / 67.3 ms |
| int8 | 10.8 MiB | 0.96 s | **25.4 ms** / 33.6 ms |
| binary | 1.9 MiB | 0.46 s | **2.7 ms** / 4.2 ms |
| (numpy in-memory brute force, float32) | 40.4 MiB RAM | — | **2.7 ms** |

Query-side embedding latency, local MiniLM: **18.8 ms median, 23.9 ms p95** (measured).

So a fully local dense path is roughly **20 ms (embed) + 25–58 ms (search) ≈ 45–80 ms/query**,
comfortably interactive, and *faster than the current implementation's 1.2 s signature check*.
At 27 k vectors an ANN index is unnecessary — brute force is fine, which removes a whole
category of index-tuning work.

**Query-time deps.** An embedding model must be reachable at query time. Local = a ~90 MB ONNX
model in-process. Hosted = a network call on the critical path, plus an outage mode.

**Free and fully local in dev?** **Yes.** Measured end to end above, at zero cost.

**Ops burden.** Moderate. The index must be rebuilt when the model changes, and the model
version becomes part of the index identity. Patch-day reindex is ~9 minutes, which is fine.
The real burden is that you now have two things that can be stale instead of one.

**Wins on.** Paraphrase and intent — exactly the queries §2.3 shows failing today. "how do I
stop losing lane" has a chance of reaching a laning section. Cross-lingual too, though here
that is a liability given 26.2% translated chunks.

**Loses on.** Exact identifiers and numbers. Dense models are notoriously weak at "3,200
souls" and at distinguishing near-identical item names. On a 72.7%-tables corpus, dense-only
would likely regress the entity/stat queries BM25 currently gets right. [MTEB (Muennighoff
et al.)](https://arxiv.org/abs/2210.07316) — 8 tasks, 58 datasets, 112 languages, 33 models —
concludes no single embedding method wins across tasks; there is no model to just pick.

---

### 3.3 Hybrid lexical + dense with rank fusion

**What it is.** Run BM25 and dense retrieval in parallel, fuse the two ranked lists. Reciprocal
Rank Fusion scores each document `1/(k + rank)` summed across lists.
[Cormack, Clarke & Büttcher, SIGIR 2009](https://dl.acm.org/doi/10.1145/1571941.1572114)
showed RRF beats both its inputs and beats Condorcet Fuse. Azure AI Search uses RRF for hybrid
queries and states the algorithm "performs best when you set `k` to a small value, such as 60"
([Microsoft Learn](https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking)).

**Build cost.** Sum of §3.1 and §3.2. Fusion itself is ~20 lines of Python and needs no
training, no tuning, and no scores — only ranks, which makes it independent of BM25's
unbounded scale and cosine's 0–1 scale.

**Run cost.** Sum of both retrievers: ~10 ms + ~45–80 ms ≈ **under 100 ms fully local**.

**Query-time deps.** Whatever the dense half needs.

**Free and fully local in dev?** Yes.

**Ops burden.** Two indexes to keep in sync, which for a two-person team is the honest cost.
But note §2.1: **three retrievers and a fusion layer already exist**, merged with additive
hand-tuned constants. Replacing those constants with RRF would *reduce* the amount of tuning
code, not add to it — RRF has one parameter and it is conventionally 60.

**Wins on.** Both classes. Hard identifiers keep working because BM25 is still there; intent
questions start working because the dense half is there. This is precisely the split this
corpus has.

**Evidence.** Anthropic's [contextual retrieval](https://www.anthropic.com/news/contextual-retrieval)
write-up reports top-20 retrieval failure rate going 5.7% → 3.7% with contextual embeddings
(−35%), → 2.9% when BM25 is added (−49%), and → 1.9% with reranking on top (−67%). Different
corpus, but the *ordering* — lexical+dense beats either alone, reranking adds more — is
consistent with BEIR's conclusion.

---

### 3.4 Reranking (cross-encoders and hosted rerank APIs)

**What it is.** Retrieve ~50–100 candidates cheaply, then score each `(query, chunk)` pair
jointly with a model that sees both at once. Far more accurate than bi-encoder cosine, and far
more expensive per document — which is why it only runs on the shortlist.

**Build cost.** Zero. Nothing to index.

**Run cost — local, measured.** `Xenova/ms-marco-MiniLM-L-6-v2` cross-encoder via ONNX on the
same 8 CPU cores:

| Candidates | Median latency | Throughput |
| --- | --- | --- |
| 20 | **1,257 ms** | 16 docs/s |
| 50 | **2,796 ms** | 18 docs/s |
| 100 | **3,859 ms** | 26 docs/s |

The model card claims **1,800 docs/second on a V100 GPU**
([card](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2), NDCG@10 74.30 on TREC DL
19, MRR@10 39.01 on MS MARCO dev, Apache 2.0). We measured **16–26 docs/s on CPU** — a 70–110×
gap. **This is the sharpest local-versus-hosted asymmetry in the whole survey.** Free local
cross-encoder reranking is viable for offline evaluation sweeps and unusable for interactive
queries, unless the shortlist is cut to roughly 10 candidates or a GPU appears.

**Run cost — hosted.** Two pricing models, and they differ by more than an order of magnitude
for chunks as small as ours (mean 281 chars ≈ 70 tokens):

- **Voyage, token-priced.** `rerank-2.5-lite` $0.02/1M, `rerank-2.5` $0.05/1M
  ([pricing](https://docs.voyageai.com/docs/pricing)). Reranking 50 candidates ≈ 3.5 k tokens
  ⇒ **~$0.00007/query**; 10,000 queries ≈ **$0.70**. Voyage lists 200 M free tokens for
  `rerank-3`/`rerank-3-lite` (not for `rerank-2`/`2.5`).
- **Cohere, search-unit-priced.** Cohere defines "a single search unit … as one query with up
  to 100 documents to be ranked", splitting any document over 500 tokens into extra
  countable chunks ([Cohere pricing](https://cohere.com/pricing)). Our chunks are ~70 tokens,
  so 50 candidates is one unit. Widely reported at roughly $1–$2.50 per 1,000 searches — I
  could **not** confirm a per-search-unit dollar figure on Cohere's current first-party
  pricing page, which now shows dedicated Model Vault hourly rates ($5.00/hr, $3,250/mo for
  Rerank 3.5). Treat the per-search figure as unverified. Even at $2/1,000, 10,000 queries
  ≈ **$20**, i.e. ~30× the Voyage token-priced equivalent for chunks this short.

**Query-time deps.** A cross-encoder in-process (slow on CPU) or a network call (fast, paid).

**Free and fully local in dev?** **Qualified yes.** Local runs at $0 but at 1.3–3.9 s. Hosted
free tiers are the problem — see §6.

**Ops burden.** Low if hosted (one API call), moderate if local (model download, ONNX runtime,
and a latency budget you have to defend).

**Wins on.** Precision at the top of the list. It is the direct fix for §2.3's dominant
failure: a cross-encoder reading `(("best items against Infernus"), (an Infernus voice line))`
scores it near zero, where BM25 scores it high. Reranking cannot recover a document the first
stage never retrieved — it fixes ranking, not recall.

---

### 3.5 Structured-first: route stats questions to SQL, text as fallback

**What it is.** Recognise that a question is about counts, rates, timings or comparisons, and
answer it by querying the warehouse rather than retrieving prose about it.

**Build cost.** No index. The cost is schema work and query surface design. The 17-table
schema already exists; `data/warehouse/coach.sqlite3` does not yet.

**Run cost.** SQLite query time — sub-millisecond to low-milliseconds on indexed columns. $0
if the query is generated by rule or template; one LLM call if generated by text-to-SQL.

**Query-time deps.** The warehouse being populated and fresh. If text-to-SQL is used, a model.

**Free and fully local in dev?** Yes for templated/parameterised queries. Text-to-SQL needs a
model, but a local one is workable for a schema this small.

**Ops burden.** Depends entirely on the mechanism. **Parameterised query templates**: low
burden, fully testable, no LLM in the loop, but every new question shape needs a new template.
**Text-to-SQL**: no per-question work, but correctness becomes probabilistic. The best system
on [BIRD](https://bird-bench.github.io/) (12,751 question–SQL pairs, 95 databases, 33.4 GB)
reaches **82.28% execution accuracy** against a **92.96% human baseline** — meaning roughly one
in five generated queries on realistic schemas is wrong. Our schema is far smaller and simpler
than BIRD's, so accuracy would be higher, but "silently returns a plausible wrong number" is a
worse failure mode than "retrieves an irrelevant paragraph", because the answer looks
authoritative.

**Wins on.** Anything that is genuinely a computation: win rates, pick rates, item purchase
timings, "am I above average for my bracket", per-patch deltas. These questions are *unanswerable*
by any text retriever, at any quality level, because the answer is not written down anywhere.
It has to be computed. No amount of embedding quality substitutes.

**Loses on.** Mechanics, rules, "what does this ability actually do". Those live only in prose.

**Note.** This is not really an alternative to the text approaches — it is the other half of
the system. The question for #17 is not "SQL or retrieval" but "what decides which one runs".

---

### 3.6 Query routing between the prose and stats halves

**What it is.** Classify the incoming question and dispatch it to the prose retriever, the
warehouse, or both.

**Already exists.** `src/deadlock_coach/semantic_router.py` (358 lines) has 13
`CapabilityRule` entries mapping capabilities to lanes — `knowledge`, `data`, `matchup`,
`practice` — with priorities and predicates (`requires_account`, `requires_global`,
`requires_patch`, `requires_matchup`). Routing is by keyword/phrase substring matching over the
normalised message, with follow-up handling that prepends the previous user turn. It is
lexical, hand-written, and — despite the filename — not semantic.

**Build cost.** Rules: already paid. Embedding-based routing: encode a handful of example
utterances per route, nearest-centroid at query time; effectively free given §3.2's numbers.
LLM routing: no build, per-query cost.

**Run cost.** Rules: microseconds, $0. Embedding router: ~19 ms (one query embed, measured),
$0 local. LLM router: one extra model call of latency and money per turn.

**Query-time deps.** None for rules; the embedding model for the embedding router; the provider
for the LLM router.

**Free and fully local in dev?** Yes for all three, given a local model.

**Ops burden.** Rules are cheap until they aren't — the failure mode is a slowly growing
phrase list nobody dares refactor, which is exactly what `SEMANTIC_QUERY_ALIASES` is on the
retrieval side. An embedding router replaces phrase lists with example utterances, which are
easier for two people to maintain and to test.

**Wins on.** Preventing the expensive-and-wrong path: sending "what's my win rate on Seven" to
a prose retriever that will confidently return a Seven voice line. Routing is what makes
§3.5's structured half reachable at all.

**Risk.** Misroutes are silent and total. A question routed to the wrong half gets a confident
answer from the wrong evidence. A router that can say "both" and let the answer layer choose is
strictly safer than one forced to pick.

---

### 3.7 Knowledge-graph / entity-centric shapes

**What it is.** Model heroes, items, abilities and their relations (counters, synergies,
components, upgrades) as a graph, and retrieve by traversal rather than by text similarity.

The domain genuinely is a graph. But the important observation is: **most of that graph is
already in the stats half, not the prose half.** The upstream API exposes
`hero-counter-stats`, `hero-synergy-stats`, `hero-comb-stats`, `item-flow-stats`, and the
warehouse schema already has `item_flow_node` / `item_flow_edge` / `item_flow_reach` tables —
literally an edge list. The entity inventory is small and enumerated: **57 heroes, 178 items**,
with manifests already mapping title → file → URL.

**Two very different options hide under this heading.**

**(a) A small hand-built entity index.** Materialise the 235 known entities with their
aliases, their canonical page, their stat card, and typed edges (`counters`, `synergises_with`,
`component_of`, `upgrades_to`) sourced from the API rather than from prose.
*Build cost:* small, mostly a mapping exercise; the alias machinery (`_entity_variants`,
`HERO_TITLE_ALIASES`, `ITEM_TITLE_ALIASES`) already exists.
*Run cost:* $0, indexed SQLite lookups.
*Free and fully local:* yes.
*Ops burden:* low-moderate; entities change on patch days but there are only 235 of them.
*Wins on:* "what counters X", "what pairs with Y", "what does Z build into" — traversal
questions where text retrieval has to hope someone wrote the answer in a sentence.

**(b) Full LLM-extracted GraphRAG.** Microsoft's [GraphRAG](https://microsoft.github.io/graphrag/)
indexing pipeline segments the corpus into TextUnits, extracts "all entities, relationships and
key claims" from each, performs Leiden hierarchical clustering, then generates bottom-up
community summaries. That is at minimum one LLM call per TextUnit plus per-community
summarisation — over 27,606 chunks. The docs give no cost figures, but Microsoft Research's own
[LazyGraphRAG announcement](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)
states LazyGraphRAG's "data indexing costs are identical to vector RAG and 0.1% of the costs of
full GraphRAG" — i.e. **full GraphRAG indexing is on the order of 1,000× vector indexing**.
Against §3.2's $0.04–$0.39, that implies tens to hundreds of dollars per full rebuild, on a
corpus that is 59.4% voice lines, translations and changelogs. Every patch day would repeat it.

*Wins on:* global, synthesising questions ("how has the item meta shifted this season") that no
chunk contains the answer to. That is a real capability gap, and also not obviously a question
this product needs to answer.

---

## 4. Comparison

Costs assume the corpus as measured: 27,606 chunks, ~1.94 M tokens. "Free local dev" means the
approach can be developed and evaluated end-to-end with no paid endpoint.

| Approach | Build cost | Run cost / query | Query-time deps | Free local dev? | Ops burden (2 devs) | Wins on |
| --- | --- | --- | --- | --- | --- | --- |
| **BM25 / FTS5** (status quo) | 6.4 s, $0 | 2–12 ms, $0 | none | ✅ full | **Lowest** — one rebuildable file | Exact names, item stats, numbers |
| **Dense embeddings** | 8.9 min local / $0.04–0.39 hosted | 45–80 ms local, $0 | embedding model | ✅ full (measured) | Moderate — model version becomes index identity | Paraphrase, intent, "how do I…" |
| **Hybrid + RRF** | sum of the two | <100 ms local, $0 | as dense | ✅ full | Moderate — 2 indexes; but replaces existing hand-tuned constants | **Both**; matches this corpus's split |
| **Rerank — local CE** | $0 | **1.3 s @20, 2.8 s @50** | ONNX model in-process | ✅ but slow | Moderate — must defend latency | Top-of-list precision; kills voice-line hits |
| **Rerank — hosted** | $0 | ~$0.00007 (Voyage tok) to ~$0.002 (Cohere unit) | network call | ⚠️ see §6 | Low — one API call | same |
| **Structured-first (SQL templates)** | schema work | <5 ms, $0 | populated warehouse | ✅ full | Low, but per-question templates | Win rates, timings, comparisons — *uncomputable* by text retrieval |
| **Structured-first (text-to-SQL)** | none | 1 LLM call | model + warehouse | ✅ with local model | Moderate — ~82% BIRD accuracy ⇒ silent wrong numbers | same, without per-question work |
| **Query routing (rules)** | already built | µs, $0 | none | ✅ full | Low → grows into an unrefactorable phrase list | Stops stats questions hitting prose |
| **Query routing (embeddings)** | negligible | ~19 ms, $0 | embedding model | ✅ full | Low — example utterances beat phrase lists | same, more robust |
| **Entity index (hand-built, 235 entities)** | small, one-off | <5 ms, $0 | none | ✅ full | Low-moderate — patch-day churn on 235 rows | Counters, synergies, components |
| **Full GraphRAG** | ~1,000× vector indexing (MSR) | LLM calls | provider | ❌ | **Highest** | Global synthesis across the corpus |

---

## 5. Cost math, grounded

One full index build of the measured 1.94 M chunk tokens:

| | Cost |
| --- | --- |
| FTS5 | **$0.00**, 6.4 s |
| Local MiniLM embeddings | **$0.00**, 8.9 min |
| Cheapest hosted embeddings (OpenAI 3-small / Voyage 4-lite) | **$0.04** |
| Most expensive hosted embeddings surveyed (Gemini Embedding 2) | **$0.39** |
| Full GraphRAG | ~1,000× the vector figure ⇒ **tens to hundreds of dollars**, per rebuild |

Recurring, at 10,000 queries:

| | Cost |
| --- | --- |
| FTS5 / local dense / local hybrid | **$0.00** |
| Hosted embedding of the *query only* (~10 tokens × 10,000 = 0.1 M tokens) | **≤$0.02** |
| Voyage `rerank-2.5-lite`, 50 candidates/query | **~$0.70** |
| Cohere Rerank, 1 search unit/query @ ~$2/1,000 (unverified) | **~$20** |

Two conclusions fall straight out. First, **hosted embedding is not a meaningful expense at
this corpus size** — the entire index costs less than a coffee, and query-side embedding is
rounding error. The reason to prefer local embeddings is operational independence, not money.
Second, **for chunks this short, token-priced reranking is ~30× cheaper than search-unit-priced
reranking**, because a search unit bills for up to 100 documents regardless of how small they
are and our mean chunk is 70 tokens.

---

## 6. What the free-dev constraint rules out immediately

**Cohere Rerank as the development path.** Trial keys are limited to **10 requests/minute** for
Rerank and, per Cohere's docs, trial keys are "limited to 1,000 API calls a month" and "not
permitted to be used for production or commercial purposes"
([rate limits](https://docs.cohere.com/docs/rate-limits)). A single evaluation sweep over a few
hundred probe queries with a handful of configurations exhausts the monthly allowance. Cohere
remains a reasonable *production* choice; it cannot be the thing you iterate against. If it is
selected, a local cross-encoder must stand in during development — and §3.4 shows that stand-in
runs 70–110× slower than the GPU figure on the model card, so the two are not
latency-interchangeable.

**Full LLM-extracted GraphRAG.** ~1,000× vector indexing cost by Microsoft Research's own
figure, repeated every patch day, on a corpus 59.4% of which is voice lines, translations and
changelogs. There is no free local path that isn't "run an LLM over 27,606 chunks on a laptop".
Rule it out for now; §3.7(a) captures the actual graph value at a fraction of the cost, and the
graph data is mostly in the API anyway.

**Text-to-SQL as an unguarded path to numbers.** Not ruled out on cost — it runs locally — but
ruled out as a *silent* mechanism. 82.28% best-in-class BIRD execution accuracy against a
92.96% human baseline means wrong numbers presented confidently. If it is used, generated SQL
needs to be constrained (allowlisted tables, validated against the schema, results
sanity-checked) rather than trusted.

**Not ruled out, contrary to expectation:**

- *Hosted embeddings.* $0.04–$0.39 for the whole corpus, and both Gemini and Voyage have free
  tiers that cover it. The argument against them is operational, not financial.
- *Voyage reranking.* Token-priced at ~$0.00007/query for our chunk size, with 200 M free
  tokens on `rerank-3`/`3-lite`. Viable even in dev.
- *Anything local.* Dense retrieval, hybrid, RRF, `sqlite-vec`, embedding-based routing and a
  hand-built entity index are all $0 and all measured working on this machine.

### The finding that outranks the approach choice

**59.4% of the index is translations, voice lines and changelogs, and voice lines are the
measured cause of the worst observed failures.** Dropping `/Quotes`, `/Update history` and the
506 non-English subpages would:

- cut the index from **27,606 → ~11,400 chunks** (−59%),
- halve every embedding, storage and rerank cost above,
- take the local embedding build from 8.9 min to ~3.7 min,
- and remove, for free, the failure mode where "best items against Infernus" returns three
  Infernus voice lines.

That is a filter in `iter_knowledge_files`, not an architecture. Whatever #17 decides, the
comparison should be run against a filtered corpus, or it will be comparing algorithms on the
basis of which one best ignores 59% of its input. Similarly, the **1,235 ms per-query signature
check** (§2.4) should be fixed before any latency comparison is taken seriously.

---

## 7. Open questions for #17

1. **Where does the knowledge live?** The whole cost model changes if the prose stops being
   2,226 imported wiki files and becomes a smaller curated set. There are currently **zero**
   curated notes. 235 entities × a curated page each is a very different corpus than 27,606
   wiki chunks, and several approaches above (local embeddings, entity index) get
   proportionally cheaper while one (BM25) gets relatively better.
2. **Is the chunker part of the decision?** 6 lines with no overlap and a 22× spread in chunk
   size is a weaker lever than any retrieval algorithm can compensate for. Section-aware,
   token-bounded chunking with table headers preserved may move quality more than dense
   retrieval does.
3. **Does the product need global synthesis?** If not, §3.7(b) is moot and the graph question
   reduces to the cheap hand-built version.
4. **What is the latency budget?** Local cross-encoder reranking at 1.3–2.8 s is either
   acceptable or disqualifying, and nothing else in the survey is close to that boundary.
5. **How is any of this measured?** There is no retrieval evaluation set in the repo. The 8
   probe queries in §2 are anecdote, not benchmark. A labelled set of ~50 real coaching
   questions with known-good source sections would let #17 decide on evidence rather than on
   the arguments in this document.

---

## Sources

Primary sources, all consulted directly:

- [SQLite FTS5 documentation](https://sqlite.org/fts5.html) — `bm25()` with k1=1.2/b=0.75, column
  weights, contentless (`content=''`) tables, `porter`/`unicode61` tokenizers, index size overhead.
- [BEIR: A Heterogenous Benchmark for Zero-shot Evaluation of Information Retrieval Models](https://arxiv.org/abs/2104.08663) —
  Thakur et al., 2021. BM25 as robust baseline; reranking best but costly; dense underperforms out of domain.
- [Reciprocal rank fusion outperforms Condorcet and individual rank learning methods](https://dl.acm.org/doi/10.1145/1571941.1572114) —
  Cormack, Clarke & Büttcher, SIGIR 2009.
- [Hybrid search scoring (RRF) — Azure AI Search](https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking) —
  RRF formula `1/(rank + k)`, k=60.
- [MTEB: Massive Text Embedding Benchmark](https://arxiv.org/abs/2210.07316) — 8 tasks, 58 datasets,
  112 languages, 33 models; no universal embedding method.
- [sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) —
  22.7 M params, 384-d, 256 word-piece limit, Apache 2.0.
- [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) — dense + sparse + multi-vector, 8192 tokens, 100+ languages, MIT.
- [cross-encoder/ms-marco-MiniLM-L6-v2](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2) —
  NDCG@10 74.30 TREC DL 19, MRR@10 39.01 MS MARCO dev, 1,800 docs/s on V100, Apache 2.0.
- [sqlite-vec](https://github.com/asg017/sqlite-vec) — pure C, no dependencies, float/int8/binary, pre-v1, Apache-2.0/MIT.
- [Ollama embedding models](https://ollama.com/blog/embedding-models) — mxbai-embed-large (334 M), nomic-embed-text (137 M), all-minilm (23 M), local `/api/embed`.
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) — embedding-001 $0.15/1M, Embedding 2 $0.20/1M, both with a free tier.
- [OpenAI text-embedding-3-small](https://developers.openai.com/api/docs/models/text-embedding-3-small) — $0.02/1M; 3-large $0.13/1M.
- [Voyage AI pricing](https://docs.voyageai.com/docs/pricing) — voyage-4-lite $0.02/1M, rerank-2.5-lite $0.02/1M, 200 M free tokens on current models.
- [Cohere pricing](https://cohere.com/pricing) — search-unit definition (1 query + ≤100 docs; >500-token docs split).
- [Cohere rate limits](https://docs.cohere.com/docs/rate-limits) — Rerank trial 10 req/min; trial keys 1,000 calls/month, non-commercial.
- [Microsoft GraphRAG documentation](https://microsoft.github.io/graphrag/) — indexing pipeline, Leiden clustering, local/global/DRIFT search.
- [LazyGraphRAG — Microsoft Research](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/) —
  "indexing costs are identical to vector RAG and 0.1% of the costs of full GraphRAG".
- [BIRD benchmark](https://bird-bench.github.io/) — 12,751 pairs, 95 DBs, 33.4 GB; best 82.28% vs 92.96% human.
- [Anthropic — Introducing Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) —
  top-20 failure rate 5.7% → 3.7% → 2.9% → 1.9% across contextual embeddings, +BM25, +reranking.
- [Deadlock API SQL table catalog](https://api.deadlock-api.com/v1/sql/tables) — 13 queryable tables.

In-repo, current: `src/deadlock_coach/knowledge_base.py`,
`src/deadlock_coach/warehouse_schema.sql`, `src/deadlock_coach/semantic_router.py`,
`src/deadlock_coach/config.py`.

Measurements in this document were produced with throwaway scripts against the live corpus:
corpus statistics via the project's own `_section_chunks`; index build and query latency via
`_ensure_knowledge_index` / `search_local_knowledge`; vector storage and KNN via `sqlite-vec`
v0.1.9 on 27,606 synthetic 384-d unit vectors; embedding and cross-encoder throughput via
`fastembed` (ONNX) on real chunk bodies. Hardware: Windows 11, 8 logical cores, no GPU.

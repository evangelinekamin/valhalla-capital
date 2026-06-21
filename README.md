# Valhalla Capital: a post-mortem

Valhalla Capital was an autonomous value-investing experiment. An agent named Valkyrie — a Python loop wrapped around a handful of language models — was given a real brokerage account, a research stack, and a mandate to find undervalued small-cap equities and trade them on its own. It ran from 13 February 2026 to 16 June 2026. It started with $1,000, ended with $902.32, hit its pre-set -10% stop, and was shut down.

This is the honest version of what happened. The numbers below were recomputed from the archived database, not transcribed from memory, and where they disagree with the original headline summary I've said so.

## Outcome

| Metric | Value |
|---|---|
| Run period | 2026-02-13 (first cycle) → 2026-06-16 (shutdown) |
| Live brokerage cutover | 2026-05-01 (IBKR, account redacted) |
| Invested capital | $1,000 (funded in four deposits: $100 + $400 + $209 + $291) |
| Final portfolio value | $902.32 ($547.63 cash + 4 positions worth $354.70) |
| Return on invested capital | -9.77% (-$97.68) — tripped the -10% stop |
| Peak value | $1,038.64 (2026-05-01, the live-cutover day) |
| Trough value | $479.03 (2026-03-20, while still on the initial $500) |
| Max drawdown from peak | -13.1% |
| LLM spend | $724.51 over 1,700 cycles |
| Broker commissions paid | $42.61 (≈4.3% of capital) |
| Proposals (overseer) | 158 → 77 filled / 71 rejected / 10 stale |
| Executions (broker) | 57 filled (33 sell, 24 buy), 18 failed, 1 pending |

The loss is almost entirely *realized*. The four positions held at shutdown (RLI, SMMT, VISN, OBE) were collectively up about $4.93 on cost. The missing ~$98 was spent on round-trips and fees that didn't work out, not on bags still being held. That distinction matters for the diagnosis: this wasn't one bad bet going to zero, it was a slow bleed from churn.

## What it was

The system was a single Hetzner box in Helsinki running everything in Docker. The brain was **overseer**: a Python agent loop talking to the raw Anthropic SDK plus OpenRouter for cheaper models, with six cycle types (quick checks every couple of hours, daily/weekly/monthly reviews, data synthesis, deep analysis) and 26 tools. Its memory lived in PostgreSQL with pgvector — decisions, learned principles, per-position theses, episodic memory, a knowledge base, and the equity curve. A separate **IBKR stack** (gateway + a trading service on TimescaleDB) handled half-Kelly position sizing, risk checks, and order execution. Feeding all of it were data pipelines scraping Twitter/Nitter, Substack newsletters, OpenInsider, news RSS, and a fundamentals/price cache.

The design was genuinely thoughtful. Every trade proposal recorded a written thesis with explicit falsification criteria. A second model on the broker side independently re-derived a buy/sell call with a win probability before anything executed. There was a thesis tracker meant to be reviewed on a schedule, a learned-principles store, and a circuit-breaker stop. On paper it had the scaffolding of a disciplined fund. Most of the interesting failures are in the gap between that scaffolding and what actually ran.

## The arc

There are two distinct phases, and the join between them is the whole story.

**February–April (home, paper-ish, $500→$1,000).** The first trade fired on 19 February — a fractional 3.24 shares of Intrepid Potash, "TIER 2 CONVICTION — Fortress balance sheet." Fractional sizing and low volume mark this as the home phase. The portfolio dipped to its all-time low of $479 on 20 March (down ~4% on the initial $500), then recovered. Two check deposits in late March topped capital up to $1,000, and through April the equity curve sat quietly between $996 and $1,029. Eight proposals in February, six in March, thirty-four in April. This was the calm part.

**May–June (live, real money, $1,000→$902).** On 1 May the account cut over to live IBKR execution, and the portfolio printed its peak of $1,038.64 the same day. Then it ground down for six weeks straight:

```
2026-05-01   1,038.64   +3.9%   <- peak, live cutover
2026-05-13     992.44   -0.8%
2026-05-29     961.91   -3.8%
2026-06-03     930.54   -7.0%
2026-06-11     912.59   -8.7%
2026-06-15     904.89   -9.5%
2026-06-16     902.32   -9.8%   <- stop tripped, shutdown
```

The decline was a grind, not a crash. The worst single down-leg was about 2.5 points (3 June). What changed at the cutover wasn't market conditions, it was *behavior*: proposals jumped to 81 in May (38 filled) from 34 the prior month. The agent got a live account and immediately started trading far more. One detail worth flagging: the equity curve holds flat across multi-day stretches (the peak value repeats verbatim for four straight readings), consistent partly with weekends but also with stale broker marks — a problem the agent complained about repeatedly (below).

## Trading behavior

Across the run the agent proposed 158 trades on 30 tickers; 77 filled, 71 were rejected by its own gates, 10 went stale before they could execute. On the broker side only 20 distinct tickers ever actually traded, with 57 fills and 18 outright failures. The most-touched names were AENT, OBE, IPI, RILY, and GPN.

The single most-traded position, **OBE (Obsidian Energy)**, is the run in miniature. The thesis was a geopolitical oil trade: Strait of Hormuz disruption, Iran–Israel escalation, "the most shorted oil producer (34.1% short interest) with GME-like short squeeze potential." The agent bought OBE near $14 in early May and then traded around it nineteen times as the headlines whipsawed — buying on escalation, trimming on de-escalation, re-buying on the next flare-up — all the way down to ~$10.30, where it was *still buying* on 16 June, the day it was shut off. The thesis was eventually invalidated twice in the tracker, once for the mundane reason "Incorrect company description."

A few structural problems show up in the data:

- **Over-trading.** Activity more than doubled at the live cutover and the loss accumulated from that point. The OBE churn is the clearest case of trading the news feed rather than a thesis.
- **Fees ate the edge.** $42.61 in commissions on a $1,000 account is 4.3% — nearly half the total loss — on positions often only a few shares wide. The agent had literally written itself the principle that costs above 2% "destroys the edge." It then paid double that.
- **The risk layer was a rubber stamp.** All 776 recorded risk checks returned `APPROVED`. Whatever the risk service was meant to catch, in practice it never once said no.
- **The agent never graded its own homework.** Every one of the 158 journal entries had falsification criteria defined and an outcome of `pending`; not one was ever reviewed. The feedback loop that was supposed to turn experience into learning was wired up but never closed.

To its credit, the agent's *rejection* gate did fire often (71 of 158 proposals blocked), and confidence on filled trades was generally high (mode 0.85). It wasn't reckless on a per-decision basis. It was undisciplined in aggregate.

## What it cost

The agent spent **$724.51** on language models across 1,700 cycles — comfortably more than it lost trading. The breakdown:

| Model | Spend | Cycles | Role |
|---|---:|---:|---|
| deepseek-v3.2 | $211.32 | 708 | cheap triage |
| claude-opus-4-6 | $153.23 | 16 | deep reviews |
| qwen-plus | $152.10 | 53 | synthesis |
| claude-sonnet-4-6 | $124.23 | 101 | analysis |
| claude-haiku-4-5 | $56.01 | 739 | quick checks |
| grok-4.1-fast | $14.03 | 64 | fast checks |
| claude-sonnet-4-5 | $13.58 | 19 | (stragglers) |

By cycle type, the 16 monthly/4 deep reviews were the expensive thinking ($5.87 and $2.37 each), but the 1,393 `quick_check` cycles dominated by volume and still rang up $159.91 in aggregate. And here's the part the agent itself kept raising: most of those quick checks found *nothing*. The phrase "signal drought" appears in 259 cycle summaries — scan after scan returning "Twitter: 0 critical alerts, News: 0 critical alerts" and then paying for the privilege. Cost per cycle actually *climbed* as the run went on, from about $0.25 in April to $0.72 in June, even as volume fell — the cheap monitoring wasn't staying cheap.

The agent noticed all of this and filed it. Among its 18 capability wishes were "Adaptive Cycle Frequency Based on Signal Quality," "Signal Drought Detection to Reduce Cycle Frequency," and three separate increasingly-exasperated requests to stop an old Sonnet build with no prompt-cache from quietly burning ~$25/week during the droughts. It was, in effect, paying a model to write its own bug reports about how much the model cost.

## What it learned

The store of "learned principles" holds 559 entries, which sounds like a lot of hard-won wisdom until you look at where they came from:

| Origin | Count | Share |
|---|---:|---:|
| MIT 18.S096 lecture notes (quant finance course) | 510 | 91% |
| Investing literature (Graham, Marks, Buffett, et al.) | 27 | 5% |
| Research frameworks | 22 | 4% |
| From its own trading experience | 0 | 0% |

Every principle carries an `evidence_count` of exactly 1 and a confidence pinned between 0.45 and 0.60. Nothing was ever reinforced by a second observation, and nothing was derived from a trade that worked or didn't. The "learning" was ingestion — the agent read a quant-finance syllabus and a value-investing bookshelf and filed the contents. That's not nothing; the corpus is coherent and well-organized. But it is not experience, and calling it "learned" oversells it.

Read as a reading list rather than a track record, it's a good one. Representative entries, verbatim:

- *"Margin of safety is the central concept of investment. Purchase securities only when market price is significantly below conservative estimate of intrinsic value."* (value_investing)
- *"Risk is not volatility. Risk is the probability of permanent capital loss. The riskiest thing in the world is believing there is no risk."* (value_investing)
- *"Commission drag compounds over time. Any position where transaction costs exceed 2% of invested capital destroys the edge. Factor costs into every sizing decision."* (risk_management) — true, and ignored.
- *"Position sizing matters more than entry price. Use half-Kelly criterion to balance growth against drawdown risk, and never exceed 25% in a single position."* (risk_management)
- *"Contrarian ideas need a catalyst. Being early without a catalyst is the same as being wrong."* (investment_analysis)
- *"Track disconfirming evidence as rigorously as confirming evidence. Confirmation bias is the single largest threat to thesis integrity."* (investment_analysis)
- *"Process over outcome. A good decision can have a bad outcome, and a bad decision can have a good outcome. Judge decisions by the quality of analysis at the time, not by hindsight."* (behavioral)
- *"No news is a valid report. Say 'nothing material, maintaining positioning' and move on. Do not elaborate on nothing. State cost of this cycle."* (process_discipline)
- *"Daily loss limits are circuit breakers, not targets."* (risk_management)

The gap between the bookshelf and the behavior is the actual lesson here. The agent could quote the discipline and could not enact it.

## Why it ended

The proximate cause is simple: the portfolio fell 9.77% against invested capital and the -10% stop did exactly what it was built to do. Honest to say, the stop *worked* — it's one of the few control surfaces that fired as designed.

The contributing causes, ranked by how well the data supports them:

1. **Churn and fees (well supported).** Trading roughly doubled at the live cutover, the loss accrued entirely after that point, the four surviving positions were break-even, and commissions alone account for ~44% of the loss. The agent traded too much, in too-small a size, against too-high a cost base.
2. **Trading the narrative (well supported).** OBE and the broader energy book were driven by Hormuz/Iran headlines and Substack/Twitter conviction signals, churned on every twist of the news cycle. This is sentiment-following dressed as a value thesis.
3. **Broken and stale data plumbing (well supported by the agent's own bug reports).** Capability wishes document IBKR portfolio state stuck on a 4-to-10-day-old timestamp, a Twitter feed frozen on one date for 8+ days, and trades proposed that silently never filled (it cites SKWD, discovered days late). At least one buy decision reasoned off a "stock is up 0.000016% today" reading — i.e., a stale price the agent mistook for a live one. You cannot value-invest on a feed that lies about the current price.
4. **An open control loop (well supported).** No journal entry was ever reviewed; every risk check passed. The mechanisms meant to create discipline and learning existed but never engaged.
5. **Market vs. alpha (uncertain — flagged).** There is no benchmark in the data. The agent itself asked for SPY tracking precisely because it couldn't tell whether its -6% (at the time) was the market or its own doing. Without that series I can't separate beta from alpha, and I won't pretend to. A concentrated small-cap book over Feb–June 2026 could have been fighting a tape as much as fighting itself.

What the data does *not* support is a story of one catastrophic trade or a sudden blow-up. It was attrition.

## What I'd do differently, and what this was worth

If I were rebuilding it, in rough priority order:

- **Trade far less.** Most of the damage was motion. A value strategy that turns over its book nineteen times on one ticker in six weeks is not a value strategy. Cap turnover hard, and make every proposed trade clear a cost hurdle the agent already knows about (it wrote the 2% rule itself).
- **Trust no feed until it's proven fresh.** Stale prices and a frozen social feed corrupted the inputs. Pre-flight freshness checks on every data source, and refuse to trade on stale marks rather than reasoning off them.
- **Close the loop.** The journal-with-falsification-criteria was a genuinely good idea undermined by never being read. Reviewing past decisions and feeding real outcomes back into the principle store is the difference between a system that ingests a textbook and one that actually learns.
- **Make the risk layer able to say no.** 776 approvals and zero rejections is not a risk check.
- **Spend models where they pay.** Roughly $725 to lose $98 is the headline absurdity. Detect droughts and back off — the agent designed this fix and never got it shipped.

And the honest accounting of worth: as a money-making venture it failed, and the all-in cost (LLM + hosting + data + the trading loss) ran to roughly $1,000 to learn that a language model with a brokerage key and a news feed will, given the chance, day-trade headlines into the ground while reciting Benjamin Graham. As an experiment it was a clean, well-instrumented run that produced an unusually legible failure: every trade, every thesis, every dollar of model spend is on record. The most useful artifact isn't the equity curve — it's the list of capability wishes, a precise self-authored diagnosis of everything that went wrong, written by the thing that was going wrong. That's the part worth keeping.

The stop held. The lights are off. The four positions are someone else's problem now.

---

## What's in this repository

The full archive of the Valhalla Capital / Valkyrie system, captured at controlled shutdown on 2026-06-16. Secrets and personal identifiers have been removed; the data is otherwise complete.

| Path | Contents |
|---|---|
| `services/` | Source for every component: `overseer` (the Valkyrie agent), `ibkr-trading-gateway`, `dashboard`, and the data pipelines (`fmp`, `twitter`, `news`, `openinsider`, `yellowbrick`, `substack`). |
| `data/csv/` | 19 analysis-ready table exports — decision journal, learned principles, theses, trades, equity curve, cycle logs. Start here. |
| `data/db/` | Full gzipped PostgreSQL dumps (overseer, trading, twitter, miniflux, fmp_cache) + the substack SQLite. Complete schema + data. |
| `data/state/` | Final portfolio state and the trade-request history. |
| `logs/` | Per-container logs from the run. |
| `meta/` | `docker-compose.yml`, systemd units, container/image inventory, and key/secret inventories (names only). |
| `docs/DATA_DICTIONARY.md` | The original archive manifest describing every table and file. |

### Provenance & integrity
Recovered from the Backblaze B2 archive `valhalla-final-20260616-2259`. `data/SHA256SUMS.bundle-original` holds checksums of the original pre-scrub bundle.

### License & use
The component code was published under permissive terms and remains reusable. The data is provided as-is for research and archival interest, includes scraped third-party content retained under archival/fair-use, and carries no warranty.

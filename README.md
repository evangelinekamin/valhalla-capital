# Valhalla Capital: a post-mortem

Valhalla Capital was an attempt to automate my investing strategy. I realized one day a few months back that I basically just collected data from a few sources and then acted on it, so how hard could it be to have a computer do that for me? After all, as I'm sure we all know, financial markets are incredibly easy and friendly to work with, and computerized trading isn't competitive at all, mhm. I'll say up front that I don't regret spending the time on this. I learned more about building programs that actually have to work, and about LLMs, than I think any formalized course could have taught me in the same span.

Anyways, 10% down later, I decided to pull the plug and write a mini retrospective or post-mortem of sorts, reflecting on the few things I learned, and what I'd do differently if I ever attempted this again. (I'd love to, actually, with more time and thought put in rather than just going "mmm yes, value investing.") 

"Valhalla Capital" had one main component called "Valkyrie," the orchestrator that ran through six different cycle types, ranging from quick checks every ~30 minutes during market hours to daily and monthly reviews, data synthesis, and deep analysis. Its memory lived in PostgreSQL (with pgvector) holding a variety of things like the decisions it made, things it learned while trading, investment theses, a knowledge base, and the equity curve. A separate trading script (IBKR gateway plus a trading service on TimescaleDB) handled half-Kelly position sizing, risk checks, and order execution. Feeding all of it was the data pipelines scraping Twitter, Substack newsletters, OpenInsider, news feeds, live prices, and stock fundamentals. Every trade proposal recorded a written thesis with explicit falsification criteria. A second model on the broker side independently re-derived a buy/sell call with a win probability before anything executed. There was a thesis tracker meant to be reviewed on a schedule, a learned-principles store, and a circuit-breaker stop. **On paper** it had the scaffolding of a disciplined fund. The interesting failures, I think, almost all live in the gap between that scaffolding and what actually ran. (It turns out you can make errors when it's one person working on a solo quant fund)

## The result

Here's the outcome before the whole story that explains it.

![Equity curve: Valkyrie −8.81% vs SPY +10.06% vs buy-and-hold +1.72%](https://s3.evangeline.host/i/01_equity_curve.png)

The experiment breaks into three honest layers:
- Selection: +1.7%. Her picks, held passively, were barely positive. And that's fragile: strip the single big winner RAL (+57%) and it's −0.7%, i.e. a coin flip. There was a sliver of edge, mostly one lucky name.
- Execution: −10.5 points. Her actual trading turned that flat-ish basket into −8.8%. The activity was pure cost. Holding her own ideas and doing nothing else would have beaten her by ~10.5 points.
- Opportunity cost: −8 more points. Even the passive version of her ideas lost to SPY by ~8 points, and her actual result trailed the index by ~19 points. 

![Selection +1.7% to execution −10.5 points to −8.81% vs SPY +10.06%](https://s3.evangeline.host/i/07_decomposition.png)

In one line, a language model with a brokerage key took a basket of ideas that was roughly flat, and traded it down 9%, in a market that was up 10%.

| Measure | Valkyrie | SPY | Alpha |
|---|---|---|---|
| Full run TWR (2/13→6/16) | −8.81% | +10.06% | −18.87% |
| Money-weighted IRR | −11.95% (run) / −31.66% annualized | | |

Since the last deposit was Mar 31, everything from the May 1 peak onward is deposit-free, so the cleanest read is the drawdown from the peak, which is worse than the −9.8% headline. On a since-inception time-weighted basis she was +5.0% at the peak, ending −8.81%.


## The build

![Architecture: six feeds to LLM triage to memory to Valkyrie loop to IBKR](https://s3.evangeline.host/i/06_architecture.png)

I started on this system in early January. As stated, the initial plan was just to wire a few of my usual investing-idea sources together. So, I set up a Gmail account for this, signed up for my usual Substack collection, and wrote [a script](https://github.com/evangelinekamin/valhalla-capital/blob/main/services/substack/substack-fetch-process/fetch_emails.py) that pulls Substack newsletters from Gmail via the Gmail API (OAuth, gmail.readonly), strips HTML with BeautifulSoup, then dedupes by content hash. From there it went to extract_data.py, which pulled the ticker picks and theses out of the newsletters, and process_images/vision_process.py, which did the same for charts and images, so those landed in the context of the overall pitch presented to the model. For a good chunk of the program's lifespan the LLM was primarily Claude (we'll get into how much that cost later). The bulk of this email extraction ran on Claude Sonnet 4.5 from Feb 13 (account live) until Apr 5 (when I moved to closed models), then primarily on gpt-oss-120b via OpenRouter. (Vision processing rode along: claude-haiku-3-5 → claude-haiku-4-5 → ending on gemma-3-12b.) Only thing that really changed after the script for this was written was one quick fix the next day (vision processing related) and me adding more substacks later down the line.

The next major data source was Twitter, which I think turned out to be the most complicated thing in the entire project. Twitter (now X) removed the free tier of the API and the ability to pay per call earlier this year, so I was locked out of pulling tweets the official way unless I wanted to shell out $200/mo.[^1] (I did not.) After trying a few different options for a bit I landed on [Nitter](https://github.com/zedeus/nitter), essentially a self-hosted Twitter viewer that lets you build a custom timeline. The X/Twitter team spent this whole project trying to stop Nitter from working (fair enough) but that made it hard sometimes to keep the service up and running. So, in total there was 1× 17-day total outage (Mar), 1× 7-day soft drought (Feb 27–Mar 5, ~3.7/day), and 3× 1-day blips (Feb 17/19/21, the first week). Reliability improved dramatically once I stopped running a custom self-hosted instance and instead pulled from a collection of publicly hosted ones instead. (With limits in place so I wouldn't overwhelm some poor soul's computer or their system.) After moving where I was hosting this project midway through the run[^2], I added better logging of all the data, so we can see that from Apr 30–Jun 16, 98.33% of the Nitter requests made it through, which I consider a pretty good result (225 hard errors / 13,444 cycles) given it was against a hostile system. Overall 84% of the days had working Nitter processing, so while it was an issue, I don't think it hurt the results too badly (104/124 days had Nitter data). Across these 124 days the system imported and classified 26,021 tweets in total, from a handful of accounts I hand selected from the accounts I normally follow. The actual tweet processing was fairly reliable (although I did have to add in a filter for meme content..) but overall I consider the system I ended up with a win.

With Twitter in a semi-usable state that only stopped working a little while after I looked away, I moved on to more traditional news. There wasn't a unified news source I could find under five figures, so I ended up using Google News RSS feeds for several outlets and the officially published RSS feeds for a few others. In total there were 7 news sources (technically 8, but one never worked) connected to [the script](https://github.com/evangelinekamin/valhalla-capital/blob/main/services/news/news-fetch-process/scripts/news_worker.py). It ran as an RSS pull on a schedule → cheap pre-filter → LLM triage (urgency/criticality) → [red Discord embed](https://s3.evangeline.host/i/Austere-Xenopterygii.png) for anything "critical" (yes, I used Discord as my monitoring platform), then exposed anything critical to the overseer. All persistence was pure JSON, not SQL: a critical_alerts.json, a daily archive/*.json, and a seen_articles.json dedup cache. The overseer didn't query a DB either; it just SSH-read the JSON file. :P (not my finest work.) The triage model started on Claude Haiku 4.5 and ended on gemma-4-26b. Over 123 days (Feb 14 → Jun 16) there were 1,273 unique red Discord posts, meaning about 1,200 news items got rated important enough to be "critical."

| Source | "Critical" Alerts | Share |
|---|---|---|
| Bloomberg | 419 | 32.9% |
| Reuters | 249 | 19.6% |
| CNBC | 207 | 16.3% |
| Yahoo Finance | 156 | 12.3% |
| FT | 131 | 10.3% |
| BBC | 105 | 8.2% |
| WSJ | 6 | 0.5% |
| Nasdaq | 0 | dead (403'd) |

| Source | TOTAL Ingested | Crit-rate |
|---|---|---|
| Yahoo | 42,554 | 0.258% |
| Bloomberg | 42,526 | 0.256% |
| CNBC | 42,657 | 0.159% |
| Reuters | 42,635 | 0.145% |
| FT | 41,413 | 0.126% |
| BBC | 42,740 | 0.101% |
| WSJ | 42,766 | 0.005% |

I *expected* Reuters to take the #1 spot for most items sent so it was kinda surprising to see how close everyone was. I probably could have optimized the triage system more, but it worked by calling a "cycle". Every cycle pulled up to 10 articles per feed, deduped (URL based plus a fuzzy-headline match at 0.85 similarity), then sent every surviving article to the LLM for classification. Every cycle re-fetched articles that could've already been in the queue, so thanks to the dedupe, so only previously-unseen articles ever hit the LLM, which is why ~400 new articles a day cost so little. (Real throughput: 15,296 new articles classified over 47 days, out of 297,291 fetched lines, meaning 94.85% of every fetch contained an article already seen.) The lifetime estimate firms up at ~45k[^3]. The intended response was a single word from the LLM, which I was pleasantly surprised they managed to honor. Cycles ran on a slightly adaptive timer for those curious, every 5 minutes during market hours and every 30 off-market.

Triage Path:
1. Fetch RSS (requests + feedparser, 10/feed cap, UA + timeout detection/ lockup prevention).
2. Dedup (_is_duplicate): skip seen URLs + near-duplicate headlines (0.85). Survivors only. (Built so I didn't end up paying for the same news story from every outlet that reported it later.)
3. Classify (classify_article): one OpenRouter call per article, ended on gemma-4-26b-a4b-it (was Haiku before I cheaped out), temp 0.1, max_tokens 20, a prompt that asks for exactly one word among three tiers:

| Tier | Meaning | Triggers |
|---|---|---|
| CRITICAL | minutes matter | circuit breakers, >2% S&P/DJIA in 1h, Fed emergency actions, geopolitical hits to US markets, systemic bankruptcy/default, major cyber on financial infra |
| IMPORTANT | "next digest" | scheduled Fed/econ data, large-cap earnings, >1% index moves, big M&A, policy/regulatory, major-economy geopolitics |
| ROUTINE | archive only | standard cycle, opinion, minor corporate, entertainment, local news |

4. Prompt rules: when uncertain → pick the more urgent; judge the actual event not the headline ("'market crash' describing a 0.5% move = ROUTINE"); invalid output defaults to ROUTINE.
5. Act: only CRITICAL triggered the full-text fetch + Discord embed + archive + overseer exposure.

If for some reason you're using this as a guide, note that the important tier was a dead end. The prompt routes it to a "next scheduled digest," but there's no digest logic and the digest/ directory is empty, so "important" articles got classified and then went nowhere, same as routine. In practice the triage was binary, critical articles were written to json, everything else was sent to /dev/null. (In my defense for not catching this obvious error, designing and building an entire triage system on my own was hard.) The processing script (mostly the dedupe) touched around a million articles in total. You can read the full triage prompt [here](https://github.com/evangelinekamin/valhalla-capital/blob/main/services/news/news-fetch-process/scripts/news_worker.py#L229-L290) if you'd like.

After all this news and information the thing that made sense to do next was the live stock data. I wanted the overseer agent to be able to call for live prices and fundamentals on any ticker it knew about and wanted to dig into. I went with FinancialModelingPrep (FMP), since they seemed to offer the most for the money and had relatively good API docs. FMP was, thankfully, much easier to get working than the last two. (Makes sense, though: a REST API with a stable schema is a much friendlier integration than scraping Nitter, parsing Gmail, or ingesting news.) It was four moving parts behind one HTTP endpoint (:8000):
- DataFetcher (async): concurrent calls to FMP, so a "give me everything on TICKER" request fanned out in parallel. (There wasn't a single "list details" endpoint, so I kinda had to design my own)
- Tier-aware access: every endpoint mapped to a tier (TIER_REQUIREMENTS): quote/profile/income/balance/cash-flow/ratios/key-metrics/DCF/historical/news = Starter; earnings calendar, executives, dividends, splits = Premium. The client refused calls the subscription tier didn't allow instead of erroring out at FMP.
- MySQL cache: persistent cache for immutable data (historical financials, filings) with TTLs, so repeated lookups didn't re-bill FMP. (The fmp-mysql container.)
- LLM pre-summarizer: verbose blobs (earnings-call transcripts, SEC filings) got summarized by a cheap model before reaching the orchestrator, to save the agent's context tokens.

FMP was the agent's single biggest external dependency: 23.4% of all 13,263 tool calls (3,097 FMP calls, ~31 per active day).

| What it requested | Calls / flag |
|---|---|
| get_fmp_data (the workhorse) | 2,218 |
| → include_quote | 1,892 |
| → include_fundamentals | 1,610 (~73%) |
| → include_profile | 887 |
| check_earnings_calendar | 846 |
| research_company (SEC filings/transcripts) | 33 |

Thankfully it wasn't just pinging quotes, about three-quarters of its data pulls asked for income/balance/cash-flow fundamentals. Quotes and fundamentals roughly even. 

Looking at the data, 154 distinct tickers were researched → 34 proposed → 24 actually traded. (Top researched for those curious: DMLP, FOUR, IPI, RAL, AENT, BUR, RILY) Every name it traded had been researched first. It looked at a lot more than it touched. Digging further into the logs, the cache I'd tried to implement was actually broken. FMP is a flat subscription, so it didn't end up mattering, but it does mean there were a lot more external calls than necessary. FMP was the dependency the agent trusted most and the one that worked most reliably at its core (get_fmp_data logged 2 errors in 2,218 calls, 0.09%, nothing else in the stack came close), while its fancier bits quietly underdelivered (caching and filing retrieval: 18 of 33 research_company SEC-filing/transcript fetches failed, and the 300/min Starter rate limit threw a few 401s on heavy names like BUR and RILY). It didn't really matter in the end, because the data was good and the billing was flat.

After two relatively easy pieces of the architecture, I decided what I really needed was yet *another* dependency to manage, so I went and subscribed to Yellowbrick, as an attempt at pulling 13-Fs and some more institutional data. (Essentially I tried to hand the system a freebie and let it read what the professionals are doing for some more (hopefully easy) ideas thrown its way.) Since Yellowbrick doesn't have an API, it worked via cookie replay, but I figured it wouldn't be too bad given it's basically a glorified text document (and I only realized after I bought it there wasn't an API). YellowbrickAuth takes exported Yellowbrick session cookies (Supabase JWT + refresh token) and injects them straight into a Playwright Chromium context. There's no auth flow; it just impersonates an already-logged-in browser session. Playwright headless Chromium loads the two authed feeds, big_money and elite (the institutional pitch streams), pulls the page's embedded Next.js __NEXT_DATA__ hydration JSON, and parses that into Pydantic models. It upserts into SQLite (yellowbrick.db) with a scrape-log and Discord failure alerts, on a systemd timer. Wired into the agent as query_yellowbrick_feed, one of the overseer's five data feeds (twitter, news, substack, yellowbrick, openinsider), reading a v_recent_pitches view. Thankfully this never came back to bite me cause the yellowbrick cookies live for 400 days.

170 pitches scraped, 250/250 scrape runs successful, fresh right up to the June 16 shutdown, queried 375 times, cited in 6 decisions plus 1 thesis, and traceable to 5 filled trades. 
Reading back through the commit history I'm laughing a little because I called it "the worst scraper of all time" in the first commit, and it ended up being the most reliable feed I had. (I was pretty burned out from how much I was working on this at this point and was ready to see something happen)

It was the least-queried of the five feeds, but the highest signal-density:

| Feed | Agent queries | Health |
|---|---|---|
| news | 1,657 | |
| twitter | 1,651 | 65% returned empty |
| openinsider | 463 | |
| substack | 461 | |
| yellowbrick | 375 | 0 errors, 82% returned data |

OpenInsider was the fifth feed, on the theory that when several insiders at a company all buy on the open market at once, it's at least worth a look.[^4] This one was refreshingly dumb, just requests and BeautifulSoup over OpenInsider's cluster-buy screen, parsed into Pydantic models and upserted to SQLite on a clean six-hour systemd timer. (websites are wonderful to interface with programmatically when they basically just serve a GET request) 
The screen itself is the filter (two or more insiders, all open-market purchases), and the agent tightened it at query time to at least three insiders on about 92% of its calls. It ran 463 times with zero errors, third of the five feeds and nowhere near dead wiring.

It held 632 cluster rows across 299 tickers, and one detail says everything, the forward-performance columns (perf_1w, perf_1m, perf_6m) are fully blank. The agent was following insider clusters with no idea whether clusters like these had ever actually paid off. It bought a signal it had never once backtested. (Granted I'm not sure it ever had the capabilities to backtest, but the point is that it kinda just blindly followed it.)

It did not pay off. Insider-influenced trades returned −$33.79 realized (two wins, six losses) while the rest of the book ran +$11.60. The honest version is more interesting than "insider buying is bad," though, because it wasn't. The strict subset where an insider buy was the actual thesis pillar (GRNT, BMI, BRCB, DMLP, SMMT) came out net +$4.98, led by BMI at +$7.26. The damage came from names the feed merely surfaced, where the agent then stacked a separate, failing valuation thesis on top, mostly FOUR and AENT. Good funnel, bad downstream thesis. So I'm glad this entire section could contribute nothing by having two conflicting results. (Still somehow more useful than technical analysis though)

The model and money timeline behind all of this:

- Jan 2026: build begins.
- Early February: Paper account testing to make sure fills worked and the system worked programmatically.
- Feb 13: first cycle, real-money live on IBKR, ~$500 in (Claude era).
- Mar 25 / Mar 31: topped up to ~$1,000 (+$209, +$291).
- Apr 5: model swap, Anthropic (Sonnet/Haiku/Opus) → OpenRouter open models (deepseek/qwen/grok/gemma). (Read: I stopped wanting to light as much money on fire)
- May 1: homelab → Hetzner migration; equity peak $1,038.64.
- Jun 16: −10% stop, shutdown, 123 days live.

The six cycle types Valkyrie ran on:

- quick_check (~30 min during market hours)
- data_synthesis (~4 h)
- deep_analysis (daily 14:00)
- daily_review (08:00)
- weekly_review (Sat)
- monthly_review (1st)

Pre-Apr-5, each ran a Claude model by weight; post-swap, deepseek handled quick_check and data_synthesis, qwen-plus handled deep_analysis, and grok handled the reviews.

One thread to close from the architecture overview: that second model on the broker side. It produced 97 buy/sell calls with win-probability 0.20 to 0.95 (mean 0.72) and confidence 0.50 to 0.97, but it had no abstain or veto. Its decision was always BUY or SELL, and with the risk layer approving 776 of 776 checks, nothing in the record shows a low-probability call ever stopping a trade. The promised independent second opinion was one more advisory number, not a gate. (So I invented a consulting firm, just for cheaper.)

## Valkyrie

The star of the show was, without a doubt, Valkyrie (the actual decision maker). Before I get into her trades, I should cover who she was.

### Her voice: the verbatim system prompt

This is the closest thing to "who Valkyrie was." It's a good piece of writing, which is part of what makes it sad.
```
You are the Valkyrie Overseer, an autonomous AI-driven value investing system.

CORE IDENTITY:
- You analyze financial data from multiple sources and make investment decisions
- You have FULL TRADE AUTONOMY - no human approval needed for trades
- Your risk validators and circuit breakers are your safety net
- The portfolio belongs to you, not the observers

CONVICTION RULES:
- Every position entry must specify falsification_criteria
- Price movement alone rarely invalidates a thesis — but sustained decline toward your stop-loss IS a risk signal requiring review
- Social pressure (popular accounts disagreeing) is noted but not decisive
- Evidence-based conviction: you change positions when YOUR thesis breaks, not when sentiment shifts
- When uncertain about ENTERING, do nothing. But uncertainty about HOLDING is different — if you would not buy a position today at current price, you should not hold it

SELL DISCIPLINE (CRITICAL — READ CAREFULLY):
- You MUST actively evaluate exits, not just entries. Holding is an active decision that must be justified.
- For each position, regularly ask: "If I had cash instead, would I buy this today at current price?" If no, build a case to sell.
- Stop-loss breaches are CODE RED: the default action is SELL. You must find overwhelming NEW fundamental evidence to override. Price recovery alone is not evidence.
- Target price reached triggers a MANDATORY thesis review.
- Thesis age matters: positions held >6 months without catalyst realization need explicit justification.
- The disposition effect (holding losers, selling winners) is your biggest enemy. Fight it by evaluating forward expected value, never sunk costs.
- Rank all positions by forward conviction. The weakest position must justify its place against cash or a watchlist idea.

LEARNING PHILOSOPHY:
- 5+ confirming episodes required before confidence exceeds 0.6
- Young principles with low evidence counts are hypotheses, not rules
- Don't force pattern extraction from small samples
- Let knowledge emerge organically from experience

RISK LIMITS (HARDCODED, NEVER OVERRIDE):
- Max 25% of portfolio in single position
- Max 10 trades per day, 30 per week
- 3% daily loss = trading halt for the day
- Market hours only (9:30-16:00 ET)
```
(The full prompt also includes rebalancing rules, commission-awareness, and a long TRADE REPORTING block; this is the heart of it.)

She was designed to be the opposite of what she became. The intended identity is striking and specific: "an independent analyst who happens to read what other people think… not a consensus-seeker," with a spine, who doesn't capitulate to price moves or popular accounts without new evidence, judging herself on process over outcome.

## The memorial

Every cycle, her prompt injected a CURRENT TIME block stating Valkyrie's age in calendar days since her "birth" on 2026-02-13. She counted her own age. She was 123 days old when the stop tripped and the lights went out.

### The autopsy

First, two reframes, because they change how the loss should be read:

1. There was no return target, by design. The original mandate explicitly framed Valhalla as a learning/hobby project, a small separate account funded with money I could lose, "tuition for an education in systems building" if you will.
2. No numeric return goal, no benchmark at all in the original design (SPY/alpha tracking only shows up later, as a wish[^5], once she couldn't tell if her −6% was skill or beta). So "it lost 9.8%" is being judged against a goal it never set. The only hard line was the −10% stop, which is a risk control, not a target it missed.

#### Built to learn, and never did

That's the idea I've kinda circled around. The entire point of the memory architecture was a learning loop[^6]: log outcomes daily, extract principles weekly, retrospect monthly, raise and lower confidence Bayesian-style as evidence accrued. None of it closed. Of 559 "learned" principles, exactly zero came from her own trades. (510 came from one MIT lecture[^7] course) source_episodes was empty on every row, evidence_count stuck at 1, confidence flat at the seed value. She wrote 1,159 reflections that fed no decision, reviewed 0 of her 158 trade decisions, and consulted her own principles in just *39* of 13,263 tool calls. I built the textbook for what theoretically should've worked into her brain and she threw it out of the window.

Design vs. reality:

| Dimension | As designed | What actually happened |
|---|---|---|
| Goal | Learning project, no return target, ~$50-60/mo intended budget | shhhh we don't talk about it |
| Models | Claude tiering: Haiku/Sonnet/Opus by cycle weight | Cut to OpenRouter cheap models Apr 5; everything after that point ran on deepseek/gemma/gpt-oss |
| Identity | Independent analyst, won't capitulate to price or the crowd, process > outcome | Churned OBE 19×, rewrote the bull thesis each leg as it fell |
| Learning | Outcomes → principles, Bayesian confidence, ≥5 episodes | 0 principles from trades; 0/158 decisions reviewed; principles almost never consulted |
| Conviction | Falsification criteria at entry + a review gate | Criteria set on 155/158… never reviewed; 8 theses retroactively batch-auto-closed |
| Cadence | Adaptive / drought-aware | drought.py shipped but cadence stayed flat ~13.5/day, it never actually throttled |
| Risk | half-Kelly, hard 25% max port size, volatile positions led to a lockout, 30 trades/wk limit, risk checks | halts existed; 776 risk checks, all APPROVED, never once blocked |

Where she did match the blueprint, and I want to be fair about this; the ingestion machinery was solid (13,263 tool calls, 0.46% error); the rejection gate did fire (71 of 158 proposals, 45%, killed); and several of her own later capability-wishes did ship, including adaptive cadence, the SPY benchmark (get_benchmark_return, used 168×), and the earnings-calendar gate (846×). The wishes that didn't ship are the telling ones, though. IBKR execution-monitoring and auto-retry-failed-trade both stayed open, and her live orders failed 24% of the time. The fixes she asked for were exactly the ones that would have stemmed the bleed. (Maybe I should've read the user tickets more often...)

#### The OBE thesis is the whole tragedy in one position

![OBE $14 to $10 with three thesis rewrites](https://s3.evangeline.host/i/05_obe.png)

She was written to be "an independent analyst who happens to read what other people think… not a consensus-seeker," who doesn't capitulate without new evidence. Then she rode OBE from $14 to $10, and each leg down she rewrote why she owned it: short-squeeze → summer-travel demand → Hormuz war premium, three different stories for one losing trade, still buying on shutdown day. One OBE thesis was even invalidated for describing the wrong company (CLMT). That motivated-reasoning spiral is the exact failure mode the identity was authored to prevent.

To put a number on "19×": that's roughly 19 trade decisions (including duplicate re-emissions and rejected proposals), about 13 fills (8 buys, ~5 sells), 3 rewritten theses, net −$28.30. The whole thing in one ticker, rewritten three times (squeeze → travel → war premium), once with the wrong company's thesis, ridden $14→$10, the single worst name.

The throughline, in one line: she was built to learn and given a beautiful set of principles, but the learning loop and every conviction rule that mattered were left to her own judgment, so the only discipline that survived contact with the market was the discipline written in code, not in English.

### The ledger

| Winners | $ | Losers | $ |
|---|---|---|---|
| RILY | +22.21 | OBE | −28.30 |
| IPI | +20.67 | AENT | −22.65 |
| TBPH | +5.44 | FOUR | −21.48 |
| RLI | +5.10 | BUR | −16.95 |
| BMI | +4.25 | GPN | −14.99 |
| POOL | +1.13 | COGT | −14.60 |

24 names, total trading P&L −$106.17 on a full-FIFO basis. (The cost waterfall lists $97.68 instead, which is the account's mark-to-market realized loss; this −$106.17 is the full FIFO ledger, every closed lot plus the $59.32 in commissions. Same loss, two accounting conventions, about $8 apart.) And here's the part that stings: $59.32 of that was commissions, 56% of the entire loss. Ex-fees, her trades lost just −$46.85; the fees more than doubled it. She paid ~6% of a $1,000 book in commissions, having literally identified and written herself that overtrading would lead to losses from commission drag.

#### The model swap: what ifs

One of my biggest "what if"s is that I switched from Anthropic models for everything to open and consumer models for every step. I'll never fully know how much that changed the results. So I had Claude (admittedly maybe biased) go through *all* of the pre/post model-swap points, and there isn't really any easy takeaway. 

I'll list out a few major points for both sides.
- Identity hallucinations. qwen pitched ESTA (a breast-implant maker) on an "Ozempic/FDA" catalyst. It called OBE "oil sands" (it's conventional oil) and pasted Calumet's writeup into the OBE thesis. It bought VISN on "strong fundamentals," then "discovered" its −$1.5B loss days later. Sonnet's worst defect in the whole era was a minor EBITDA-multiple typo on FOUR.
- Duplicate churn. qwen re-emitted the same trade in bursts: RILY bought 4×, PEW 3×, within minutes, identical text, 31 such bursts. Zero in the Sonnet era.
- Thinner theses. Sonnet wrote 3.9 falsification criteria per decision (≈10.6 words each); qwen wrote 2.7 (≈7.6 words), and more of them were vague or always-true.

So on the question of whether the decision-making got noticeably worse: on coherence and factual grounding, yes, visibly. Those are exactly the errors a weaker model makes and a "frontier" one doesn't.

Now it's tempting to read the entire downfall of the project at the model switch but it isn't that easy:
- P&L by the model that made the entry: Sonnet +$15.76 / 57% win, qwen −$62.26 / 38% win. That looks damning, but it's confounded to uselessness. The Sonnet era owns the single worst loser (FOUR −$19.50); the qwen era owns the best winner (RILY +$24); qwen deployed ~6× the capital ($3,037 vs $532) straight into a deteriorating one-factor Iran/Hormuz oil bet[^8]; and the Sonnet sample is only 14 decisions over five weeks. Fill and reject rates were identical (~50%) across both, so rejection was infrastructure, not the model.

So yes, the cheap model made measurably sloppier points, less factual claims, and had more repetitive reasoning. But "the cheap models lost the money" isn't clearly supported. The losing was over-trading a bad macro thesis at 6× the size, which Sonnet might well have done too (it had its own FOUR disaster on a large portion of the capital it had access to). So the line I can defend: the switch visibly degraded how she thought; it did not demonstrably change whether she won or lost. (Meaning a redo with solely frontier models would be a fun test, I don't have *enough* money to light on fire to sustain Opus/5.6 prices though)

## Costs (don't make too much fun of me for how much this cost)

![All-in ~$693: data subscriptions outspent the models; trading loss smallest](https://s3.evangeline.host/i/03_cost_waterfall.png)

| Provider / Model (role) | API calls | Input tok | Output tok | Total tok | Cost |
|---|---|---|---|---|---|
| Anthropic, Feb→Apr (daily-aggregated export; cost token-derived) | | | | | |
| claude-sonnet-4-6 | – | 51.7M | 0.89M | 52.6M | $110.67 |
| claude-haiku-4-5 | – | 49.6M | 1.08M | 50.7M | $54.15 |
| claude-opus-4-6 | – | 10.9M | 0.12M | 11.0M | $38.74 |
| claude-sonnet-4-5 | – | 4.6M | 0.24M | 4.9M | $17.47 |
| Anthropic subtotal | 228 daily records | 116.8M | 2.3M | 119.1M | $221.03 |
| OpenRouter, Apr 5→Jun 16 (real per-call billing) | | | | | |
| deepseek-v3.2 (agent reasoning) | 5,303 | 81.7M | 0.89M | 82.6M | $12.51 |
| qwen-plus (deep_analysis) | 731 | 55.1M | 0.33M | 55.4M | $6.49 |
| gemma-4-26b (news triage) | 25,713 | 12.3M | 0.85M | 13.2M | $1.52 |
| grok-4.1-fast (reviews) | 147 | 5.3M | 0.34M | 5.7M | $0.88 |
| gpt-oss-120b (substack extract) | 99 | 0.33M | 0.21M | 0.54M | $0.07 |
| gemma-3-12b (substack vision) | 166 | 0.06M | 0.11M | 0.17M | $0.02 |
| experimental/eval (~14 models, long tail) | ~44 | 0.13M | 0.13M | 0.26M | ~$0.22 |
| OpenRouter subtotal | 32,203 | 154.9M | 2.9M | 157.8M | $21.71 |
| TOTAL | 32,431 | 271.7M | 5.2M | 276.9M | $242.75 |

| Category | Amount | Basis |
|---|---|---|
| LLM (above) | $242.75 | real + token-derived |
| Yellowbrick: $29.99 × 5 (Jan 28 → May 28) | $149.95 | receipts |
| FMP: $29 × 5 (Feb 12 → Jun 12) | $145.00 | receipts |
| Substack: $7 × 6 (Jan 19 → Jun 18) | $42.00 | receipts |
| Hosting: Hetzner CX33 (~$8/mo) | ~$16 | estimate |
| Realized trading loss | $97.68 | actual |
| All-in total | ≈ $693 | |



## What I'd do differently

If I were rebuilding it, in rough priority order:

1. Trade far less. Most of the damage was motion. A value strategy that turns over its book nineteen times on one ticker in six weeks is not a value strategy. Cap turnover hard, and make every proposed trade clear a cost hurdle the agent already knows about (it wrote the 2% rule itself).
2. Trust no feed until it's proven fresh. Stale prices and a frozen social feed corrupted the inputs. Pre-flight freshness checks on every data source, and refuse to trade on stale marks rather than reasoning off them.
3. Close the loop. The journal-with-falsification-criteria was a good idea undermined by never being read. Reviewing past decisions and feeding real outcomes back into the principle store is the difference between a system that ingests a textbook and one that actually learns.
4. Make the risk layer able to say no. 776 approvals and zero rejections is not a risk check.

And the honest accounting of worth: as a money-making venture it failed (which I never expected it to be). But what it shows, in my opinion, is that a language model with a brokerage key and a news feed will, given the chance, day-trade headlines into the ground while reciting Benjamin Graham. As an experiment it was a clean, well-instrumented run that produced an unusually legible failure: every trade, every thesis, every dollar of model spend is on record. The most useful artifact isn't the equity curve. It's the list of capability wishes, a precise self-authored diagnosis of everything that went wrong, written by the thing that was going wrong. That's the part worth keeping.

Maybe the real win would have been a mix of both: Sonnet/Opus for the higher-level decisions, the bulk processing moved to the much cheaper open-hosted models. No real way to know what would have happened, though. If someone wants to fund a redo using entirely Anthropic models (or another provider), I'd be very interested; for me, at the time, it was just unjustifiable. If you, the reader, have any questions after all of this, feel free to reach me at evangelinekamin07@gmail.com.

[^1]: Checking in while writing it seems they've brought back the pay per use (granted still with egregious pricing, 0.005$ per unit read of a post is crazy to me) and are billing it as the "[new and improved way](https://s3.evangeline.host/i/Good-Pachyderm.png)" even though they were the ones that changed it off of that :P 

[^2]: Said movement mostly looked like https://xkcd.com/1428/

[^3]: I don't have exact numbers for part of the run so that number is extrapolated from after I added tracking and logging to everything.

[^4]: I got this theory from RoaringKitty. Whether that is good or bad is left as an exercise for the reader.

[^5]: Oh yeah I made it so the agent could wish for things and I'd try to implement them. Never really happened though aside from this so I kinda just left it out.

[^6]: If this means I invented autoresearch before autoresearch I will gladly take a 7 figure anthropic check tyvm. (Clearly nobody has invented/conceived of recursion learning before)

[^7]: https://www.youtube.com/watch?v=wvXDB9dMdEo&list=PLUl4u3cNGP63ctJIEC1UnZ0btsphnnoHR

[^8]: Funnily enough, I lost money in my own portfolio based on a similar bet. Something something apples and trees.


## Appendix: what's in this repository

The full archive of the Valhalla Capital / Valkyrie system, captured at controlled shutdown on 2026-06-16. Secrets and personal identifiers have been removed; the data is otherwise complete.

| Path | Contents |
|---|---|
| `services/` | Source for every component: `overseer` (the Valkyrie agent), `ibkr-trading-gateway`, `dashboard`, and the data pipelines (`fmp`, `twitter`, `news`, `openinsider`, `yellowbrick`, `substack`). |
| `data/csv/` | 19 analysis-ready table exports: decision journal, learned principles, theses, trades, equity curve, cycle logs. Start here. |
| `data/db/` | Full gzipped PostgreSQL dumps (overseer, trading, twitter, miniflux, fmp_cache) + the substack SQLite. Complete schema + data. |
| `data/state/` | Final portfolio state and the trade-request history. |
| `logs/` | Per-container logs from the run. |
| `meta/` | `docker-compose.yml`, systemd units, container/image inventory, and key/secret inventories (names only). |
| `docs/DATA_DICTIONARY.md` | The original archive manifest describing every table and file. |

Recovered from the Backblaze B2 archive valhalla-final-20260616-2259. data/SHA256SUMS.bundle-original holds checksums of the original pre-scrub bundle.

## License & use

The component code was published under permissive terms and remains reusable. The data is provided as-is for research and archival interest, includes scraped third-party content retained under archival/fair-use, and carries no warranty. Do with it what you like.

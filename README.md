# ⚡ Crypto News Bot

A Telegram bot that posts **Hebrew crypto market briefings** twice a day and forwards **translated posts from tracked X (Twitter) accounts** to your groups. Pure Python standard library: no third-party dependencies.

## Features

### Scheduled briefings
- Sent at fixed Israel times, `08:00` and `20:00` by default (`BRIEFING_TIMES`). The schedule is clock-based and persisted, so restarts and deploys never shift, skip or double-send a slot (a missed slot is sent as soon as the bot is back).
- **Market snapshot:** BTC, ETH and SOL prices with 24h change (CoinGecko), a market-mood line, the Crypto Fear & Greed Index (alternative.me), BTC dominance (CoinGecko), and Gold, Oil and QQQ (Yahoo Finance).
- **News:** headlines from 5 RSS feeds (CoinDesk, CoinTelegraph, Bitcoin Magazine, The Block, Decrypt). Items from the last 8 hours, up to 3 per feed, deduplicated and filtered for crypto relevance and sponsored content. The top 5 go into the briefing.
- **AI digest:** one Gemini call rewrites the top stories as short Hebrew paragraphs ending with a 🎯 bottom line. If Gemini is unavailable, the bot falls back to a translated numbered list (Gemini batch translation, then per-item fallbacks: MyMemory, then Google Translate).

### X (Twitter) tracking
- Every 5 minutes, each tracked account's RSS feed is fetched through public Nitter mirrors (tried in order until one answers).
- New posts pass through a promo/spam filter (ads, referral codes, giveaways, PnL cards, self-promotion), a crypto keyword filter, and one Gemini call that both filters low-value posts and translates the rest to Hebrew.
- **Two-layer deduplication:** seen post IDs (last 100 per account), plus a text-similarity check against the account's last 20 forwarded posts, so the same story isn't forwarded twice.
- A post's first photo or video is forwarded with the translated caption, falling back to a text message.
- Hebrew-only by design. With `GEMINI_ONLY=1` (the default), a post that can't get a Gemini translation is skipped rather than sent in English.

### Hebrew / RTL formatting
Messages are prefixed with right-to-left marks, and Latin, ticker and number runs are wrapped in LTR isolates so mixed text like `$BTC 82K` renders in the right order. Common machine-translation mistakes in trading jargon are corrected.

## Admin commands

Only the Telegram user in `ADMIN_ID` can run commands. The command menu is shown only in the admin's private chat.

| Command | What it does |
|---|---|
| `/setup` (or `/start`) | Register the current chat for broadcasts. Inside a forum topic, the bot posts to that topic. In groups use `/setup@YourBot`. |
| `/send` | Send a briefing now to all enabled groups |
| `/list` | List tracked X accounts |
| `/add <handle or x.com URL>` | Start tracking an account (its existing posts are marked as seen) |
| `/remove <handle>` | Stop tracking an account |
| `/groups` | List registered groups |
| `/enable <id>` / `/disable <id>` / `/delgroup <id>` | Manage broadcast targets |
| `/health` | Probe the translation engines and show today's Gemini usage |
| `/check` | Per-account diagnostics: whether any mirror answered, how many posts are new, and why each would be filtered |

- **Links:** sending an `x.com/<user>` link starts tracking that account. Sending an `x.com/<user>/status/<id>` link fetches that post, translates it and broadcasts it.
- **Groups:** when the admin adds the bot to a group, the group is registered automatically. If the bot is removed from a group, the group is unregistered.

## Architecture

The bot is a single Python process with three threads:

```
main.py
 ├─ health server thread   GET / -> "OK" on $PORT (for the hosting health check)
 ├─ keep-alive thread      GET $RENDER_EXTERNAL_URL every 10 min (if set)
 └─ CryptoBot.run()        one loop, single-threaded bot logic
      ├─ Telegram getUpdates long poll (30 s) -> admin commands, group auto-registration
      ├─ every 5 min        -> Nitter RSS -> filters -> dedup -> Gemini -> broadcast
      └─ at BRIEFING_TIMES  -> prices + Fear & Greed + dominance + macro + RSS
                               -> Gemini digest (or translated list) -> broadcast
```

| File | Responsibility |
|---|---|
| `src/main.py` | Entry point: health server, keep-alive, starts the loop, exits non-zero on a crash so the host restarts it |
| `src/bot.py` | Telegram Bot API over `urllib`, commands, scheduling, broadcasting |
| `src/news.py` | Market data, RSS scraping, translation (Gemini with free fallbacks), Hebrew formatting, briefing builder |
| `src/ai_summary.py` | Gemini news digest |
| `src/twitter.py` | Nitter RSS fetching and parsing, promo filter, media extraction, captions |
| `src/storage.py` | Persistent state (accounts, groups, seen IDs, schedule) |
| `tests/` | Unit tests (`unittest`, no network) |

**State.** All state is one JSON document kept in memory. Every change is written back to the `TRACKING_DATA` environment variable through the Render API, so it survives restarts and redeploys. Without `RENDER_API_KEY` and `RENDER_SERVICE_ID`, state lives in memory only and is lost when the process stops.

## Environment variables

Names only. Never commit real values. `.env` files are gitignored.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | | Bot token from @BotFather |
| `ADMIN_ID` | yes | | Numeric Telegram user ID allowed to run commands |
| `GEMINI_API_KEY` | recommended | | Google AI Studio key for the digest and post translation |
| `GEMINI_MODEL` | no | `gemini-2.5-flash` | Gemini model ID |
| `GEMINI_DAILY_BUDGET` | no | `18` | Self-imposed cap on Gemini calls per day |
| `GEMINI_ONLY` | no | `1` | `1`: posts need a Gemini translation or are skipped. `0`: fall back to the free translators |
| `BRIEFING_TIMES` | no | `08:00,20:00` | Comma-separated `HH:MM` briefing times, Israel time |
| `BRIEFING_AI_SUMMARY` | no | `1` | `0` disables the Gemini digest in briefings |
| `COINGECKO_API_KEY` | no | | CoinGecko demo API key (higher rate limits) |
| `MYMEMORY_EMAIL` | no | | Raises MyMemory's free daily translation quota |
| `RENDER_API_KEY` | for persistence | | Render API key used to save state |
| `RENDER_SERVICE_ID` | for persistence | | ID of the Render service that stores `TRACKING_DATA` |
| `TRACKING_DATA` | managed by the bot | | JSON state written by the bot. Don't edit by hand. On a fresh deploy you may create it with `{}` |
| `PORT` | set by Render | `10000` | Port of the health-check server |
| `RENDER_EXTERNAL_URL` | set by Render | | Public URL used by the keep-alive ping |

## Run locally

Requires Python 3.11+ (CI and the Docker image use 3.12). There is nothing to `pip install`.

```bash
git clone https://github.com/aviniazov7/crypto-news-bot.git
cd crypto-news-bot
export TELEGRAM_BOT_TOKEN=<your-bot-token>
export ADMIN_ID=<your-telegram-user-id>
export GEMINI_API_KEY=<your-gemini-key>   # optional
python3 src/main.py
```

Then send `/setup` to the bot in a private chat, or add it to a group. Run the tests with:

```bash
python3 -m unittest discover -s tests -v
```

## Run with Docker

Put the variables in a `.env` file (`KEY=value` per line; it is gitignored), then:

```bash
docker build -t crypto-news-bot .
docker run --rm --env-file .env -p 10000:10000 crypto-news-bot
```

## Deploy on Render

1. **New → Web Service**, connect the repository, and choose the **Docker** runtime. The Dockerfile is used as-is.
2. Add the environment variables above. Set `RENDER_API_KEY` and `RENDER_SERVICE_ID` if state should survive deploys.
3. The built-in server answers `OK` on `/`, which satisfies the health check.

**Free-instance notes (learned the hard way):**
- Render grants **750 free instance hours per workspace per month, shared by all free web services**. An always-on bot uses about 720–744 hours by itself.
- When the hours run out, Render suspends every free service until the next month. After the monthly resume, the instance can stay asleep until it receives an HTTP request.
- **Fix:** add an external uptime monitor (for example a 5-minute HTTP check on the service URL). It keeps the bot awake, wakes it after a resume, and alerts you when it goes down. A paid instance avoids the hour limit entirely.

CI (`.github/workflows/crypto-news.yml`) runs a syntax check, an import smoke test and the unit tests on pushes to `main` and on pull requests.

## Known limitations

- **Nitter is fragile.** Posts come from public Nitter mirrors, hard-coded in `src/twitter.py`. Public instances come and go (X sent the project a cease-and-desist in August 2026). When every mirror fails, nothing is forwarded and nothing is logged; use `/check` to diagnose. Each dead mirror can also block the loop for up to 10 seconds per account.
- **Gemini free-tier limits.** The free tier allows roughly 20 requests per day and 5 per minute per Google Cloud project, shared by every key in that project. The bot doesn't pace or retry calls, so bursts of posts or `503 model overloaded` responses drop posts while `GEMINI_ONLY=1`. The daily budget counter is kept in memory: it resets on restart and at the container's midnight, not at Google's reset time.
- **Gemini models get retired.** Google retires model IDs periodically (`gemini-2.5-flash` is scheduled for shutdown). If `/health` reports `404` for Gemini, set `GEMINI_MODEL` to a current model.
- **Unofficial translation fallbacks.** The Google fallbacks use unofficial endpoints, and they and MyMemory are often rate-limited (HTTP 429) from cloud IPs.
- **State lives in one environment variable.** Every change is a Render API call. Linux caps a single environment variable at 128 KiB, which is reached at around 11–12 very active tracked accounts. Beyond that the container may fail to start.
- **Minimal Telegram error handling.** There is no retry or `retry_after` handling, only the HTTP status is logged (not Telegram's error description), and groups that migrate to a supergroup are not re-mapped automatically.
- **One loop does everything.** Commands older than 2 minutes are ignored (to avoid replays after a restart), so a slow Twitter check can swallow a command. A briefing slot is marked as sent before sending, so a failed send isn't retried. The 4096-character message limit isn't enforced (a worst-case briefing measured about 3,350 characters).

## License

[MIT](LICENSE)

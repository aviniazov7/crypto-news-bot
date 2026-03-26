# ⚡ Crypto News → Telegram (GitHub Actions)

24/7 crypto news pipeline — runs in the cloud, $0/month forever.

## Stack
- **News**: RSS feeds (CoinDesk, CoinTelegraph, Bitcoin Magazine, The Block, Decrypt)
- **Prices**: CoinGecko free API (no key)
- **Delivery**: Telegram Bot API
- **Scheduler**: GitHub Actions cron
- **Dependencies**: None (Python stdlib only)

## Schedule
Runs every 4 hours automatically. Edit `.github/workflows/crypto-news.yml` to change.

## Secrets Required
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `TELEGRAM_CHAT_ID` — from @userinfobot

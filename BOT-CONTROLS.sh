# ====================================
#  CRYPTO NEWS BOT - CONTROL GUIDE
# ====================================


# ── STOP THE BOT ──────────────────

# Option 1: From Terminal
gh workflow disable crypto-news.yml --repo aviniazov7/crypto-news-bot

# Option 2: From GitHub
# Go to: github.com/aviniazov7/crypto-news-bot
# Click: Actions → Crypto News Briefing → ⋯ → Disable workflow


# ── RESUME THE BOT ────────────────

# Option 1: From Terminal
gh workflow enable crypto-news.yml --repo aviniazov7/crypto-news-bot

# Option 2: From GitHub
# Go to: github.com/aviniazov7/crypto-news-bot
# Click: Actions → Crypto News Briefing → Enable workflow


# ── RUN MANUALLY (ONE TIME) ──────

# From GitHub:
# Actions → Crypto News Briefing → Run workflow → Run workflow


# ── DELETE EVERYTHING ─────────────

# This will delete the repo and stop the bot forever:
# gh repo delete aviniazov7/crypto-news-bot --yes

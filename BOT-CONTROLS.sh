#!/bin/bash
# ============================================
#  CRYPTO NEWS BOT — CONTROL COMMANDS
#  Keep this file for reference
# ============================================


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  STOP THE BOT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# From Terminal:
gh workflow disable crypto-news.yml --repo aviniazov7/crypto-news-bot

# From GitHub website:
# 1. Go to: github.com/aviniazov7/crypto-news-bot
# 2. Click: Actions tab
# 3. Click: Crypto News Briefing (left sidebar)
# 4. Click: ⋯ (three dots, top right)
# 5. Click: Disable workflow


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RESUME THE BOT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# From Terminal:
gh workflow enable crypto-news.yml --repo aviniazov7/crypto-news-bot

# From GitHub website:
# Same steps as above, but click: Enable workflow


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RUN ONCE (MANUALLY)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# From GitHub website:
# 1. Go to: github.com/aviniazov7/crypto-news-bot
# 2. Click: Actions tab
# 3. Click: Crypto News Briefing
# 4. Click: Run workflow (blue button)
# 5. Click: Run workflow (green button)
# 6. Wait ~30 seconds → check Telegram


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CHECK STATUS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# See last run status:
gh run list --repo aviniazov7/crypto-news-bot --limit 5

# See if workflow is enabled or disabled:
gh workflow list --repo aviniazov7/crypto-news-bot


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DELETE EVERYTHING (PERMANENT!)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# WARNING: This deletes the repo and stops the bot forever
# gh repo delete aviniazov7/crypto-news-bot --yes

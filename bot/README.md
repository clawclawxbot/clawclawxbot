# CLAWCLAWX — Telegram Crypto Info Bot

A lightweight, **info-only** Telegram bot: live crypto prices, charts, market
overview, conversions and simple price alerts. Data comes from the free
[CoinGecko API](https://www.coingecko.com/en/api).

> ℹ️ For information / education only — **not financial advice**. The bot does
> not place trades or touch any funds.

## Commands

| Command | What it does |
|---|---|
| `/start` | Welcome message |
| `/help` | List all commands |
| `/p <coin>` | Price, 24h change, market cap (e.g. `/p btc`) |
| `/chart <coin> [days]` | Price chart, default 7 days (e.g. `/chart eth 30`) |
| `/top [n]` | Top coins by market cap (default 10) |
| `/global` | Global market stats |
| `/convert <amt> <from> <to>` | Convert (e.g. `/convert 2 btc usd`) |
| `/alert <coin> <price>` | Notify when a coin crosses a price |
| `/alerts` | List your active alerts |
| `/delalert <id>` | Remove an alert |

Coins accept a symbol (`btc`) or a name (`bitcoin`).

## Setup

1. **Create the bot** — message [@BotFather](https://t.me/BotFather) on Telegram,
   send `/newbot`, follow the prompts, copy the token.

2. **Install dependencies** (Python 3.10+ recommended):

   ```bash
   cd CLAWCLAWX/bot
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure** — copy the example env file and add your token:

   ```bash
   cp .env.example .env
   # then edit .env and paste your BOT_TOKEN
   ```

4. **Run**:

   ```bash
   python bot.py
   ```

   You should see `CLAWCLAWX bot starting (polling)…`. Open Telegram, find your
   bot, and send `/start`.

## Notes

- The free CoinGecko API is rate-limited. If you hit limits, add a free demo key
  in `.env` (`COINGECKO_API_KEY=`).
- Alerts are stored in `alerts.json` next to the bot and checked every 60s.
- This uses **long polling**, so no public server/webhook is required — it runs
  fine on a laptop or any small VPS.

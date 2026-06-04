"""
CLAWCLAWX — Telegram crypto info bot.

Info-only (no trading / no money handling): live prices, charts, market
overview, coin details and simple price alerts. Data from CoinGecko's free
public API (an optional demo key raises the rate limit).

NOTE: This bot is for information / education only — it is NOT financial advice.

Commands:
  /start                welcome + button to the menu
  /help                 list all commands
  /p   <coin>           price + 24h change + market cap        (e.g. /p btc)
  /chart <coin> [days]  price chart (default 7 days)           (e.g. /chart eth 30)
  /top  [n]             top coins by market cap (default 10)
  /global               global market stats
  /convert <amt> <a> <b>  convert between coins/fiat           (e.g. /convert 2 btc usd)
  /alert <coin> <price>   notify when a coin crosses a price   (e.g. /alert btc 80000)
  /alerts               list your active alerts
  /delalert <id>        remove an alert
"""

from __future__ import annotations  # allow `X | None` type hints on Python 3.9

import io
import json
import logging
import os
from pathlib import Path

import httpx
import matplotlib

matplotlib.use("Agg")  # headless backend
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("clawclawx-bot")

# load a local .env file if python-dotenv is installed (optional)
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env"))
except Exception:  # noqa: BLE001
    pass

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CG_API_KEY = os.environ.get("COINGECKO_API_KEY", "").strip()  # optional demo key
HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY", "").strip()  # optional, Solana on-chain data
CG_BASE = "https://api.coingecko.com/api/v3"
VS = os.environ.get("VS_CURRENCY", "usd").lower()

ALERTS_FILE = Path(__file__).with_name("alerts.json")

# Common symbol -> CoinGecko id shortcuts (so /p btc works without a lookup)
ALIASES = {
    "btc": "bitcoin", "eth": "ethereum", "bnb": "binancecoin",
    "sol": "solana", "xrp": "ripple", "ada": "cardano", "doge": "dogecoin",
    "trx": "tron", "ton": "the-open-network", "avax": "avalanche-2",
    "dot": "polkadot", "matic": "matic-network", "pol": "polygon-ecosystem-token",
    "link": "chainlink", "ltc": "litecoin", "bch": "bitcoin-cash",
    "shib": "shiba-inu", "uni": "uniswap", "atom": "cosmos", "xlm": "stellar",
    "near": "near", "apt": "aptos", "arb": "arbitrum", "op": "optimism",
    "fil": "filecoin", "etc": "ethereum-classic", "icp": "internet-computer",
    "usdt": "tether", "usdc": "usd-coin", "dai": "dai", "pepe": "pepe",
    "sui": "sui", "sei": "sei-network", "render": "render-token",
}

_id_cache: dict[str, tuple[str, str]] = {}  # query -> (coin_id, symbol)


# ----------------------------------------------------------------------------
# CoinGecko helpers
# ----------------------------------------------------------------------------
def _headers() -> dict:
    return {"x-cg-demo-api-key": CG_API_KEY} if CG_API_KEY else {}


async def cg_get(path: str, params: dict | None = None) -> dict | list:
    url = f"{CG_BASE}{path}"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params or {}, headers=_headers())
        r.raise_for_status()
        return r.json()


async def resolve_coin(query: str) -> tuple[str, str] | None:
    """Resolve a user query (symbol or name) to (coin_id, SYMBOL)."""
    q = query.strip().lower()
    if not q:
        return None
    if q in ALIASES:
        return ALIASES[q], q.upper()
    if q in _id_cache:
        return _id_cache[q]
    try:
        data = await cg_get("/search", {"query": q})
        coins = data.get("coins", []) if isinstance(data, dict) else []
        if not coins:
            return None
        top = coins[0]
        result = (top["id"], top["symbol"].upper())
        _id_cache[q] = result
        return result
    except Exception as e:  # noqa: BLE001
        log.warning("resolve_coin failed for %r: %s", query, e)
        return None


def fmt_price(v: float) -> str:
    if v is None:
        return "—"
    if v >= 1:
        return f"{v:,.2f}"
    return f"{v:,.6f}".rstrip("0").rstrip(".")


def fmt_big(v: float | None) -> str:
    if not v:
        return "—"
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if v >= size:
            return f"{v / size:.2f}{unit}"
    return f"{v:,.0f}"


def arrow(change: float | None) -> str:
    if change is None:
        return ""
    return "🟢▲" if change >= 0 else "🔴▼"


# ----------------------------------------------------------------------------
# Command handlers
# ----------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📈 BTC", callback_data="ignore"),
                InlineKeyboardButton("🏆 Top 10", callback_data="ignore"),
            ],
        ]
    )
    text = (
        "<b>⚡ CLAWCLAWX — Crypto Info Bot</b>\n\n"
        "Real-time crypto prices, charts, market data & alerts.\n"
        "Info & education only — <i>not financial advice.</i>\n\n"
        "Try:\n"
        "• <code>/p btc</code> — price\n"
        "• <code>/chart eth 30</code> — 30-day chart\n"
        "• <code>/trending</code> — what's hot\n"
        "• <code>/feargreed</code> — market sentiment\n"
        "• <code>/alert btc 80000</code> — price alert\n\n"
        "Send /help for all commands."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>🦞 CLAWCLAWX commands</b>\n\n"
        "<b>Prices &amp; charts</b>\n"
        "<code>/p &lt;coin&gt;</code> — price, 24h change, market cap\n"
        "<code>/info &lt;coin&gt;</code> — rank, ATH/ATL, supply\n"
        "<code>/chart &lt;coin&gt; [days]</code> — price chart\n"
        "<code>/convert &lt;amt&gt; &lt;from&gt; &lt;to&gt;</code> — convert\n\n"
        "<b>Market</b>\n"
        "<code>/top [n]</code> — top coins by market cap\n"
        "<code>/trending</code> — trending coins\n"
        "<code>/gainers</code> · <code>/losers</code> — 24h movers\n"
        "<code>/global</code> — global market stats\n"
        "<code>/feargreed</code> — fear &amp; greed index\n\n"
        "<b>Token &amp; Solana</b>\n"
        "<code>/tokenomics</code> — $CLAWX token info\n"
        "<code>/launch</code> — how to launch a token\n"
        "<code>/sol &lt;mint&gt;</code> — Solana on-chain token info\n\n"
        "<b>Watchlist</b>\n"
        "<code>/watch &lt;coin&gt;</code> · <code>/unwatch &lt;coin&gt;</code>\n"
        "<code>/watchlist</code> — your saved coins\n\n"
        "<b>Alerts</b>\n"
        "<code>/alert &lt;coin&gt; &lt;price&gt;</code> — set an alert\n"
        "<code>/alerts</code> · <code>/delalert &lt;id&gt;</code>\n\n"
        "<i>Coin can be a symbol (btc) or name (bitcoin).</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /p <coin>   e.g. /p btc")
        return
    resolved = await resolve_coin(context.args[0])
    if not resolved:
        await update.message.reply_text("❓ Coin not found. Try /p bitcoin")
        return
    coin_id, sym = resolved
    try:
        data = await cg_get(
            "/simple/price",
            {
                "ids": coin_id,
                "vs_currencies": VS,
                "include_24hr_change": "true",
                "include_market_cap": "true",
                "include_24hr_vol": "true",
            },
        )
        d = data.get(coin_id, {})
        if not d:
            await update.message.reply_text("⚠️ No data for that coin.")
            return
        p = d.get(VS)
        chg = d.get(f"{VS}_24h_change")
        mc = d.get(f"{VS}_market_cap")
        vol = d.get(f"{VS}_24h_vol")
        cur = VS.upper()
        text = (
            f"<b>{sym}</b>  ({coin_id})\n\n"
            f"💵 Price: <b>{fmt_price(p)} {cur}</b>\n"
            f"{arrow(chg)} 24h: <b>{chg:+.2f}%</b>\n"
            f"🏦 Mkt cap: {fmt_big(mc)} {cur}\n"
            f"📊 24h vol: {fmt_big(vol)} {cur}"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:  # noqa: BLE001
        log.exception("price error")
        await update.message.reply_text(f"⚠️ Error fetching price: {e}")


async def chart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /chart <coin> [days]   e.g. /chart btc 30")
        return
    resolved = await resolve_coin(context.args[0])
    if not resolved:
        await update.message.reply_text("❓ Coin not found.")
        return
    coin_id, sym = resolved
    days = 7
    if len(context.args) > 1 and context.args[1].isdigit():
        days = max(1, min(365, int(context.args[1])))

    await update.message.chat.send_action("upload_photo")
    try:
        data = await cg_get(
            f"/coins/{coin_id}/market_chart",
            {"vs_currency": VS, "days": days},
        )
        prices = data.get("prices", [])
        if not prices:
            await update.message.reply_text("⚠️ No chart data available.")
            return
        times = [datetime.fromtimestamp(p[0] / 1000, tz=timezone.utc) for p in prices]
        values = [p[1] for p in prices]

        buf = render_chart(times, values, sym, days)
        last = values[-1]
        change = (values[-1] / values[0] - 1) * 100 if values[0] else 0
        caption = (
            f"<b>{sym}</b> — last {days}d {arrow(change)} {change:+.2f}%\n"
            f"Now: <b>{fmt_price(last)} {VS.upper()}</b>"
        )
        await update.message.reply_photo(photo=buf, caption=caption, parse_mode=ParseMode.HTML)
    except Exception as e:  # noqa: BLE001
        log.exception("chart error")
        await update.message.reply_text(f"⚠️ Error building chart: {e}")


def render_chart(times, values, sym: str, days: int) -> io.BytesIO:
    """Render a dark, blue-themed price chart to a PNG buffer."""
    up = values[-1] >= values[0]
    line = "#a855f7" if up else "#ff5d6c"
    fill = "#7c3aed" if up else "#ff5d6c"

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=130)
    fig.patch.set_facecolor("#0a0414")
    ax.set_facecolor("#0a0414")

    ax.plot(times, values, color=line, linewidth=2.2)
    ax.fill_between(times, values, min(values), color=fill, alpha=0.14)

    ax.set_title(f"{sym} · {days}d", color="#efeaff", fontsize=14, fontweight="bold", loc="left")
    ax.grid(color="#2a1b40", linewidth=0.6)
    for spine in ax.spines.values():
        spine.set_color("#2a1b40")
    ax.tick_params(colors="#9a8ab5", labelsize=8)
    if days <= 2:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.autofmt_xdate()
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    n = 10
    if context.args and context.args[0].isdigit():
        n = max(1, min(25, int(context.args[0])))
    try:
        data = await cg_get(
            "/coins/markets",
            {
                "vs_currency": VS,
                "order": "market_cap_desc",
                "per_page": n,
                "page": 1,
                "price_change_percentage": "24h",
            },
        )
        cur = VS.upper()
        lines = [f"<b>🏆 Top {n} by market cap</b>\n"]
        for i, c in enumerate(data, 1):
            chg = c.get("price_change_percentage_24h") or 0
            lines.append(
                f"{i}. <b>{c['symbol'].upper()}</b>  {fmt_price(c['current_price'])} {cur}  "
                f"{arrow(chg)} {chg:+.1f}%"
            )
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception as e:  # noqa: BLE001
        log.exception("top error")
        await update.message.reply_text(f"⚠️ Error: {e}")


async def global_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        data = await cg_get("/global")
        d = data.get("data", {})
        cur = VS.upper()
        mc = d.get("total_market_cap", {}).get(VS)
        vol = d.get("total_volume", {}).get(VS)
        btc_dom = d.get("market_cap_percentage", {}).get("btc")
        chg = d.get("market_cap_change_percentage_24h_usd")
        text = (
            "<b>🌍 Global crypto market</b>\n\n"
            f"🏦 Total mkt cap: {fmt_big(mc)} {cur}\n"
            f"📊 24h volume: {fmt_big(vol)} {cur}\n"
            f"₿ BTC dominance: {btc_dom:.1f}%\n"
            f"{arrow(chg)} 24h change: {chg:+.2f}%\n"
            f"🪙 Active coins: {d.get('active_cryptocurrencies', '—')}"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:  # noqa: BLE001
        log.exception("global error")
        await update.message.reply_text(f"⚠️ Error: {e}")


async def convert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 3:
        await update.message.reply_text("Usage: /convert <amount> <from> <to>   e.g. /convert 2 btc usd")
        return
    try:
        amount = float(context.args[0])
    except ValueError:
        await update.message.reply_text("First argument must be a number.")
        return
    frm, to = context.args[1].lower(), context.args[2].lower()
    fiats = {"usd", "eur", "idr", "gbp", "jpy", "btc", "eth"}

    async def unit_in_usd(token: str) -> float | None:
        if token in {"usd"}:
            return 1.0
        if token in {"eur", "idr", "gbp", "jpy"}:
            # use CoinGecko's simple price of bitcoin in that fiat as a bridge
            data = await cg_get("/simple/price", {"ids": "bitcoin", "vs_currencies": f"usd,{token}"})
            b = data["bitcoin"]
            return b["usd"] / b[token]  # value of 1 unit fiat in usd
        resolved = await resolve_coin(token)
        if not resolved:
            return None
        cid, _ = resolved
        data = await cg_get("/simple/price", {"ids": cid, "vs_currencies": "usd"})
        return data.get(cid, {}).get("usd")

    try:
        fu = await unit_in_usd(frm)
        tu = await unit_in_usd(to)
        if not fu or not tu:
            await update.message.reply_text("❓ Couldn't resolve one of those.")
            return
        result = amount * fu / tu
        await update.message.reply_text(
            f"<b>{amount:g} {frm.upper()}</b> ≈ <b>{fmt_price(result)} {to.upper()}</b>",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:  # noqa: BLE001
        log.exception("convert error")
        await update.message.reply_text(f"⚠️ Error: {e}")


# ----------------------------------------------------------------------------
# Price alerts (JSON-persisted, checked by a repeating job)
# ----------------------------------------------------------------------------
def load_alerts() -> list[dict]:
    if ALERTS_FILE.exists():
        try:
            return json.loads(ALERTS_FILE.read_text())
        except Exception:  # noqa: BLE001
            return []
    return []


def save_alerts(alerts: list[dict]) -> None:
    ALERTS_FILE.write_text(json.dumps(alerts, indent=2))


async def alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /alert <coin> <price>   e.g. /alert btc 80000")
        return
    resolved = await resolve_coin(context.args[0])
    if not resolved:
        await update.message.reply_text("❓ Coin not found.")
        return
    coin_id, sym = resolved
    try:
        target = float(context.args[1].replace(",", ""))
    except ValueError:
        await update.message.reply_text("Price must be a number.")
        return

    data = await cg_get("/simple/price", {"ids": coin_id, "vs_currencies": VS})
    current = data.get(coin_id, {}).get(VS)
    if current is None:
        await update.message.reply_text("⚠️ Couldn't read current price.")
        return
    direction = "above" if target >= current else "below"

    alerts = load_alerts()
    new_id = (max((a["id"] for a in alerts), default=0)) + 1
    alerts.append({
        "id": new_id,
        "chat_id": update.effective_chat.id,
        "coin_id": coin_id,
        "symbol": sym,
        "target": target,
        "direction": direction,
    })
    save_alerts(alerts)
    await update.message.reply_text(
        f"🔔 Alert #{new_id} set: notify when <b>{sym}</b> goes <b>{direction}</b> "
        f"{fmt_price(target)} {VS.upper()} (now {fmt_price(current)}).",
        parse_mode=ParseMode.HTML,
    )


async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    mine = [a for a in load_alerts() if a["chat_id"] == chat_id]
    if not mine:
        await update.message.reply_text("You have no active alerts. Set one: /alert btc 80000")
        return
    cur = VS.upper()
    lines = ["<b>🔔 Your alerts</b>\n"]
    for a in mine:
        lines.append(f"#{a['id']} — {a['symbol']} {a['direction']} {fmt_price(a['target'])} {cur}")
    lines.append("\nRemove with /delalert &lt;id&gt;")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def del_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /delalert <id>")
        return
    aid = int(context.args[0])
    chat_id = update.effective_chat.id
    alerts = load_alerts()
    kept = [a for a in alerts if not (a["id"] == aid and a["chat_id"] == chat_id)]
    if len(kept) == len(alerts):
        await update.message.reply_text("No alert with that id (or not yours).")
        return
    save_alerts(kept)
    await update.message.reply_text(f"🗑️ Alert #{aid} removed.")


async def check_alerts(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Repeating job: fetch prices for all alerted coins and fire matches."""
    alerts = load_alerts()
    if not alerts:
        return
    ids = ",".join(sorted({a["coin_id"] for a in alerts}))
    try:
        data = await cg_get("/simple/price", {"ids": ids, "vs_currencies": VS})
    except Exception as e:  # noqa: BLE001
        log.warning("alert check failed: %s", e)
        return

    remaining = []
    for a in alerts:
        price_now = data.get(a["coin_id"], {}).get(VS)
        if price_now is None:
            remaining.append(a)
            continue
        hit = (a["direction"] == "above" and price_now >= a["target"]) or (
            a["direction"] == "below" and price_now <= a["target"]
        )
        if hit:
            try:
                await context.bot.send_message(
                    chat_id=a["chat_id"],
                    text=(
                        f"🚨 <b>{a['symbol']}</b> is now {fmt_price(price_now)} {VS.upper()} "
                        f"— crossed {a['direction']} {fmt_price(a['target'])}!"
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("could not notify chat %s: %s", a["chat_id"], e)
        else:
            remaining.append(a)
    if len(remaining) != len(alerts):
        save_alerts(remaining)


# ----------------------------------------------------------------------------
# Market discovery: trending, gainers/losers, fear & greed, info
# ----------------------------------------------------------------------------
async def trending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        data = await cg_get("/search/trending")
        coins = (data.get("coins") or [])[:10]
        if not coins:
            await update.message.reply_text("⚠️ No trending data right now.")
            return
        lines = ["<b>🔥 Trending coins</b>\n"]
        for i, c in enumerate(coins, 1):
            it = c.get("item", {})
            rank = it.get("market_cap_rank")
            rank_s = f"#{rank}" if rank else "—"
            lines.append(f"{i}. <b>{it.get('symbol', '').upper()}</b> · {it.get('name', '')}  ({rank_s})")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception as e:  # noqa: BLE001
        log.exception("trending error")
        await update.message.reply_text(f"⚠️ Error: {e}")


async def _movers(update: Update, want_gainers: bool) -> None:
    try:
        data = await cg_get(
            "/coins/markets",
            {
                "vs_currency": VS,
                "order": "market_cap_desc",
                "per_page": 250,
                "page": 1,
                "price_change_percentage": "24h",
            },
        )
        ranked = [c for c in data if c.get("price_change_percentage_24h") is not None]
        ranked.sort(key=lambda c: c["price_change_percentage_24h"], reverse=want_gainers)
        cur = VS.upper()
        title = "📈 Top gainers (24h)" if want_gainers else "📉 Top losers (24h)"
        lines = [f"<b>{title}</b>\n<i>among top 250 by market cap</i>\n"]
        for i, c in enumerate(ranked[:10], 1):
            chg = c["price_change_percentage_24h"]
            lines.append(
                f"{i}. <b>{c['symbol'].upper()}</b>  {fmt_price(c['current_price'])} {cur}  "
                f"{arrow(chg)} {chg:+.1f}%"
            )
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception as e:  # noqa: BLE001
        log.exception("movers error")
        await update.message.reply_text(f"⚠️ Error: {e}")


async def gainers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _movers(update, True)


async def losers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _movers(update, False)


async def fear_greed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get("https://api.alternative.me/fng/", params={"limit": 1})
            r.raise_for_status()
            d = r.json()["data"][0]
        val = int(d["value"])
        label = d["value_classification"]
        emo = "😨" if val <= 25 else "😟" if val <= 45 else "😐" if val <= 55 else "🙂" if val <= 75 else "🤑"
        filled = round(val / 10)
        bar = "█" * filled + "░" * (10 - filled)
        await update.message.reply_text(
            f"<b>{emo} Crypto Fear &amp; Greed Index</b>\n\n"
            f"<b>{val}/100</b> — {label}\n<code>{bar}</code>",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:  # noqa: BLE001
        log.exception("fng error")
        await update.message.reply_text(f"⚠️ Error: {e}")


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /info <coin>   e.g. /info eth")
        return
    resolved = await resolve_coin(context.args[0])
    if not resolved:
        await update.message.reply_text("❓ Coin not found.")
        return
    coin_id, sym = resolved
    try:
        d = await cg_get(
            f"/coins/{coin_id}",
            {
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false",
                "sparkline": "false",
            },
        )
        md = d.get("market_data", {})
        cur = VS.upper()
        price_now = (md.get("current_price") or {}).get(VS)
        ath = (md.get("ath") or {}).get(VS)
        atl = (md.get("atl") or {}).get(VS)
        ath_chg = (md.get("ath_change_percentage") or {}).get(VS) or 0
        rank = d.get("market_cap_rank")
        home_links = d.get("links", {}).get("homepage", [])
        home = f"\n🔗 {home_links[0]}" if home_links and home_links[0] else ""
        text = (
            f"<b>{d.get('name', '')} ({sym})</b>  ·  rank #{rank or '—'}\n\n"
            f"💵 Price: <b>{fmt_price(price_now)} {cur}</b>\n"
            f"🔝 ATH: {fmt_price(ath)} {cur}  ({ath_chg:+.0f}% off ATH)\n"
            f"🔻 ATL: {fmt_price(atl)} {cur}\n"
            f"🪙 Circulating: {fmt_big(md.get('circulating_supply'))}\n"
            f"📦 Total: {fmt_big(md.get('total_supply'))}  ·  "
            f"Max: {fmt_big(md.get('max_supply')) if md.get('max_supply') else '∞'}"
            f"{home}"
        )
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
        )
    except Exception as e:  # noqa: BLE001
        log.exception("info error")
        await update.message.reply_text(f"⚠️ Error: {e}")


# ----------------------------------------------------------------------------
# Watchlist (JSON-persisted, per chat)
# ----------------------------------------------------------------------------
WATCHLIST_FILE = ALERTS_FILE.with_name("watchlist.json")


def load_watch() -> dict:
    if WATCHLIST_FILE.exists():
        try:
            return json.loads(WATCHLIST_FILE.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_watch(data: dict) -> None:
    WATCHLIST_FILE.write_text(json.dumps(data, indent=2))


async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /watch <coin>   e.g. /watch sol")
        return
    resolved = await resolve_coin(context.args[0])
    if not resolved:
        await update.message.reply_text("❓ Coin not found.")
        return
    coin_id, sym = resolved
    data = load_watch()
    key = str(update.effective_chat.id)
    lst = data.get(key, [])
    if any(x["id"] == coin_id for x in lst):
        await update.message.reply_text(f"{sym} is already on your watchlist.")
        return
    if len(lst) >= 20:
        await update.message.reply_text("Watchlist is full (max 20). Remove one with /unwatch.")
        return
    lst.append({"id": coin_id, "sym": sym})
    data[key] = lst
    save_watch(data)
    await update.message.reply_text(f"⭐ Added <b>{sym}</b> to your watchlist.", parse_mode=ParseMode.HTML)


async def unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /unwatch <coin>")
        return
    resolved = await resolve_coin(context.args[0])
    if not resolved:
        await update.message.reply_text("❓ Coin not found.")
        return
    coin_id, sym = resolved
    data = load_watch()
    key = str(update.effective_chat.id)
    lst = data.get(key, [])
    new = [x for x in lst if x["id"] != coin_id]
    if len(new) == len(lst):
        await update.message.reply_text(f"{sym} isn't on your watchlist.")
        return
    data[key] = new
    save_watch(data)
    await update.message.reply_text(f"🗑️ Removed {sym} from your watchlist.")


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    key = str(update.effective_chat.id)
    lst = load_watch().get(key, [])
    if not lst:
        await update.message.reply_text("Your watchlist is empty. Add one: /watch btc")
        return
    try:
        data = await cg_get(
            "/simple/price",
            {"ids": ",".join(x["id"] for x in lst), "vs_currencies": VS, "include_24hr_change": "true"},
        )
        cur = VS.upper()
        lines = ["<b>⭐ Your watchlist</b>\n"]
        for x in lst:
            d = data.get(x["id"], {})
            p = d.get(VS)
            chg = d.get(f"{VS}_24h_change")
            chg_s = f"{arrow(chg)} {chg:+.1f}%" if chg is not None else ""
            lines.append(f"<b>{x['sym']}</b>  {fmt_price(p)} {cur}  {chg_s}")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception as e:  # noqa: BLE001
        log.exception("watchlist error")
        await update.message.reply_text(f"⚠️ Error: {e}")


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
async def launch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>🚀 Launch a token on Solana</b>\n\n"
        "<b>No-code launchpads</b> (easiest):\n"
        "• <b>pump.fun</b> — instant bonding-curve launch\n"
        "• <b>bonk.fun / LetsBonk</b> — Bonk launchpad\n\n"
        "<b>Open-source SDKs</b> (for devs):\n"
        "• pumpdotfun-sdk · pump-fun-token-launcher (TypeScript)\n"
        "• pumpfun-rs (Rust)\n\n"
        "⚠️ Launching deploys on-chain and costs real SOL + needs a wallet. "
        "Info &amp; education only — DYOR, not financial advice.\n\n"
        "🦞 $CLAWX launches June 6, 5:00 PM UTC."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def helius_get_asset(mint: str) -> dict | None:
    """Fetch a Solana token's on-chain metadata via Helius DAS getAsset."""
    if not HELIUS_API_KEY:
        return None
    url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    payload = {"jsonrpc": "2.0", "id": "1", "method": "getAsset", "params": {"id": mint}}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json().get("result")


async def sol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not HELIUS_API_KEY:
        await update.message.reply_text(
            "⚠️ On-chain lookups need a Helius key. Add HELIUS_API_KEY to .env "
            "(free at helius.dev), then restart the bot."
        )
        return
    if not context.args:
        await update.message.reply_text("Usage: /sol <mint address>   (Solana token mint)")
        return
    mint = context.args[0]
    try:
        res = await helius_get_asset(mint)
        if not res:
            await update.message.reply_text("❓ Token not found on Solana.")
            return
        meta = (res.get("content") or {}).get("metadata", {}) or {}
        name = meta.get("name", "—")
        symbol = meta.get("symbol", "")
        ti = res.get("token_info") or {}
        decimals = ti.get("decimals", 0) or 0
        supply = ti.get("supply")
        if supply is not None and decimals:
            supply = supply / (10 ** decimals)
        price = (ti.get("price_info") or {}).get("price_per_token")

        head = f"<b>{name}{(' (' + symbol + ')') if symbol else ''}</b>"
        lines = [head, f"<code>{mint}</code>", ""]
        if price is not None:
            lines.append(f"💵 Price: {fmt_price(price)} USD")
        if supply is not None:
            lines.append(f"🪙 Supply: {fmt_big(supply)}")
        lines.append("\n<i>Solana on-chain data · Helius</i>")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception as e:  # noqa: BLE001
        log.exception("sol error")
        await update.message.reply_text(f"⚠️ Error: {e}")


async def tokenomics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>🦞 $CLAWX — Tokenomics</b>\n\n"
        "<b>Ticker:</b> $CLAWX\n"
        "<b>Network:</b> Solana\n"
        "<b>Total supply:</b> 1,000,000,000\n"
        "<b>Buy / Sell tax:</b> 0% / 0%\n"
        "<b>Contract:</b> Coming soon (TBA)\n"
        "<b>Launch:</b> June 6, 5:00 PM UTC\n\n"
        "<b>📊 Distribution</b>\n"
        "• Liquidity &amp; exchanges — 40%\n"
        "• Community &amp; airdrops — 25%\n"
        "• Team (vested) — 15%\n"
        "• Treasury — 10%\n"
        "• Marketing — 10%\n\n"
        "<b>⚡ Utility</b>\n"
        "• Premium signals, alerts &amp; higher limits\n"
        "• Governance voting on the roadmap\n"
        "• Revenue share &amp; staking rewards\n"
        "• Fee discounts across CLAWCLAWX\n\n"
        "🔗 clawclawxbot.xyz"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN is not set. Create a bot with @BotFather, then:\n"
            "  export BOT_TOKEN='123456:ABC...'  (or put it in a .env file)"
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler(["p", "price"], price))
    app.add_handler(CommandHandler("chart", chart))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("global", global_cmd))
    app.add_handler(CommandHandler(["tokenomics", "tokenomic", "token"], tokenomics))
    app.add_handler(CommandHandler("launch", launch))
    app.add_handler(CommandHandler("sol", sol))
    app.add_handler(CommandHandler("convert", convert))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("trending", trending))
    app.add_handler(CommandHandler("gainers", gainers))
    app.add_handler(CommandHandler("losers", losers))
    app.add_handler(CommandHandler(["feargreed", "fng"], fear_greed))
    app.add_handler(CommandHandler("watch", watch))
    app.add_handler(CommandHandler("unwatch", unwatch))
    app.add_handler(CommandHandler("watchlist", watchlist))
    app.add_handler(CommandHandler("alert", alert))
    app.add_handler(CommandHandler("alerts", list_alerts))
    app.add_handler(CommandHandler("delalert", del_alert))

    # check alerts every 60s (JobQueue requires the [job-queue] extra)
    if app.job_queue:
        app.job_queue.run_repeating(check_alerts, interval=60, first=15)

    log.info("CLAWCLAWX bot starting (polling)…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

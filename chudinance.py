import os
import asyncio
import logging
from typing import Optional, Tuple

import aiohttp
import discord

# ---------- Config ----------
TOKEN = os.environ.get("TOKEN")
GUILD_ID_RAW = os.environ.get("GUILD_ID")  # optional; if unset, updates all guilds
INTERVAL_SECONDS = int(os.environ.get("INTERVAL_SECONDS", "120"))  # update cadence (sec)

if not TOKEN:
    raise SystemExit("Missing env var TOKEN")

GUILD_ID: Optional[int] = None
if GUILD_ID_RAW:
    cleaned = GUILD_ID_RAW.strip()
    if cleaned.isdigit():
        GUILD_ID = int(cleaned)
    else:
        print("Warning: GUILD_ID is not a pure integer; ignoring and updating all guilds.")

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("btcd-bot")

# ---------- Discord client ----------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True  # enable "Server Members Intent" in Dev Portal
client = discord.Client(intents=intents)

_http_session: Optional[aiohttp.ClientSession] = None
update_task: Optional[asyncio.Task] = None


# ---------- Data fetch ----------
async def fetch_btcd_and_change(session: aiohttp.ClientSession) -> Tuple[float, float]:
    """
    Compute BTC Dominance (BTC.D) and its 24h change in percentage points using CoinGecko.
    - BTC.D = (BTC market cap / Total market cap) * 100
    - To estimate 24h change: use BTC market cap 24h % change (b) and total market cap 24h % change (t).
      Let D1 = current dominance. Yesterday's dominance D0 = D1 / ((1+b)/(1+t)).
      24h change (percentage points) = D1 - D0.
    Returns: (btcd_now_percent, btcd_change_pp)
    """
    timeout = aiohttp.ClientTimeout(total=12)

    # 1) BTC market cap + its 24h market cap % change
    url_btc = f"{COINGECKO_BASE}/coins/markets?vs_currency=usd&ids=bitcoin"
    async with session.get(url_btc, timeout=timeout) as r:
        if r.status != 200:
            txt = (await r.text())[:200]
            raise RuntimeError(f"BTC markets HTTP {r.status} body={txt!r}")
        rows = await r.json()
        if not isinstance(rows, list) or not rows:
            raise RuntimeError("BTC markets: empty list")
        btc_row = rows[0]
        btc_mcap = float(btc_row["market_cap"])
        btc_mcap_chg_pct_24h = float(btc_row.get("market_cap_change_percentage_24h", 0.0))  # %
        b = btc_mcap_chg_pct_24h / 100.0

    # 2) Global total market cap + its 24h % change
    url_global = f"{COINGECKO_BASE}/global"
    async with session.get(url_global, timeout=timeout) as r:
        if r.status != 200:
            txt = (await r.text())[:200]
            raise RuntimeError(f"Global HTTP {r.status} body={txt!r}")
        j = await r.json()
        data = j.get("data", {})
        total_caps = data.get("total_market_cap", {})
        total_mcap_usd = float(total_caps.get("usd", 0.0))
        if total_mcap_usd <= 0:
            raise RuntimeError("Global total_market_cap.usd missing/zero")
        total_mcap_chg_pct_24h = float(data.get("market_cap_change_percentage_24h_usd", 0.0))  # %
        t = total_mcap_chg_pct_24h / 100.0

    # Current dominance
    D1 = (btc_mcap / total_mcap_usd) * 100.0

    # Back out yesterday's dominance D0 via relative changes
    # D1 = D0 * (1+b)/(1+t)  =>  D0 = D1 / ((1+b)/(1+t))
    denom = (1.0 + b) / (1.0 + t) if (1.0 + t) != 0 else 1.0
    D0 = D1 / denom if denom != 0 else D1

    change_pp = D1 - D0  # percentage points over 24h

    return D1, change_pp


async def get_self_member(guild: discord.Guild) -> Optional[discord.Member]:
    me = getattr(guild, "me", None)
    if isinstance(me, discord.Member):
        return me
    m = guild.get_member(client.user.id)
    if isinstance(m, discord.Member):
        return m
    try:
        return await guild.fetch_member(client.user.id)
    except discord.HTTPException as e:
        log.warning(f"[{guild.name}] fetch_member failed: {e}")
        return None


async def update_guild(guild: discord.Guild):
    me = await get_self_member(guild)
    if not me:
        log.info(f"[{guild.name}] Could not obtain bot Member; skipping.")
        return

    perms = me.guild_permissions
    can_edit_nick = perms.change_nickname or perms.manage_nicknames

    try:
        assert _http_session is not None, "HTTP session not initialized"
        btcd, change_pp = await fetch_btcd_and_change(_http_session)
    except Exception as e:
        log.error(f"[{guild.name}] BTC.D fetch failed: {e}")
        try:
            await client.change_presence(activity=discord.Game(name="BTC.D error"))
        except Exception:
            pass
        return

    emoji = "🟢" if change_pp >= 0 else "🔴"

    # Nickname: "52.34% 🟢/🔴" (no coin name)
    nickname = f"{btcd:.2f}% {emoji}"
    if len(nickname) > 32:
        nickname = nickname[:32]

    if can_edit_nick:
        try:
            await me.edit(nick=nickname, reason="Auto BTC Dominance update (CoinGecko)")
        except discord.Forbidden:
            log.info(f"[{guild.name}] Forbidden by role hierarchy; cannot change nickname.")
        except discord.HTTPException as e:
            log.warning(f"[{guild.name}] HTTP error updating nick: {e}")
    else:
        log.info(f"[{guild.name}] Missing permission: Change Nickname/Manage Nicknames.")

    # Presence under the name: "BTC.D 24h +0.18 pp"
    try:
        await client.change_presence(activity=discord.Game(name=f"BTC.D 24h {change_pp:+.2f} pp"))
    except Exception as e:
        log.debug(f"[{guild.name}] Could not set presence: {e}")

    log.info(f"[{guild.name}] BTC.D → Nick: {nickname if can_edit_nick else '(unchanged)'} | 24h {change_pp:+.2f} pp")


# ---------- Loop ----------
async def updater_loop():
    await client.wait_until_ready()
    log.info(f"Updater loop started. Target: {'all guilds' if not GUILD_ID else GUILD_ID}")

    # one shared HTTP session
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()

    while not client.is_closed():
        try:
            if GUILD_ID:
                g = client.get_guild(GUILD_ID)
                targets = [g] if g else []
                if not g:
                    log.info("Configured GUILD_ID not found yet. Is the bot in that server?")
            else:
                targets = list(client.guilds)

            if not targets:
                log.info("No guilds to update yet.")
            else:
                await asyncio.gather(*(update_guild(g) for g in targets))

        except Exception as e:
            log.error(f"Updater loop error: {e}")

        await asyncio.sleep(INTERVAL_SECONDS)


@client.event
async def on_ready():
    global update_task
    log.info(f"Logged in as {client.user} in {len(client.guilds)} guild(s).")
    if update_task is None or update_task.done():
        update_task = asyncio.create_task(updater_loop())


if __name__ == "__main__":
    client.run(TOKEN)

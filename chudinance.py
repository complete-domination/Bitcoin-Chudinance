import os
import asyncio
import aiohttp
import discord

# ==============================
# CONFIGURATION
# ==============================
TOKEN = os.environ.get("TOKEN")  # Your Discord bot token
UPDATE_INTERVAL = 300  # Update every 5 minutes (in seconds)
COINGECKO_URL = "https://api.coingecko.com/api/v3/global"

# ==============================
# DISCORD CLIENT SETUP
# ==============================
intents = discord.Intents.none()
client = discord.Client(intents=intents)

# Cache last known dominance value to avoid nulls on temporary API failure
last_btc_dominance = None


# ==============================
# FETCH FUNCTION
# ==============================
async def fetch_btc_dominance():
    """Fetch Bitcoin dominance from CoinGecko's global market data."""
    async with aiohttp.ClientSession() as session:
        async with session.get(COINGECKO_URL) as response:
            if response.status != 200:
                raise Exception(f"Bad response from API (HTTP {response.status})")
            data = await response.json()
            btc_d = data.get("data", {}).get("market_cap_percentage", {}).get("btc")
            if btc_d is None:
                raise Exception("BTC dominance not found in API response.")
            return btc_d


# ==============================
# PRESENCE UPDATE LOOP
# ==============================
async def update_btc_dominance_loop():
    """Continuously update the bot's presence and nickname with BTC dominance."""
    global last_btc_dominance

    await client.wait_until_ready()
    print(f"✅ Logged in as {client.user}")

    while not client.is_closed():
        try:
            btc_d = await fetch_btc_dominance()
            last_btc_dominance = btc_d
            formatted = f"{btc_d:.2f}%"

            # Update Discord presence
            await client.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"BTC Dominance: {formatted}"
                ),
                status=discord.Status.online
            )

            # Update nickname across all guilds
            for guild in client.guilds:
                try:
                    me = guild.me
                    await me.edit(nick=f"BTC.D {formatted}")
                except discord.Forbidden:
                    print(f"⚠️ Missing permission to change nickname in {guild.name}")

            print(f"✅ Updated BTC Dominance → {formatted}")

        except Exception as e:
            print(f"⚠️ Error: {e}")

            # If API fails, keep showing last known data
            if last_btc_dominance is not None:
                formatted = f"{last_btc_dominance:.2f}% ⚠️"
                await client.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.watching,
                        name=f"BTC.D (cached)"
                    ),
                    status=discord.Status.online
                )
                for guild in client.guilds:
                    try:
                        me = guild.me
                        await me.edit(nick=f"BTC.D {formatted}")
                    except discord.Forbidden:
                        pass
            else:
                await client.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.watching,
                        name="BTC.D unavailable"
                    ),
                    status=discord.Status.idle
                )

        await asyncio.sleep(UPDATE_INTERVAL)


# ==============================
# EVENT HOOKS
# ==============================
@client.event
async def on_ready():
    """Event called when the bot connects."""
    print("🤖 Bot is ready.")
    client.loop.create_task(update_btc_dominance_loop())


# ==============================
# RUN BOT
# ==============================
if not TOKEN:
    raise SystemExit("❌ ERROR: Discord TOKEN not found in environment variables.")
else:
    client.run(TOKEN)

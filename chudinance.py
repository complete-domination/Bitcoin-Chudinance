import os
import asyncio
import aiohttp
import discord

TOKEN = os.environ["TOKEN"]
UPDATE_INTERVAL = 300  # seconds (5 minutes)
API_URL = "https://api.coingecko.com/api/v3/global"

intents = discord.Intents.none()
client = discord.Client(intents=intents)

last_value = None

async def get_btc_dominance():
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL) as resp:
            if resp.status == 429:
                raise Exception("Rate limited (HTTP 429)")
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            data = await resp.json()
            btc = data.get("data", {}).get("market_cap_percentage", {}).get("btc")
            if btc is None:
                raise Exception("BTC dominance missing in response")
            return btc

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    await update_presence_loop()

async def update_presence_loop():
    global last_value
    await client.wait_until_ready()

    while not client.is_closed():
        try:
            btc_dom = await get_btc_dominance()
            last_value = btc_dom  # store latest success
            formatted = f"{btc_dom:.2f}%"

            await client.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"BTC Dominance: {formatted}"
                ),
                status=discord.Status.online
            )

            for guild in client.guilds:
                me = guild.me
                await me.edit(nick=f"{formatted}")

            print(f"✅ Updated BTC Dominance: {formatted}")

        except Exception as e:
            print(f"⚠️ Error fetching BTC dominance: {e}")
            if last_value:
                # Show last known value, mark as stale
                formatted = f"{last_value:.2f}% ⚠️"
                await client.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.watching,
                        name=f"BTC.D (cached)"
                    ),
                    status=discord.Status.online
                )
                for guild in client.guilds:
                    me = guild.me
                    await me.edit(nick=formatted)
            else:
                # No cached data at all
                await client.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.watching,
                        name="BTC.D unavailable"
                    ),
                    status=discord.Status.idle
                )

        await asyncio.sleep(UPDATE_INTERVAL)

client.run(TOKEN)

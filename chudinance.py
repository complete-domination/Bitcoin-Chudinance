import os
import asyncio
import aiohttp
import discord

TOKEN = os.environ["TOKEN"]
UPDATE_INTERVAL = 300  # 5 minutes

intents = discord.Intents.none()
client = discord.Client(intents=intents)

API_URL = "https://api.coingecko.com/api/v3/global"

async def get_btc_dominance():
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            data = await resp.json()
            return data["data"]["market_cap_percentage"]["btc"]

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    await update_presence_loop()

async def update_presence_loop():
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            btc_dom = await get_btc_dominance()
            formatted = f"{btc_dom:.2f}%"
            await client.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"BTC Dominance: {formatted}"
                ),
                status=discord.Status.online
            )

            # Optional: change nickname to percentage
            for guild in client.guilds:
                me = guild.me
                await me.edit(nick=f"BTC.D {formatted}")
            
            print(f"Updated BTC.D → {formatted}")
        except Exception as e:
            print("⚠️ Error fetching BTC dominance:", e)
            await client.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="BTC.D unavailable"
                ),
                status=discord.Status.idle
            )
        await asyncio.sleep(UPDATE_INTERVAL)

client.run(TOKEN)

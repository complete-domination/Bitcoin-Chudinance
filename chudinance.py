import os
import asyncio
import aiohttp
import discord

# ---------- CONFIG ----------
TOKEN = os.environ["TOKEN"]
UPDATE_INTERVAL = 300  # seconds (5 minutes)
API_URL = "https://api.coingecko.com/api/v3/global"

# ---------- DISCORD CLIENT ----------
intents = discord.Intents.none()
client = discord.Client(intents=intents)

# ---------- FETCH BTC DOMINANCE ----------
async def get_btc_dominance():
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            data = await resp.json()
            return data["data"]["market_cap_percentage"]["btc"]

# ---------- EVENT: ON READY ----------
@client.event
async def on_ready():
    print(f"🤖 Bot is ready.")
    print(f"✅ Logged in as {client.user}")
    asyncio.create_task(update_btc_dominance_loop())

# ---------- LOOP: UPDATE PRESENCE ----------
async def update_btc_dominance_loop():
    await client.wait_until_ready()
    last_value = None

    while not client.is_closed():
        try:
            btc_dom = await get_btc_dominance()
            formatted = f"{btc_dom:.2f}%"

            # --- Determine trend direction ---
            if last_value is not None:
                if btc_dom > last_value:
                    arrow = "↑"
                elif btc_dom < last_value:
                    arrow = "↓"
                else:
                    arrow = "→"
            else:
                arrow = "•"

            last_value = btc_dom

            # --- Update presence ---
            await client.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"BTC Dominance: {formatted} {arrow}"
                ),
                status=discord.Status.online
            )

            # --- Try updating nickname in each guild ---
            for guild in client.guilds:
                me = guild.me
                if me and guild.me.guild_permissions.change_nickname:
                    try:
                        await me.edit(nick=f"BTC.D {formatted} {arrow}")
                    except Exception as e:
                        print(f"⚠️ Could not change nickname in {guild.name}: {e}")
                else:
                    print(f"ℹ️ Skipping nickname change in {guild.name} (no permission or unavailable).")

            print(f"✅ Updated BTC Dominance → {formatted} {arrow}")

        except Exception as e:
            print(f"⚠️ Error: {e}")
            await client.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="BTC.D unavailable"
                ),
                status=discord.Status.idle
            )

        await asyncio.sleep(UPDATE_INTERVAL)

# ---------- RUN BOT ----------
client.run(TOKEN)

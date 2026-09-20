"""Find Discord channel ID from guilds the bot is in"""
import os, requests
from dotenv import load_dotenv
load_dotenv(override=True)

token = os.getenv("DISCORD_BOT_TOKEN", "")
headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}

# Get bot's guilds
r = requests.get("https://discord.com/api/v10/users/@me/guilds", headers=headers, timeout=10)
print(f"Guilds: HTTP {r.status_code}")
if r.status_code == 200:
    guilds = r.json()
    print(f"Bot is in {len(guilds)} guild(s)")
    for g in guilds:
        guild_id = g.get("id")
        guild_name = g.get("name")
        print(f"\nGuild: {guild_name} (id={guild_id})")
        # Get channels
        rc = requests.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers, timeout=10)
        if rc.status_code == 200:
            channels = rc.json()
            for ch in channels:
                if ch.get("type") == 0:  # 0 = text channel
                    print(f"  TEXT #{ch['name']} id={ch['id']}")
        else:
            print(f"  Channels: {rc.status_code} {rc.text[:100]}")
else:
    print(f"Error: {r.text[:300]}")

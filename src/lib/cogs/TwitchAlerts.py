from dotenv import find_dotenv, load_dotenv
from discord.ext import commands, tasks
from discord.ui import Button, View
from src.lib.bot import config
import logging
import requests
import discord
import os

env_file = find_dotenv(".env.local")
load_dotenv(env_file)


class TwitchAlerts(commands.Cog):

    with open(os.environ["TWITCH_CLIENT_ID"], "r", encoding="utf-8") as f:
        client_id = f.readline().strip()

    with open(os.environ["TWITCH_CLIENT_SECRET"], "r", encoding="utf-8") as f:
        client_secret = f.readline().strip()

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.bearer_token = None
        self.livestreams = set()

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")
        self.check_live.start()
    
    async def cog_unload(self):
        self.check_live.stop()

    @tasks.loop(minutes=5)
    async def check_live(self):
        await self.bot.wait_until_ready()
        if self.bearer_token == None or (requests.get("https://id.twitch.tv/oauth2/validate", headers={"Authorization": f"OAuth {self.bearer_token}"})).status_code != 200:
            self.bearer_token = (requests.post("https://id.twitch.tv/oauth2/token", params={"client_id": self.client_id, "client_secret": self.client_secret, "grant_type": "client_credentials"})).json()["access_token"]
        if len(streams := (requests.get("https://api.twitch.tv/helix/streams", params={"user_login": config["TWITCH_ALERTS"]["TRIGGER"]}, headers={"Authorization": f"Bearer {self.bearer_token}", "Client-Id": self.client_id})).json()["data"]) == 0:
            if (user_login := config["TWITCH_ALERTS"]["TRIGGER"]) in self.livestreams:
                self.livestreams.remove(user_login)
            return
        stream = streams[0]
        if ((user_login := stream["user_login"]) in self.livestreams):
            return
        self.livestreams.add(user_login)
        embed = discord.Embed(title=stream["title"], description=f"**{stream['user_name']}** is now live streaming {stream['game_name']} on Twitch!", colour=0xDC3145, timestamp=discord.utils.utcnow())
        embed.set_author(name="ScuffBot Twitch Alerts", icon_url=self.bot.user.display_avatar.url)
        embed.set_image(url=stream["thumbnail_url"].replace("{width}", "1280").replace("{height}", "720"))
        view = View()
        view.add_item(
            Button(
                label="Watch on Twitch",
                style=discord.ButtonStyle.link,
                url=f"https://twitch.tv/{stream['user_login']}",
            )
        )
        channel = await self.bot.fetch_channel(int(config["TWITCH_ALERTS"]["CHANNEL"]))
        await channel.send("@everyone", embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(TwitchAlerts(bot))

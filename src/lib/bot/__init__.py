import json
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv, find_dotenv
import logging.config
import logging
import discord
import yaml
import sys
import os
from ..db import DB as SCUFF_DB

env_file = find_dotenv(".env.local")
load_dotenv(env_file)

with open(os.environ["CONFIG_FILE"], "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

DB = SCUFF_DB()


class SCUFFBOT(commands.Bot):

    def __init__(self, is_dev):
        super().__init__(command_prefix="!",
                         owner_id=169402073404669952, intents=discord.Intents.all())
        self.is_dev = is_dev
        self.mode = "DEVELOPMENT" if is_dev else "PRODUCTION"

    async def setup_hook(self):
        self.setup_logger()
        self.DB = DB
        try:
            self.DB.connect()
        except Exception as e:
            self.logger.error(f"Failed to connect to the database: {e}")
            sys.exit(1)
        await self.load_cog_manager()

    def setup_logger(self):
        with open("./logging.json") as f:
            logging.config.dictConfig(json.loads(f.read()))
        self.logger = logging.getLogger(__name__)
        for handler in logging.getLogger().handlers:
            if handler.name == "file" and os.path.isfile('logs/latest.log'):
                handler.doRollover()

    async def load_cog_manager(self):
        await self.load_extension("src.lib.cogs.Cogs")

    def run(self, bot_token: str):
        super().run(bot_token, log_handler=None)

    def create_embed(self, title, description, colour):
        embed = discord.Embed(title=None, description=description,
                              colour=colour if colour else 0xDC3145, timestamp=discord.utils.utcnow())
        embed.set_author(name=title if title else None,
                         icon_url=self.avatar_url)
        return embed

    #  Doesn't work, need to look into
    @staticmethod
    def has_permissions(**perms):
        original = app_commands.checks.has_permissions(**perms)

        async def extended_check(interaction):
            if interaction.guild is None:
                return False
            return interaction.user.id in config["DEVELOPERS"] or (interaction.user.id == 169402073404669952) or await original.predicate(interaction)
        return app_commands.check(extended_check)

    @staticmethod
    def is_developer(interaction: discord.Interaction):
        return interaction.user.id in config["DEVELOPERS"]

    async def on_ready(self):
        self.appinfo = await super().application_info()
        self.avatar_url = self.appinfo.icon.url if self.appinfo.icon is not None else None
        self.logger.info(
            f"Connected on {self.user.name} | d.py v{str(discord.__version__)}"
        )

    async def on_interaction(self, interaction):
        self.logger.info(
            f"[COMMAND] [{interaction.guild} // {interaction.guild.id}] {interaction.user} ({interaction.user.id}) used command {interaction.command.name}")

    async def on_message(self, message):
        await self.wait_until_ready()
        if (isinstance(message.channel, discord.DMChannel) and message.author.id == self.owner_id):
            message_components = message.content.lower().split(" ")
            match message_components[0]:
                case "sync":
                    if len(message_components) == 2:
                        result = await self.tree.sync(guild=discord.Object(id=int(message_components[1])))
                    else:
                        result = await self.tree.sync()
                    await message.channel.send(f"Synced {[command.name for command in result]}")

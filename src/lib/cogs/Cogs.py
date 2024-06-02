from discord.ext import commands
from discord import app_commands
from src.lib.bot import config
import discord
import logging

from glob import glob
import os
import traceback


class Cogs(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.disabled_cogs = []
        self.unloaded_cogs = []
        self.loaded_cogs = []
        self.logger = logging.getLogger(__name__)

        if self.bot.is_dev:
            for cog in [path.split("\\")[-1][:-3] if os.name == "nt" else path.split("\\")[-1][:-3].split("/")[-1] for path in glob("./src/lib/cogs/*.py")]:
                if cog not in ["Cogs", "ErrorHandler"]:
                    self.disabled_cogs.append(cog)
        else:
            self.disabled_cogs.append("Template")

    async def fetch_cogs(self):
        for cog in [path.split("\\")[-1][:-3] if os.name == "nt" else path.split("\\")[-1][:-3].split("/")[-1] for path in glob("./src/lib/cogs/*.py")]:
            if cog != "Cogs" and cog not in self.disabled_cogs:
                self.unloaded_cogs.append(cog)

    async def load_cog(self, cog):
        try:
            await self.bot.load_extension(f"src.lib.cogs.{cog}")
        except Exception as e:
            self.logger.error(f"[COG] {cog} failed to load. {e}")
            traceback.print_exc()
            raise e

    async def unload_cog(self, cog):
        try:
            await self.bot.unload_extension(f"src.lib.cogs.{cog}")
        except Exception as e:
            self.logger.error(f"[COG] {cog} failed to unload. {e}")
            traceback.print_exc()
            raise e

    async def reload_cog(self, cog):
        try:
            await self.bot.unload_extension(f"src.lib.cogs.{cog}")
            await self.bot.load_extension(f"src.lib.cogs.{cog}")
        except Exception as e:
            self.logger.error(f"[COG] {cog} failed to reload. {e}")
            traceback.print_exc()
            raise e

    async def load_cogs(self):
        if not self.unloaded_cogs:
            await self.fetch_cogs()
        while self.unloaded_cogs:
            cog = self.unloaded_cogs.pop(0)
            if cog in config["DEPENDENCIES"]:
                if all([dependency in self.loaded_cogs for dependency in config["DEPENDENCIES"][cog]]):
                    await self.load_cog(cog)
                else:
                    self.logger.warning(f"[COG] Deferring {cog}")
                    self.unloaded_cogs.append(cog)
            else:
                await self.load_cog(cog)

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")

    CogGroup = app_commands.Group(name="cog", description="Manages SCUFFBOT cogs.", guild_ids=[
                                  1165195575013163038, 422983658257907732])

    @CogGroup.command(name="list", description="Lists all cog statuses.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def list(self, interaction: discord.Interaction):
        embed = self.bot.create_embed("SCUFFBOT SETUP", None, None)
        embed.add_field(name="Enabled", value=">>> {}".format(
            "\n".join([x for x in self.bot.cogs])), inline=True)
        if bool(self.unloaded_cogs + self.disabled_cogs):
            embed.add_field(name="Disabled", value=">>> {}".format(
                "\n".join(self.unloaded_cogs + self.disabled_cogs)), inline=True)
        embed.add_field(
            name="\u200b", value=f"You may also use the following command to manage cogs.\n> `/cog [load|unload|reload] [*cogs]`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @CogGroup.command(name="unload", description="Unloads cogs.")
    @app_commands.describe(
        cogs="Space separated list of cogs to unload."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def unload(self, interaction: discord.Interaction, *, cogs: str):
        failed_cogs = []
        cogs = cogs.split(" ")
        for cog in cogs:
            try:
                await self.unload_cog(cog)
            except Exception as e:
                failed_cogs.append(cog)
        if failed_cogs:
            embed = self.bot.create_embed(
                "SCUFFBOT SETUP", f"Could not unload {', '.join([cog for cog in failed_cogs])}.", None)
        else:
            embed = self.bot.create_embed(
                "SCUFFBOT SETUP", f"Unloaded {', '.join([cog for cog in cogs])}.", None)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @CogGroup.command(name="load", description="Loads cogs.")
    @app_commands.describe(
        cogs="Space separated list of cogs to load."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def load(self, interaction: discord.Interaction, *, cogs: str):
        failed_cogs = []
        cogs = cogs.split(" ")
        for cog in cogs:
            try:
                await self.load_cog(cog)
            except Exception as e:
                failed_cogs.append(cog)
        if failed_cogs:
            embed = self.bot.create_embed(
                "SCUFFBOT SETUP", f"Could not load {', '.join([cog for cog in failed_cogs])}.", None)
        else:
            embed = self.bot.create_embed(
                "SCUFFBOT SETUP", f"Loaded {', '.join([cog for cog in cogs])}.", None)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @CogGroup.command(name="reload", description="Reloads cogs.")
    @app_commands.describe(
        cogs="Space separated list of cogs to reload."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def load(self, interaction: discord.Interaction, *, cogs: str):
        failed_cogs = []
        cogs = cogs.split(" ")
        for cog in cogs:
            try:
                await self.reload_cog(cog)
            except Exception as e:
                failed_cogs.append(cog)
        if failed_cogs:
            embed = self.bot.create_embed(
                "SCUFFBOT SETUP", f"Could not reload {', '.join([cog for cog in failed_cogs])}.", None)
        else:
            embed = self.bot.create_embed(
                "SCUFFBOT SETUP", f"Reloaded {', '.join([cog for cog in cogs])}.", None)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    cogs_class = Cogs(bot)
    await bot.add_cog(cogs_class)
    await cogs_class.load_cogs()

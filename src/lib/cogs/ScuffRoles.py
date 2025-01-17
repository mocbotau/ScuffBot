from discord.ext import commands
from discord import Object
from src.lib.bot import config
import discord
import logging
import re
import asyncio


class ScuffRoles(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    async def cog_load(self):
        asyncio.create_task(self.role_integrity_check())
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")

    async def role_integrity_check(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            for member in guild.members:
                await self.apply_title(member)

    async def apply_title(self, member):
        role_map = await self.fetch_scuff_titles(member.guild)
        correct_title = await self.get_correct_scuff_title(role_map, member)
        if not role_map:
            return
        if correct_title is None:
            high_difference = [
                role
                for role in member.roles
                if role in role_map.values()
            ]
        else:
            high_difference = [
                role
                for role in member.roles
                if role in role_map.values() and role != correct_title
            ]
        if high_difference:
            self.logger.info(
                f"Removing {[', '.join([role.name for role in high_difference])]} from {member}")
            await member.remove_roles(*[Object(id=int(role.id)) for role in high_difference], reason="Member scuff title doesn't reflect number of legacy roles")
        if correct_title and correct_title not in member.roles:
            self.logger.info(f"Adding {correct_title} to {member}")
            await member.add_roles(Object(id=int(correct_title.id)), reason="Applying correct scuff title")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles != after.roles:
            await self.apply_title(after)

    async def fetch_scuff_titles(self, guild):
        legacy_roles = dict()
        for role in guild.roles:
            if result := re.search(r"\[(\d+)\+ Legacy (?:Role|Roles)\]$", role.name):
                legacy_roles[result.group(1)] = role
        return {int(k): v for k, v in legacy_roles.items()}

    async def get_correct_scuff_title(self, role_map, member):
        closest_key = None
        legacy_roles = [
            role for role in member.roles if role.id in config["LEGACY_ROLES"]]
        for key in role_map:
            if int(key) <= len(legacy_roles) and (closest_key is None or abs(int(key) - len(legacy_roles)) < abs(closest_key - len(legacy_roles))):
                closest_key = int(key)
        return role_map.get(closest_key)


async def setup(bot):
    await bot.add_cog(ScuffRoles(bot))

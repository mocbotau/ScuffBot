from discord.ext import commands
import discord
import logging
from src.lib.bot import config
import asyncio


class NameRoles(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.roles = config["NAME_ROLES"]

    async def cog_load(self):
        asyncio.create_task(self.rank_integrity_check())
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles != after.roles:
            added_roles = [
                role for role in after.roles if role not in before.roles and role.id in self.roles]
            if added_roles:
                name = after.display_name.split(" | ")[0]
                rank = self.roles[added_roles[0].id]
                await after.edit(nick=f"{name} | {rank}")

    async def rank_integrity_check(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            for member in guild.members:
                old_name = member.display_name
                tokens = [token.strip()
                          for token in member.display_name.split("|")]
                role_intersection = [
                    role_id for role_id in config["NAME_ROLES"].keys() if role_id in [role.id for role in member.roles]]
                if not role_intersection or config["NAME_ROLES"][role_intersection[0]] == tokens[-1]:
                    continue
                for role_id in config["NAME_ROLES"]:
                    if role_id in role_intersection:
                        try:
                            await member.edit(nick=f"{tokens[0]} | {config['NAME_ROLES'][role_id]}", reason="Name does not match RL role.")
                        except Exception as e:
                            self.logger.info(
                                f"FAILED ({e}): {old_name} => {tokens[0]} | {config['NAME_ROLES'][role_id]}")
                        else:
                            self.logger.info(
                                f"{old_name} => {tokens[0]} | {config['NAME_ROLES'][role_id]}")
                        break


async def setup(bot):
    await bot.add_cog(NameRoles(bot))

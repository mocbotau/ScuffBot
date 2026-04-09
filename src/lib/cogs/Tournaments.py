from discord.ext import commands
from src.lib.bot import config
import logging
import re
import asyncio

class Tournaments(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.TRIGGER_CHANNELS = {obj["ID"]: obj["TYPE"] for obj in config["TOURNAMENT"]["TRIGGER_CHANNELS"]}
        self.channels = []
        self.logger = logging.getLogger(__name__)

    async def cog_load(self):
        asyncio.create_task(self.getLostChannels())
        for channelID in self.TRIGGER_CHANNELS:
            if (channel := self.bot.get_channel(channelID)) is not None:
                self.logger.info(f"[TOURNAMENTS] Listening for {channel}")
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel is not None and after.channel is not None and before.channel == after.channel:
            return
        if member.bot:
            return

        #Channel deletion
        if before.channel in self.channels and len(before.channel.members) == 0:
            await self.deleteTournamentChannel(before.channel)

        #Channel creation
        if after.channel.id in self.TRIGGER_CHANNELS:
            voice_channel = await self.createTournamentChannel(member, self.TRIGGER_CHANNELS[after.channel.id])
            await member.move_to(voice_channel)

            
    async def getLostChannels(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            for channel in guild.channels:
                if re.match("^(?:RL [0-9]'s|Extra Games) #[0-9]+$", channel.name):
                    if len(channel.members) == 0:
                        await self.deleteTournamentChannel(channel)
                    else:
                        self.logger.info(f"[COG] Discovered old channel. Re-listening for {channel.name}")
                        self.channels.append(channel)

    async def createTournamentChannel(self, member, limit):
        if limit == 0:
            channels = [channel for channel in self.channels if re.match(f"^Extra Games #[0-9]+$", channel.name)]
            channel_num = 1 if len(channels) == 0 else max([int(channel.name.split('#')[-1]) for channel in channels]) + 1
            voice_channel = await member.guild.create_voice_channel(name=f"Extra Games #{channel_num}", category=self.bot.get_channel({v: k for k, v in self.TRIGGER_CHANNELS.items()}[0]).category, reason=f"{member} created an extra games voice channel.")
        else:
            channels = [channel for channel in self.channels if re.match(f"^RL {limit}'s #[0-9]+$", channel.name)]
            channel_num = 1 if len(channels) == 0 else max([int(channel.name.split('#')[-1]) for channel in channels]) + 1
            voice_channel = await member.guild.create_voice_channel(name=f"RL {limit}'s #{channel_num}", user_limit=limit, category=self.bot.get_channel({v: k for k, v in self.TRIGGER_CHANNELS.items()}[limit]).category, reason=f"{member} created a {limit}'s voice channel.")
        self.channels.append(voice_channel)
        return voice_channel
            
    async def deleteTournamentChannel(self, channel):
        await channel.delete(reason=f"{channel.name} empty.")
        self.channels.remove(channel)

async def setup(bot):
    await bot.add_cog(Tournaments(bot))

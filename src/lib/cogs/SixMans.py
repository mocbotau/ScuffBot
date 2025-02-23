import asyncio
import re
from discord.ext import commands
from discord.ui import Button, View, Select
from discord import PermissionOverwrite, app_commands
from src.lib.db import DB
from src.lib.bot import config
from typing import Any, Callable, Union
import discord
import logging

from src.utils.SixMans import LOBBY_TIMEOUT, PARTY_SIZE, SixMansQueue, SixMansState, SixMansMatchType, SixMansParty


BAKKES_APP_ID = 356877880938070016
DISCORD_RPC_APP_ID = 562098317547405322
ROCKET_LEAGUE_APP_IDS = [BAKKES_APP_ID]
TIME_DIFFERENT_THRESHOLD = 10

class SixMansPrompt(View):
    def __init__(self, ctx, party_id: int):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.bot = ctx.bot
        self.message: Union[None | discord.Message] = None
        self.broken_out = False

        self.state = SixMansState.PRE_LOBBY
        self.game = SixMansMatchType.PRE_MATCH

        self.party = SixMansParty(self.bot, party_id)
        self.scores = {"1v1": (None, None), "2v2": (
            None, None), "3v3_A": (None, None), "3v3_B": (None, None), "3v3_C": (None, None)}
        self.last_remaining = None

        self.bot.add_listener(self.on_voice_state_update)
        self.bot.add_listener(self.on_presence_update)

    async def on_presence_update(self, _, member: discord.Member):
        if self.state == SixMansState.PLAYING and member.id in list(map(lambda p: p.id, self.party.get_players())) and set(map(lambda a: a.application_id, list(filter(lambda a: isinstance(a, discord.Activity), member.activities)))).intersection(set(ROCKET_LEAGUE_APP_IDS)):
            print(f"Playing {self.get_match_type()}", flush=True)
            all_players = DB.rows(
                "SELECT UserID, Type, Team, isOnesPlayer FROM SixManUsers WHERE PartyID = %s", self.party.party_id)

            match self.game:
                case SixMansMatchType.ONE_V_ONE:
                    players = [(int(row["UserID"]), int(row["Team"]))
                               for row in all_players if row["isOnesPlayer"] == 1]
                case SixMansMatchType.TWO_V_TWO:
                    players = [(int(row["UserID"]), int(row["Team"]))
                               for row in all_players if row["isOnesPlayer"] == 0]
                case SixMansMatchType.THREE_V_THREE_A | SixMansMatchType.THREE_V_THREE_B | SixMansMatchType.THREE_V_THREE_C:
                    players = [(int(row["UserID"]), int(row["Team"]))
                               for row in all_players]

            activity = next(filter(lambda a: isinstance(a, discord.Activity)
                                   and a.application_id in ROCKET_LEAGUE_APP_IDS, member.activities), None)
            if activity.application_id == BAKKES_APP_ID:
                if "Overtime" in activity.state:
                    match = re.search(
                        r"^Private (?P<own_score>[0-9]+):(?P<opposition_score>[0-9]+) \[Overtime (?P<minutes_elapsed>[0-9]+):(?P<seconds_elapsed>[0-9]+)\]$", activity.state)
                    remaining_seconds = 0
                else:
                    match = re.search(
                        r"^Private (?P<own_score>[0-9]+):(?P<opposition_score>[0-9]+) \[(?P<minutes_left>[0-9]+):(?P<seconds_left>[0-9]+) remaining\]$", activity.state)
                    remaining_seconds = (int(match.group("minutes_left"))
                                         * 60) + int(match.group("seconds_left"))
            else:
                if match := re.search(
                        r"^(?:Won|Lost) \((?P<own_score>[0-9]+) - (?P<opposition_score>[0-9]+)\)$", activity.state):
                    remaining_seconds = -1
                elif "(OT)" in activity.state:
                    match = re.search(
                        r"^(?:Winning|Tied|Losing) (?P<own_score>[0-9]+) - (?P<opposition_score>[0-9]+) \(OT\)$", activity.state)
                    remaining_seconds = 0
                else:
                    match = re.search(
                        r"^(?:Winning|Tied|Losing) (?P<own_score>[0-9]+) - (?P<opposition_score>[0-9]+)$", activity.state)
                    remaining_seconds = self.last_remaining


            if member.id in list(map(lambda p: p[0], players)):
                match_type = self.get_match_type()
                match_score = [None, None]
                team_index = next(filter(lambda p: p[0] == member.id, players))[
                    1] - 1
                match_score[team_index] = int(match.group("own_score"))
                match_score[1 -
                            team_index] = int(match.group("opposition_score"))
                if any(match_score) and self.scores[match_type] != tuple(match_score):
                    print(
                        f"Inferred score {tuple(match_score)} from {member}", flush=True)
                    self.scores[match_type] = tuple(match_score)
                    await self.update_view()
            if remaining_seconds == -1 or (self.last_remaining != None and remaining_seconds - self.last_remaining > TIME_DIFFERENT_THRESHOLD):
                match self.game:
                    case SixMansMatchType.ONE_V_ONE:
                        self.game = SixMansMatchType.TWO_V_TWO
                        self.state = SixMansState.PLAYING
                    case SixMansMatchType.TWO_V_TWO:
                        self.game = SixMansMatchType.THREE_V_THREE_A
                        self.state = SixMansState.PLAYING
                    case SixMansMatchType.THREE_V_THREE_A:
                        self.game = SixMansMatchType.THREE_V_THREE_B
                        self.state = SixMansState.PLAYING
                    case SixMansMatchType.THREE_V_THREE_B:
                        self.game = SixMansMatchType.THREE_V_THREE_C
                        self.state = SixMansState.PLAYING
                    case SixMansMatchType.THREE_V_THREE_C:
                        self.state = SixMansState.SCORE_VALIDATION
                self.last_remaining = None
                return await self.update_view()
            self.last_remaining = remaining_seconds

    async def on_voice_state_update(self, member, before, after):
        if before.channel is not None and after.channel is not None and before.channel == after.channel:
            return
        if member.bot:
            return

        # User joins channel
        if str(after.channel.id) == (await self.party.get_details())["VoiceChannelID"] and self.state == SixMansState.PRE_LOBBY and len(after.channel.members) == PARTY_SIZE:
            self.state = SixMansState.CHOOSE_CAPTAIN_ONE
            await self.update_view()

    async def interaction_check(self, interaction: discord.Interaction):
        if "custom_id" in interaction.data and interaction.data["custom_id"] == "team_comp":
            return True
        match self.state:
            case SixMansState.CHOOSE_CAPTAIN_ONE:
                if interaction.user and interaction.user.id != self.party.captain_one.id:
                    await interaction.response.send_message(f"Only {self.party.captain_one.mention} can do this.", ephemeral=True)
                return interaction.user and interaction.user.id == self.party.captain_one.id
            case SixMansState.CHOOSE_CAPTAIN_TWO:
                if interaction.user and interaction.user.id != self.party.captain_two.id:
                    await interaction.response.send_message(f"Only {self.party.captain_two.mention} can do this.", ephemeral=True)
                return interaction.user and interaction.user.id == self.party.captain_two.id
            case SixMansState.CHOOSE_1S_PLAYER:
                team = DB.field(
                    "SELECT Team FROM SixManUsers WHERE PartyID = %s AND UserID = %s", self.party.party_id, interaction.user.id)
                ones_player = DB.field(
                    "SELECT UserID FROM SixManUsers WHERE PartyID = %s AND Team = %s AND isOnesPlayer IS NOT NULL", self.party.party_id, team)
                if interaction.user and interaction.user.id not in [self.party.captain_one.id, self.party.captain_two.id]:
                    await interaction.response.send_message(f"Only {self.party.captain_one.mention} or {self.party.captain_two.mention} can do this.", ephemeral=True)
                elif ones_player != None:
                    await interaction.response.send_message("You have already nominated a 1s player for your team.", ephemeral=True)
                    return False
                return interaction.user and interaction.user.id in [self.party.captain_one.id, self.party.captain_two.id]
            case SixMansState.PLAYING | SixMansState.SCORE_VALIDATION | SixMansState.POST_MATCH:
                if interaction.user and interaction.user.id not in [self.party.captain_one.id, self.party.captain_two.id]:
                    await interaction.response.send_message(f"Only {self.party.captain_one.mention} or {self.party.captain_two.mention} can do this.", ephemeral=True)
                return interaction.user and interaction.user.id in [self.party.captain_one.id, self.party.captain_two.id]

    async def delete_lobby(self):
        lobby_details = await self.party.get_details()
        lobby_name = f"SixMans #{self.party.lobby_id}"

        guild = self.bot.get_channel(
            int(lobby_details["VoiceChannelID"])).guild
        await (guild.get_role(int(lobby_details["RoleID"]))).delete(reason=f"{lobby_name} finished/cancelled")
        await (self.bot.get_channel(int(lobby_details["VoiceChannelID"]))).delete(reason=f"{lobby_name} finished/cancelled")
        await (self.bot.get_channel(int(lobby_details["TextChannelID"]))).delete(reason=f"{lobby_name} finished/cancelled")

        if lobby_details["VoiceChannelA"]:
            await (self.bot.get_channel(int(lobby_details["VoiceChannelA"]))).delete(reason=f"{lobby_name} finished/cancelled")
        if lobby_details["VoiceChannelB"]:
            await (self.bot.get_channel(int(lobby_details["VoiceChannelB"]))).delete(reason=f"{lobby_name} finished/cancelled")
        DB.execute("DELETE FROM SixManLobby WHERE LobbyID = %s",
                   self.party.lobby_id)
        del self.ctx.lobbies[str(self.party.lobby_id)]

    def get_match_type(self):
        match self.game:
            case SixMansMatchType.ONE_V_ONE:
                match_type = "1v1"
            case SixMansMatchType.TWO_V_TWO:
                match_type = "2v2"
            case SixMansMatchType.THREE_V_THREE_A:
                match_type = "3v3_A"
            case SixMansMatchType.THREE_V_THREE_B:
                match_type = "3v3_B"
            case SixMansMatchType.THREE_V_THREE_C:
                match_type = "3v3_C"
        return match_type

    async def create_break_out_rooms(self):
        self.broken_out = True
        lobby_a = f"SixMans #{self.party.lobby_id} - Team {self.party.captain_one.display_name}"
        lobby_b = f"SixMans #{self.party.lobby_id} - Team {self.party.captain_two.display_name}"

        team_one_players = self.party.get_players(1)
        team_two_players = self.party.get_players(2)

        guild: discord.Guild = self.message.guild
        voice_channel_a_perms = dict(list(map(lambda user: (user, PermissionOverwrite(speak=True, connect=True, view_channel=True)), team_one_players))) | {
            guild.default_role: PermissionOverwrite(view_channel=False, connect=False)}
        voice_channel_b_perms = dict(list(map(lambda user: (user, PermissionOverwrite(speak=True, connect=True, view_channel=True)), team_two_players))) | {
            guild.default_role: PermissionOverwrite(view_channel=False, connect=False)}

        voice_channel_a = await guild.create_voice_channel(name=lobby_a, overwrites=voice_channel_a_perms, category=self.message.channel.category, reason=f"{lobby_a} created")
        voice_channel_b = await guild.create_voice_channel(name=lobby_b, overwrites=voice_channel_b_perms, category=self.message.channel.category, reason=f"{lobby_b} created")

        DB.execute("UPDATE SixManLobby SET VoiceChannelA = %s, VoiceChannelB = %s WHERE LobbyID = %s",
                   voice_channel_a.id, voice_channel_b.id, self.party.lobby_id)

        # Move members
        for member in guild.get_channel(int(DB.field("SELECT VoiceChannelID FROM SixManLobby WHERE LobbyID = %s", self.party.lobby_id))).members:
            if member in team_one_players:
                await member.move_to(voice_channel_a)
            else:
                await member.move_to(voice_channel_b)

    def generate_flag_str(self, member: discord.Member):
        data = DB.row("SELECT Type, isOnesPlayer FROM SixManUsers WHERE PartyID = %s AND UserID = %s",
                      self.party.party_id, member.id)
        flags = []
        match data["Type"]:
            case 1 | 2:
                flags.append("CAPTAIN")
        match data["isOnesPlayer"]:
            case 1:
                flags.append("1s")
            case 0:
                flags.append("2s")
            case _: pass
        flags.append("3s")
        return ", ".join(flags)

    def generate_match_summary(self) -> str:
        name_1 = f"Team {self.party.captain_one.display_name}"
        name_2 = f"Team {self.party.captain_two.display_name}"
        max_len = max(len(name_1), len(name_2))

        return f"""```
{' '* (max_len)} |1v1|2v2|3v3 #1|3v3 #2|3v3 #3|
{'-'* (max_len)} |{'-'* (3)}|{'-'* (3)}|{'-'* (6)}|{'-'* (6)}|{'-'* (6)}|
{name_1:<{max_len}} |{'-' if self.scores['1v1'][0] == None else self.scores['1v1'][0]:^3}|{'-' if self.scores['2v2'][0] == None else self.scores['2v2'][0]:^3}|{'-' if self.scores['3v3_A'][0] == None else self.scores['3v3_A'][0]:^6}|{'-' if self.scores['3v3_B'][0] == None else self.scores['3v3_B'][0]:^6}|{'-' if self.scores['3v3_C'][0] == None else self.scores['3v3_C'][0]:^6}|
{name_2:<{max_len}} |{'-' if self.scores['1v1'][1] == None else self.scores['1v1'][1]:^3}|{'-' if self.scores['2v2'][1] == None else self.scores['2v2'][1]:^3}|{'-' if self.scores['3v3_A'][1] == None else self.scores['3v3_A'][1]:^6}|{'-' if self.scores['3v3_B'][1] == None else self.scores['3v3_B'][1]:^6}|{'-' if self.scores['3v3_C'][1] == None else self.scores['3v3_C'][1]:^6}|```"""

    def generate_match_composition(self) -> str:
        players = DB.rows(
            "SELECT UserID, Type, Team, isOnesPlayer FROM SixManUsers WHERE PartyID = %s", self.party.party_id)

        ones_a = [row["UserID"]
                  for row in players if row["isOnesPlayer"] == 1 and row["Team"] == 1]
        ones_b = [row["UserID"]
                  for row in players if row["isOnesPlayer"] == 1 and row["Team"] == 2]

        twos_a = [row["UserID"]
                  for row in players if row["isOnesPlayer"] == 0 and row["Team"] == 1]
        twos_b = [row["UserID"]
                  for row in players if row["isOnesPlayer"] == 0 and row["Team"] == 2]

        threes_a = [row["UserID"] for row in players if row["Team"] == 1]
        threes_b = [row["UserID"] for row in players if row["Team"] == 2]

        match self.game:
            case SixMansMatchType.ONE_V_ONE:
                return (f"""### Now Playing: 1v1 Match\n{self.generate_members_verse_string(ones_a, ones_b)}""")
            case SixMansMatchType.TWO_V_TWO:
                return (f"""### Now Playing: 2v2 Match\n{self.generate_members_verse_string(twos_a, twos_b)}""")
            case SixMansMatchType.THREE_V_THREE_A:
                return (f"""### Now Playing: 3v3 Match #1\n{self.generate_members_verse_string(threes_a, threes_b)}""")
            case SixMansMatchType.THREE_V_THREE_B:
                return (f"""### Now Playing: 3v3 Match #2\n{self.generate_members_verse_string(threes_a, threes_b)}""")
            case SixMansMatchType.THREE_V_THREE_C:
                return (f"""### Now Playing: 3v3 Match #3\n{self.generate_members_verse_string(threes_a, threes_b)}""")

    def generate_members_verse_string(self, team_a, team_b):
        team_a_string = ', '.join(
            [self.bot.get_user(int(user_id)).mention for user_id in team_a])
        team_b_string = ', '.join(
            [self.bot.get_user(int(user_id)).mention for user_id in team_b])
        return f"""{team_a_string if team_a else 'TBD'} **vs** {team_b_string if team_b else 'TBD'}"""

    def generate_embed(self):
        team_one_players = self.party.get_players(1)
        team_two_players = self.party.get_players(2)
        team_one_str = [
            f"• **[{self.generate_flag_str(member)}]** {member.display_name}" if member else f"• {member}" for member in team_one_players]
        team_two_str = [
            f"• **[{self.generate_flag_str(member)}]** {member.display_name}" if member else f"• {member}" for member in team_two_players]
        match self.state:
            case SixMansState.PRE_LOBBY:
                description = f"Hello! Welcome to {self.bot.user.mention} Six Mans!\n\nSix Mans will start once all players have joined the voice channel. If this message does not update after all six players have already connected, try reconnecting to the call.\n\nOtherwise, if all players have not connected within {LOBBY_TIMEOUT} minutes, the lobby will automatically be deleted."
                embed: discord.Embed = self.bot.create_embed(
                    f"ScuffBot Six Mans #{self.party.lobby_id}", description, None)
                embed.set_footer(
                    text=f"Party {'N/A' if not self.party.party_id else self.party.party_id} | Game {'N/A' if not self.party.game_id else self.party.game_id}")
                return embed
            case SixMansState.CHOOSE_CAPTAIN_ONE:
                description = f"Hello! Welcome to {self.bot.user.mention} Six Mans!\n\nTo begin, {self.party.captain_one.mention} needs to select **ONE** player to join their team.\n\n"
                embed: discord.Embed = self.bot.create_embed(
                    f"ScuffBot Six Mans #{self.party.lobby_id}", description, None)
                embed.add_field(
                    name=f"Team {self.party.captain_one.display_name}", value="\n".join(team_one_str))
                embed.add_field(
                    name=f"Team {self.party.captain_two.display_name}", value="\n".join(team_two_str))
                embed.set_footer(
                    text=f"Party {'N/A' if not self.party.party_id else self.party.party_id} | Game {'N/A' if not self.party.game_id else self.party.game_id}")
                return embed
            case SixMansState.CHOOSE_CAPTAIN_TWO:
                description = f"{self.party.captain_two.mention} now needs to select **TWO** players to join their team.\n\n"
                embed: discord.Embed = self.bot.create_embed(
                    f"ScuffBot Six Mans #{self.party.lobby_id}", description, None)
                embed.add_field(
                    name=f"Team {self.party.captain_one.display_name}", value="\n".join(team_one_str))
                embed.add_field(
                    name=f"Team {self.party.captain_two.display_name}", value="\n".join(team_two_str))
                embed.set_footer(
                    text=f"Party {'N/A' if not self.party.party_id else self.party.party_id} | Game {'N/A' if not self.party.game_id else self.party.game_id}")
                return embed
            case SixMansState.CHOOSE_1S_PLAYER:
                ones_players = (DB.field("SELECT UserID FROM SixManUsers WHERE PartyID = %s AND isOnesPlayer = 1 AND Team = 1", self.party.party_id), DB.field(
                    "SELECT UserID FROM SixManUsers WHERE PartyID = %s AND isOnesPlayer = 1 AND Team = 2", self.party.party_id))
                if ones_players[0] == None and ones_players[1] == None:
                    waiting_message = "both team captains to nominate a player.**"
                elif ones_players[0] == None and ones_players[1] != None:
                    waiting_message = f"{self.party.captain_one.mention} to nominate a player.**"
                else:
                    waiting_message = f"{self.party.captain_two.mention} to nominate a player.**"
                description = f"Perfect! We now have our teams sorted. We will start off with the 1v1 match.\n\nTo begin, each team captain needs to nominate a player from their own team to play their 1s match. You can do this by clicking the **Nominate player** button below.\n\n**Currently waiting on {waiting_message}"
                embed: discord.Embed = self.bot.create_embed(
                    f"ScuffBot Six Mans #{self.party.lobby_id}", description, None)
                embed.add_field(
                    name=f"Team {self.party.captain_one.display_name}", value="\n".join(team_one_str))
                embed.add_field(
                    name=f"Team {self.party.captain_two.display_name}", value="\n".join(team_two_str))
                embed.set_footer(
                    text=f"Party {'N/A' if not self.party.party_id else self.party.party_id} | Game {'N/A' if not self.party.game_id else self.party.game_id}")
                return embed
            case SixMansState.PLAYING:
                match self.game:
                    case SixMansMatchType.PRE_MATCH:
                        description = f"Now that we have our 1s players sorted, we are ready to get the ball rolling... *pun intended :D*\n\nAmongst yourselves, please nominate a player to host a private match. Whether you create separate 1v1, 2v2, and 3v3 matches or create a single 3v3 match and re-use it for all matches is entirely up to you.\n\nFrom this point onwards, if you would like to see the entire team composition, click the **View team composition** button below.\n\nThe next screen will show you a breakdown of the matches with specific team compositions for each match.\n\nWhen you are ready to move on, click the **Break out** button below and you will be moved automatically into separate channels. May the best team win!"
                    case SixMansMatchType.ONE_V_ONE | SixMansMatchType.TWO_V_TWO | SixMansMatchType.THREE_V_THREE_A | SixMansMatchType.THREE_V_THREE_B | SixMansMatchType.THREE_V_THREE_C:
                        description = f"{self.generate_match_summary()}\n**You should now be in game playing!** All match scores will automatically populate where possible. If scores cannot be determined, a '-' will be displayed and you may amend the scores at the very end. Best of luck!\n\n{self.generate_match_composition()}\n\nOnly once you have played all your matches, press the **Go to Match Reporting** button below."
            case SixMansState.SCORE_VALIDATION:
                team_a_scores = list(
                    self.party.reported_scores[self.party.captain_one.id].values())
                team_b_scores = list(
                    self.party.reported_scores[self.party.captain_two.id].values())

                if all(map(lambda s: s == (None, None), team_a_scores)) and all(map(lambda s: s == (None, None), team_b_scores)):
                    waiting_message = "both team captains to review the match results.**"
                elif all(map(lambda s: s == (None, None), team_a_scores)) and not all(map(lambda s: s == (None, None), team_b_scores)):
                    waiting_message = f"{self.party.captain_one.mention} to review the match results.**"
                elif not all(map(lambda s: s == (None, None), team_a_scores)) and all(map(lambda s: s == (None, None), team_b_scores)):
                    waiting_message = f"{self.party.captain_two.mention} to review the match results.**"
                else:
                    waiting_message = f"a resolution to a discrepancy between reported match results.**"

                description = f"Here is a chance to review the match outcomes.\n\nIf the inferred scores did not look right, please report the correct winning teams using the button below. The report will not be registered if there is a discrepancy between both teams.\n\n**Currently waiting on {waiting_message}"
            case SixMansState.POST_MATCH:
                match self.party.calculate_winner():
                    case 1:
                        winner = self.party.captain_one.display_name
                    case 2:
                        winner = self.party.captain_two.display_name
                    case _:
                        winner = "N/A"
                description = f"### Congratulations Team {winner}!\nYou have won the six mans scrims!\n\nPress the **End Game** button below when you are done. Thanks for playing!"
            case _:
                description = "Uh oh! Something has gone wrong."
        embed: discord.Embed = self.bot.create_embed(
            f"ScuffBot Six Mans #{self.party.lobby_id}", description, None)
        embed.set_footer(
            text=f"Party {'N/A' if not self.party.party_id else self.party.party_id} | Game {'N/A' if not self.party.game_id else self.party.game_id}")
        return embed

    def add_button(self, label: str, style: discord.ButtonStyle, callback: Callable[[discord.Interaction], Any], **kwargs):
        button = Button(label=label, style=style, row=1, **kwargs)
        button.callback = callback
        self.add_item(button)

    def update_options(self):
        self.clear_items()
        match self.state:
            case SixMansState.CHOOSE_CAPTAIN_ONE | SixMansState.CHOOSE_CAPTAIN_TWO:
                self.add_button(
                    "Choose Player(s)", discord.ButtonStyle.blurple, self.choose_button_callback)
                self.add_button(
                    "Cancel Game", discord.ButtonStyle.red, self.cancel_button_callback)
            case SixMansState.CHOOSE_1S_PLAYER:
                self.add_button(
                    "Nominate Player", discord.ButtonStyle.blurple, self.choose_button_callback)
                self.add_button(
                    "Cancel Game", discord.ButtonStyle.red, self.cancel_button_callback)
            case SixMansState.PLAYING:
                match self.game:
                    case SixMansMatchType.PRE_MATCH:
                        self.add_button(
                            "Break Out", discord.ButtonStyle.blurple, self.break_out_button_callback)
                        self.add_button(
                            "Stay Together", discord.ButtonStyle.grey, self.start_game)
                        self.add_button("View Team Composition", discord.ButtonStyle.grey,
                                        self.team_composition_callback, custom_id="team_comp")
                    case SixMansMatchType.ONE_V_ONE | SixMansMatchType.TWO_V_TWO | SixMansMatchType.THREE_V_THREE_A | SixMansMatchType.THREE_V_THREE_B | SixMansMatchType.THREE_V_THREE_C:
                        self.add_button(
                            f"Go to Match Reporting", discord.ButtonStyle.blurple, self.go_to_match_reporting_callback)
                        self.add_button("View Team Composition", discord.ButtonStyle.grey,
                                        self.team_composition_callback, custom_id="team_comp")
            case SixMansState.SCORE_VALIDATION:
                self.add_button(
                    "Review Matches", discord.ButtonStyle.blurple, self.send_report_view)
            case SixMansState.POST_MATCH:
                self.add_button("End Game", discord.ButtonStyle.red,
                                self.cancel_button_callback)

    async def update_view(self, embed=None):
        self.update_options()
        if self.message:
            await self.message.edit(embed=embed or self.generate_embed(), view=self)

    async def cancel_button_callback(self, _: discord.Interaction):
        await self.delete_lobby()

    async def choose_button_callback(self, interaction: discord.Interaction):
        match self.state:
            case SixMansState.CHOOSE_CAPTAIN_ONE | SixMansState.CHOOSE_CAPTAIN_TWO:
                users = [interaction.client.get_user(int(user_id)) for user_id in DB.column(
                    "SELECT UserID FROM SixManUsers WHERE PartyID = %s AND Team = 0", self.party.party_id)]
                reason = "join your team."
            case SixMansState.CHOOSE_1S_PLAYER:
                users = [interaction.client.get_user(int(user_id)) for user_id in DB.column("SELECT UserID FROM SixManUsers WHERE PartyID = %s AND Team = %s", self.party.party_id, DB.field(
                    "SELECT Team FROM SixManUsers WHERE UserID = %s AND PartyID = %s", interaction.user.id, self.party.party_id))]
                reason = "play your 1s match."
        view = UserDropdownView(self, message_interaction=interaction, users=users, amount=1 if self.state in [
                                SixMansState.CHOOSE_CAPTAIN_ONE, SixMansState.CHOOSE_1S_PLAYER] else 2 if self.state == SixMansState.CHOOSE_CAPTAIN_TWO else 0, reason=reason)
        await interaction.response.send_message(view=view, ephemeral=True)

    async def start_game(self, interaction: discord.Interaction = None):
        if interaction != None:
            await interaction.response.defer()
        self.game = SixMansMatchType.ONE_V_ONE
        DB.execute("INSERT INTO SixManGames () VALUES ()")
        self.party.game_id = DB.field("SELECT MAX(GameID) FROM SixManGames")
        DB.execute("UPDATE SixManParty SET GameID = %s WHERE PartyID = %s",
                   self.party.game_id, self.party.party_id)
        await self.update_view()

    async def break_out_button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.broken_out:
            return
        await self.create_break_out_rooms()
        await self.start_game()

    async def go_to_match_reporting_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.game != SixMansMatchType.THREE_V_THREE_C:
            view = ConfirmButtons()
            view.message = await interaction.followup.send("Are you sure you have played **all** the necessary matches? You can not go back after match reporting.", view=view, ephemeral=True)
            await view.wait()
            if not view.confirmed:
                return
        self.state = SixMansState.SCORE_VALIDATION
        await self.update_view()

    async def send_report_view(self, interaction: discord.Interaction):
        await interaction.response.send_message(view=ReportMatches(self), ephemeral=True)

    async def team_composition_callback(self, interaction: discord.Interaction):
        team_one_players = self.party.get_players(1)
        team_two_players = self.party.get_players(2)
        team_one_str = [
            f"• **[{self.generate_flag_str(member)}]** {member.display_name}" if member else f"• {member}" for member in team_one_players]
        team_two_str = [
            f"• **[{self.generate_flag_str(member)}]** {member.display_name}" if member else f"• {member}" for member in team_two_players]
        embed: discord.Embed = self.bot.create_embed(
            f"ScuffBot Six Mans #{self.party.lobby_id}", "", None)
        embed.add_field(
            name=f"Team {self.party.captain_one.display_name}", value="\n".join(team_one_str))
        embed.add_field(
            name=f"Team {self.party.captain_two.display_name}", value="\n".join(team_two_str))
        embed.set_footer(
            text=f"Party {'N/A' if not self.party.party_id else self.party.party_id} | Game {'N/A' if not self.party.game_id else self.party.game_id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ConfirmButtons(View):
    def __init__(self, *, timeout=10):
        super().__init__(timeout=timeout)
        self.confirmed = None

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def accept_button(self, interaction: discord.Interaction, button: Button):
        self.confirmed = True
        self.clear_items()
        await interaction.response.edit_message(view=self)
        self.stop()


class TeamDropdown(Select):
    def __init__(self, teams: list[str], match_type: str, winner: int = -1):
        self.match_type = match_type
        options = [discord.SelectOption(
            label=team, value=idx, default=winner == idx) for idx, team in enumerate(teams)]
        super().__init__(placeholder=f"Select the winning team for the {match_type.split('_')[0]} series",
                         min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()


class ReportMatches(View):

    def __init__(self, ctx: SixMansPrompt) -> None:
        super().__init__(timeout=None)
        self.ctx = ctx
        self.selects = list()

        teams = [f"Team {self.ctx.party.captain_one.display_name}",
                 f"Team {self.ctx.party.captain_two.display_name}"]

        # 1v1, 2v2 series
        for match in list(self.ctx.scores.items())[:3]:
            if match[0].startswith("3v3"):
                winner = self.ctx.party.calculate_winner([0 if value is None else value for tup in list(
                    self.ctx.scores.values())[2:] for value in tup]) - 1
            else:
                winner = (0 if match[1][0] > match[1][1] else 1) if all(
                    map(lambda s: s is not None, match[1])) else -1
            select = TeamDropdown(teams, match[0], winner)
            self.add_item(select)
            self.selects.append(select)

        self.submit_button = discord.ui.Button(
            label="Submit", style=discord.ButtonStyle.green)
        self.submit_button.callback = self.submit_button_callback
        self.add_item(self.submit_button)

    async def submit_button_callback(self, interaction: discord.Interaction):
        if any(map(lambda s: len(s.values) == 0 and all(map(lambda o: o.default == False, s.options)), self.selects)):
            return await interaction.response.send_message("You must report all series scores first before submitting.\n\nIf it appears like you have reported all 3 series outcomes, try clicking **Review Matches** again and after interacting with a single dropdown, wait until the blinking dots next to the dropdown disappears before moving onto the next dropdown.", ephemeral=True)
        for select in self.selects:
            match_type = select.match_type

            score = [0, 0]
            if select.values:
                score[int(select.values[0])] = 1
            else:
                score[int(next(filter(lambda o: o.default ==
                          True, select.options)).value)] = 1
            self.ctx.party.reported_scores[interaction.user.id][match_type] = tuple(
                score)
            if match_type.startswith("3v3"):
                for m in ["3v3_B", "3v3_C"]:
                    score = [0, 0]
                    if select.values:
                        score[int(select.values[0])] = 1
                    else:
                        score[int(next(filter(lambda o: o.default ==
                                              True, select.options)).value)] = 1
                    self.ctx.party.reported_scores[interaction.user.id][m] = tuple(
                        score)

        team_a_scores = list(
            self.ctx.party.reported_scores[self.ctx.party.captain_one.id].values())
        team_b_scores = list(
            self.ctx.party.reported_scores[self.ctx.party.captain_two.id].values())

        if all(map(lambda s: s == (None, None), team_a_scores)) and not all(map(lambda s: s == (None, None), team_b_scores)):
            waiting_message = f"We have received your report. Thanks! We are currently waiting for {self.ctx.party.captain_one.mention} to review the match results."
        elif not all(map(lambda s: s == (None, None), team_a_scores)) and all(map(lambda s: s == (None, None), team_b_scores)):
            waiting_message = f"We have received your report. Thanks! We are currently waiting for {self.ctx.party.captain_two.mention} to review the match results."
        elif team_a_scores != team_b_scores:
            waiting_message = f"**Unfortunately, the reported match outcomes do not match across both team captains. Please resolve this discrepancy.**"
        else:
            waiting_message = f"Thanks for reporting the match outcomes. Your report matches the opposition's report."

        await interaction.response.send_message(waiting_message, ephemeral=True)
        # Check if both scores are present and compare
        scores = list(self.ctx.party.reported_scores.values())
        if scores[0] == scores[1]:
            for select in self.selects:
                match_type = select.match_type
                # Both scores set and equal
                DB.execute(f"UPDATE SixManGames SET {match_type}_A = %s, {match_type}_B = %s WHERE GameID = %s",
                           scores[0][match_type][0], scores[1][match_type][1], self.ctx.party.game_id)
                if match_type.startswith("3v3"):
                    for m in ["3v3_B", "3v3_C"]:
                        DB.execute(f"UPDATE SixManGames SET {m}_A = %s, {m}_B = %s WHERE GameID = %s",
                                   scores[0][m][0], scores[1][m][1], self.ctx.party.game_id)
            self.ctx.state = SixMansState.POST_MATCH
        await self.ctx.update_view()


class SixMansCommands(app_commands.Group):
    def __init__(self, ctx):
        super().__init__(name="sixmans", description="Manage six man lobbies")
        self.ctx = ctx

    @app_commands.command(name="close", description="Closes an existing six mans lobby.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        lobby_id="The six mans lobby number to close."
    )
    async def close(self, interaction: discord.Interaction, lobby_id: str):
        await interaction.response.defer(ephemeral=True)
        if lobby_id in self.ctx.lobbies:
            await self.ctx.lobbies[lobby_id].delete_lobby()
            await interaction.followup.send(embed=self.ctx.bot.create_embed("SCUFFBOT SIX MANS", f"Successfully closed SixMans #{lobby_id}", None), ephemeral=True)
        else:
            await interaction.followup.send(embed=self.ctx.bot.create_embed("SCUFFBOT SIX MANS", f"SixMans #{lobby_id} does not exist", None), ephemeral=True)

    @close.autocomplete("lobby_id")
    async def autocomplete_callback(self, _: discord.Interaction, current: str):
        return [app_commands.Choice(name=lobby_id, value=lobby_id) for lobby_id in self.ctx.lobbies]


class SixMans(commands.Cog):
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.queue_prompt = QueuePrompt(self, None)
        self.player_queue = SixMansQueue(self.queue_prompt)
        self.category = config["SIX_MAN"]["CATEGORY"]

        self.lobbies = dict()

    async def cog_load(self):
        asyncio.create_task(self.create_queue_prompt())
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")

    async def create_queue_prompt(self):
        await self.bot.wait_until_ready()
        category_channel = self.bot.get_channel(self.category)
        prompt_channel = next(
            filter(lambda c: "join-queue" in c.name, category_channel.text_channels), None)
        if prompt_channel == None:
            channel = await category_channel.create_text_channel("join-queue", overwrites={category_channel.guild.default_role: PermissionOverwrite(send_messages=False, view_channel=True)})
            await asyncio.sleep(3)
            message = await channel.send(None, embed=self.bot.create_embed("SCUFFBOT SIX MANS", f"To join/leave the six man queue, click the respective button below.",  None))
            self.queue_prompt = QueuePrompt(self, message)
        else:
            message = next(iter([message async for message in prompt_channel.history() if message.author == self.bot.user]))
            self.queue_prompt.message = message
        await self.queue_prompt.update_view()

    async def generate_lobby_id(self):
        highest_lobby_num = max(
            [0] + (lobbies := DB.column("SELECT LobbyID FROM SixManParty WHERE LobbyID IS NOT NULL")))
        r = list(range(1, highest_lobby_num))
        possible_lobby_nums = [i for i in r if i not in lobbies]
        return highest_lobby_num + 1 if not possible_lobby_nums else possible_lobby_nums.pop(0)

    async def create_party(self, members):
        lobby_id = await self.generate_lobby_id()
        lobby_name = f"SixMans #{lobby_id}"

        guild: discord.Guild = members[0].guild

        # Create role
        lobby_role = await guild.create_role(name=lobby_name, reason=f"{lobby_name} created")

        # Create perms
        vc_perms = {lobby_role: PermissionOverwrite(
            speak=True, connect=True, view_channel=True), guild.default_role: PermissionOverwrite(view_channel=False, connect=False)}
        text_perms = {lobby_role: PermissionOverwrite(
            read_messages=True, send_messages=False), guild.default_role: PermissionOverwrite(read_messages=False, view_channel=False)}

        # Create voice channel
        voice_channel = await guild.create_voice_channel(name=lobby_name, overwrites=vc_perms, category=self.bot.get_channel(self.category), reason=f"{lobby_name} created")

        # Create text channel
        text_channel = await guild.create_text_channel(name=f"six-mans-{lobby_id}", overwrites=text_perms, category=self.bot.get_channel(self.category), reason=f"{lobby_name} created")

        # Send preliminary starting message
        message = await text_channel.send(embed=self.bot.create_embed("SCUFFBOT SIX MANS", f"SCUFFBOT is creating the six mans lobby. Please do not join the call until the six mans lobby is ready. This message will update once complete.", None))
        DB.execute("INSERT INTO SixManLobby (LobbyID, MessageID, VoiceChannelID, TextChannelID, RoleID) VALUES (%s, %s, %s, %s, %s)",
                   lobby_id, message.id, voice_channel.id, text_channel.id, lobby_role.id)
        DB.execute("INSERT INTO SixManParty (LobbyID) VALUES (%s)", lobby_id)
        party_id = DB.field("SELECT MAX(PartyID) FROM SixManParty")

        # Invite members
        lobby_invite_link = str(await voice_channel.create_invite(reason=f"{lobby_name} created"))
        for member in members:
            await member.add_roles(lobby_role, reason=f"{member} added to {lobby_name}")
            await member.send(embed=self.bot.create_embed("SCUFFBOT SIX MANS", f"You have been added into **{lobby_name}**. Failing to join within {LOBBY_TIMEOUT} minutes will drop the match.", None), view=View().add_item(discord.ui.Button(label="Join Six Mans", style=discord.ButtonStyle.link, url=lobby_invite_link)))
            DB.execute(
                "INSERT INTO SixManUsers (PartyID, UserID) VALUES (%s, %s)", party_id, member.id)
        await text_channel.send(content=lobby_role.mention, delete_after=5)
        return (lobby_id, party_id)

    async def start(self, lobby_id: int, party_id: int):
        text_channel = self.bot.get_channel(int(DB.field(
            "SELECT TextChannelID FROM SixManLobby WHERE LobbyID = %s", lobby_id)))
        voice_channel = self.bot.get_channel(int(DB.field(
            "SELECT VoiceChannelID FROM SixManLobby WHERE LobbyID = %s", lobby_id)))
        message = await text_channel.fetch_message(int(DB.field("SELECT MessageID FROM SixManLobby WHERE LobbyID = %s", lobby_id)))
        view = SixMansPrompt(self, party_id)
        view.message = message
        self.lobbies[str(lobby_id)] = view
        await view.update_view()

        # Delete lobby if not all people have joined
        await asyncio.sleep(LOBBY_TIMEOUT * 60)
        if len(voice_channel.members) != PARTY_SIZE and view.state == SixMansState.PRE_LOBBY:
            await view.delete_lobby()


async def setup(bot):
    ctx = SixMans(bot)
    bot.add_view(ctx.queue_prompt)
    bot.tree.add_command(SixMansCommands(ctx))
    await bot.add_cog(ctx)


class QueuePrompt(View):

    def __init__(self, ctx: SixMans, message: discord.Message):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.message = message
        join_button = Button(
            label="Join Queue", style=discord.ButtonStyle.green, custom_id="queue_prompt_join")
        join_button.callback = self.join_callback
        self.add_item(join_button)
        leave_button = Button(
            label="Leave Queue", style=discord.ButtonStyle.grey, custom_id="queue_prompt_leave")
        leave_button.callback = self.leave_callback
        self.add_item(leave_button)

    def generate_embed(self):
        queue_len = len(self.ctx.player_queue)
        return self.ctx.bot.create_embed("SCUFFBOT SIX MANS", f"To join/leave the six man queue, click the respective button below.\n\nThere {'is' if queue_len == 1 else 'are'} currently **{queue_len} {'player' if queue_len == 1 else 'players'}** in the queue.", None)

    async def update_view(self, embed=None):
        if self.message:
            await self.message.edit(embed=embed or self.generate_embed(), view=self)

    async def join_callback(self, interaction: discord.Interaction):
        if interaction.user in self.ctx.player_queue:
            await interaction.response.send_message(embed=interaction.client.create_embed("SCUFFBOT SIX MANS", f"You are already in the queue.", None), ephemeral=True)
        elif str(interaction.user.id) in DB.column("SELECT A.UserID FROM SixManUsers A INNER JOIN SixManParty B WHERE A.PartyID = B.PartyID AND B.LobbyID IS NOT NULL"):
            await interaction.response.send_message(embed=interaction.client.create_embed("SCUFFBOT SIX MANS", f"You are already in a six mans lobby. Failed to join queue.", None), ephemeral=True)
        else:
            self.ctx.player_queue.add(interaction.user)
            await interaction.response.send_message(embed=interaction.client.create_embed("SCUFFBOT SIX MANS", f"You have joined the six mans queue. ({len(self.ctx.player_queue)}/{PARTY_SIZE})", None), ephemeral=True)
            if ((party := self.ctx.player_queue.get_party())):
                lobby_id, party_id = await self.ctx.create_party(party)
                await self.update_view()
                await self.ctx.start(lobby_id, party_id)
            await self.update_view()

    async def leave_callback(self, interaction: discord.Interaction):
        if not interaction.user in self.ctx.player_queue:
            await interaction.response.send_message(embed=interaction.client.create_embed("SCUFFBOT SIX MANS", f"You are not in a queue. Click the `Join Queue` button to join the queue.", None), ephemeral=True)
        else:
            self.ctx.player_queue.remove(interaction.user)
            await interaction.response.send_message(embed=interaction.client.create_embed("SCUFFBOT SIX MANS", f"You have left the six mans queue.", None), ephemeral=True)
            await self.update_view()


class UserDropdown(Select):
    def __init__(self, users: list[discord.Member], amount: int, reason: str):
        options = [discord.SelectOption(
            label=user.display_name, value=user.id) for user in users]
        super().__init__(placeholder=f"Choose {amount} {'member' if amount == 1 else 'members'} to {reason}",
                         min_values=amount, max_values=amount, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()


class UserDropdownView(View):
    def __init__(self, ctx: SixMansPrompt, message_interaction: discord.Interaction, users: list[discord.Member], amount: int, reason: str):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.message_interaction = message_interaction
        self.reason = reason

        self.user_dropdown = UserDropdown(users, amount, reason)
        self.add_item(self.user_dropdown)

        self.submit_button = discord.ui.Button(
            label="Submit", style=discord.ButtonStyle.green)
        self.submit_button.callback = self.submit_button_callback
        self.add_item(self.submit_button)

    async def submit_button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not self.user_dropdown.values:
            return await interaction.followup.send("Your selection can not be empty.", ephemeral=True)
        match self.ctx.state:
            case SixMansState.CHOOSE_CAPTAIN_ONE:
                for user_id in self.user_dropdown.values:
                    DB.execute("UPDATE SixManUsers SET Team = 1 WHERE UserID = %s AND PartyID = %s",
                               user_id, self.ctx.party.party_id)
                self.ctx.state = SixMansState.CHOOSE_CAPTAIN_TWO
            case SixMansState.CHOOSE_CAPTAIN_TWO:
                for user_id in self.user_dropdown.values:
                    DB.execute("UPDATE SixManUsers SET Team = 2 WHERE UserID = %s  AND PartyID = %s",
                               user_id, self.ctx.party.party_id)
                # Add last player
                last_player_id = DB.field(
                    "SELECT UserID FROM SixManUsers WHERE PartyID = %s AND Team = 0", self.ctx.party.party_id)
                DB.execute(
                    "UPDATE SixManUsers SET Team = 1 WHERE UserID = %s", last_player_id)
                self.ctx.state = SixMansState.CHOOSE_1S_PLAYER
            case SixMansState.CHOOSE_1S_PLAYER:
                DB.execute("UPDATE SixManUsers SET isOnesPlayer = 1 WHERE UserID = %s AND PartyID = %s",
                           self.user_dropdown.values[0], self.ctx.party.party_id)
                if len(DB.rows("SELECT UserID FROM SixManUsers WHERE PartyID = %s AND isOnesPlayer = 1", self.ctx.party.party_id)) == 2:
                    DB.execute(
                        "UPDATE SixManUsers SET isOnesPlayer = 0 WHERE PartyID = %s AND isOnesPlayer IS NULL", self.ctx.party.party_id)
                    self.ctx.state = SixMansState.PLAYING
        await self.message_interaction.edit_original_response(content=f"You have selected {', '.join([interaction.client.get_user(int(user_id)).mention for user_id in self.user_dropdown.values])} to {self.reason}", view=None)
        await self.ctx.update_view()

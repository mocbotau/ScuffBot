from discord.ext import commands
from discord.ui import Button, View, Select, Modal, TextInput
from discord import app_commands, PermissionOverwrite, Object
from src.lib.bot import config, DB
from typing import Any, Callable, Union
import discord
import logging

from src.utils.SixMans import PARTY_SIZE, SixMansState, SixMansMatchType, SixMansParty

class SixMansPrompt(View):
    def __init__(self, bot: discord.Client, party_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.message: Union[None | discord.Message] = None
        
        self.state = SixMansState.CHOOSE_CAPTAIN_ONE
        self.game = SixMansMatchType.PRE_MATCH
        
        self.party = SixMansParty(bot, party_id)
        
    async def interaction_check(self, interaction: discord.Interaction):
        if "custom_id" in interaction.data and interaction.data["custom_id"] == "team_comp": return True
        match self.state:
            case SixMansState.CHOOSE_CAPTAIN_ONE:
                if interaction.user and interaction.user.id != self.party.captain_one.id:
                    await interaction.response.send_message(f"Only {self.party.captain_one.mention} can do this.", ephemeral=True)
                return interaction.user and interaction.user.id == self.party.captain_one.id
            case SixMansState.CHOOSE_CAPTAIN_TWO:
                if interaction.user and interaction.user.id != self.party.captain_two.id:
                    await interaction.response.send_message(f"Only {self.party.captain_two.mention} can do this.", ephemeral=True)
                return interaction.user and interaction.user.id == self.party.captain_two.id
            case SixMansState.CHOOSE_1S_PLAYER | SixMansState.PLAYING | SixMansState.SCORE_UPLOAD | SixMansState.POST_MATCH:
                if interaction.user and interaction.user.id not in [self.party.captain_one.id, self.party.captain_two.id]:
                    await interaction.response.send_message(f"Only {self.party.captain_one.mention} or {self.party.captain_two.mention} can do this.", ephemeral=True)
                return interaction.user and interaction.user.id in [self.party.captain_one.id, self.party.captain_two.id]
                   
    async def delete_lobby(self):
        lobby_details = await self.party.get_details()
        lobby_name = f"SixMans #{self.party.lobby_id}"
        
        guild = self.bot.get_channel(int(lobby_details["VoiceChannelID"])).guild
        await (guild.get_role(int(lobby_details["RoleID"]))).delete(reason=f"{lobby_name} finished/cancelled")
        await (self.bot.get_channel(int(lobby_details["VoiceChannelID"]))).delete(reason=f"{lobby_name} finished/cancelled")
        await (self.bot.get_channel(int(lobby_details["TextChannelID"]))).delete(reason=f"{lobby_name} finished/cancelled")
        
        if lobby_details["VoiceChannelA"]:
            await (self.bot.get_channel(int(lobby_details["VoiceChannelA"]))).delete(reason=f"{lobby_name} finished/cancelled")
        if lobby_details["VoiceChannelB"]:
            await (self.bot.get_channel(int(lobby_details["VoiceChannelB"]))).delete(reason=f"{lobby_name} finished/cancelled")
        DB.execute("DELETE FROM SixManLobby WHERE LobbyID = %s", self.party.lobby_id)

    def get_match_type(self):
        match self.game:
            case SixMansMatchType.ONE_V_ONE:
                match_type = "1v1"
            case SixMansMatchType.TWO_V_TWO:
                match_type = "2v2"
            case SixMansMatchType.THREE_V_THREE:
                match_type = "3v3"
        return match_type
   
    async def create_break_out_rooms(self):
        lobby_a = f"SixMans #{self.party.lobby_id} - Team {self.party.captain_one.display_name}"
        lobby_b = f"SixMans #{self.party.lobby_id} - Team {self.party.captain_two.display_name}"

        team_one_players = self.party.get_players(1)
        team_two_players = self.party.get_players(2)

        guild: discord.Guild = self.message.guild
        voice_channel_a_perms = dict(list(map(lambda user: (user, PermissionOverwrite(speak=True,connect=True,view_channel=True)), team_one_players))) | {guild.default_role: PermissionOverwrite(view_channel=True, connect=False)}
        voice_channel_b_perms = dict(list(map(lambda user: (user, PermissionOverwrite(speak=True,connect=True,view_channel=True)), team_two_players))) | {guild.default_role: PermissionOverwrite(view_channel=True, connect=False)}

        voice_channel_a = await guild.create_voice_channel(name=lobby_a, overwrites=voice_channel_a_perms, category=self.message.channel.category, reason=f"{lobby_a} created")
        voice_channel_b = await guild.create_voice_channel(name=lobby_b, overwrites=voice_channel_b_perms, category=self.message.channel.category, reason=f"{lobby_b} created")

        DB.execute("UPDATE SixManLobby SET VoiceChannelA = %s, VoiceChannelB = %s WHERE LobbyID = %s", voice_channel_a.id, voice_channel_b.id, self.party.lobby_id)
        
        # Move members
        for member in guild.get_channel(int(DB.field("SELECT VoiceChannelID FROM SixManLobby WHERE LobbyID = %s", self.party.lobby_id))).members:
            if member in team_one_players:
                await member.move_to(voice_channel_a)
            else:
                await member.move_to(voice_channel_b)

    def generate_flag_str(self, member: discord.Member):
        data = DB.row("SELECT Type, isOnesPlayer FROM SixManUsers WHERE PartyID = %s AND UserID = %s", self.party.party_id, member.id)
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
        scores = [0 if x is None else x for x in DB.row("SELECT 1v1_A, 1v1_B, 2v2_A, 2v2_B, 3v3_A, 3v3_B FROM SixManGames WHERE GameID = %s", self.party.game_id).values()]
        team_a = ['W' if x else '-' for x in [scores[i] > scores[i + 1] for i in range(0, len(scores), 2)]]
        team_b = ['W' if x else '-' for x in [scores[i+1] > scores[i] for i in range(0, len(scores), 2)]]

        return (f"""```
|        | 1v1 | 2v2 | 3v3 |
|--------|-----|-----|-----|
| Team A |  {team_a[0]}  |  {team_a[1]}  |  {team_a[2]}  |
| Team B |  {team_b[0]}  |  {team_b[1]}  |  {team_b[2]}  |```""")
    
    def generate_match_composition(self) -> str:
        players = DB.rows("SELECT UserID, Type, Team, isOnesPlayer FROM SixManUsers WHERE PartyID = %s", self.party.party_id)

        ones_a = [row["UserID"] for row in players if row["isOnesPlayer"] == 1 and row["Team"] == 1]
        ones_b = [row["UserID"] for row in players if row["isOnesPlayer"] == 1 and row["Team"] == 2]
        
        twos_a = [row["UserID"] for row in players if row["isOnesPlayer"] == 0 and row["Team"] == 1]
        twos_b = [row["UserID"] for row in players if row["isOnesPlayer"] == 0 and row["Team"] == 2]
        
        threes_a = [row["UserID"] for row in players if row["Team"] == 1]
        threes_b = [row["UserID"] for row in players if row["Team"] == 2]

        return (f"""### 1v1 Match {'[NOW PLAYING]' if self.game == SixMansMatchType.ONE_V_ONE else ''}
{', '.join([self.bot.get_user(int(user_id)).display_name for user_id in ones_a]) if ones_a else 'TBD'} **vs** {', '.join([self.bot.get_user(int(user_id)).display_name for user_id in ones_b]) if ones_b else 'TBD'}
### 2v2 Match {'[NOW PLAYING]' if self.game == SixMansMatchType.TWO_V_TWO else ''}
{', '.join([self.bot.get_user(int(user_id)).display_name for user_id in twos_a]) if twos_a else 'TBD'} **vs** {', '.join([self.bot.get_user(int(user_id)).display_name for user_id in twos_b]) if twos_b else 'TBD'}
### 3v3 Match {'[NOW PLAYING]' if self.game == SixMansMatchType.THREE_V_THREE else ''}
{', '.join([self.bot.get_user(int(user_id)).display_name for user_id in threes_a]) if threes_a else 'TBD'} **vs** {', '.join([self.bot.get_user(int(user_id)).display_name for user_id in threes_b]) if threes_b else 'TBD'}
""")

    def generate_embed(self):
        team_one_players = self.party.get_players(1)
        team_two_players = self.party.get_players(2)
        team_one_str = [f"• **[{self.generate_flag_str(member)}]** {member.display_name}" if member else f"• {member}" for member in team_one_players]
        team_two_str = [f"• **[{self.generate_flag_str(member)}]** {member.display_name}" if member else f"• {member}" for member in team_two_players]
        match self.state:
            case SixMansState.CHOOSE_CAPTAIN_ONE:
                description = f"Hello! Welcome to {self.bot.user.mention} Six Mans!\n\nTo begin, {self.party.captain_one.mention} needs to select **ONE** player to join their team.\n\n"
                embed: discord.Embed = self.bot.create_embed(f"ScuffBot Six Mans #{self.party.lobby_id}", description, None)
                embed.add_field(name="Team A", value="\n".join(team_one_str))
                embed.add_field(name="Team B", value="\n".join(team_two_str))
                embed.set_footer(text=f"Party {'N/A' if not self.party.party_id else self.party.party_id} | Game {'N/A' if not self.party.game_id else self.party.game_id}")
                return embed
            case SixMansState.CHOOSE_CAPTAIN_TWO:
                description = f"{self.party.captain_two.mention} now needs to select **TWO** players to join their team.\n\n"
                embed: discord.Embed = self.bot.create_embed(f"ScuffBot Six Mans #{self.party.lobby_id}", description, None)
                embed.add_field(name="Team A", value="\n".join(team_one_str))
                embed.add_field(name="Team B", value="\n".join(team_two_str))
                embed.set_footer(text=f"Party {'N/A' if not self.party.party_id else self.party.party_id} | Game {'N/A' if not self.party.game_id else self.party.game_id}")
                return embed
            case SixMansState.CHOOSE_1S_PLAYER:
                ones_players = (DB.field("SELECT UserID FROM SixManUsers WHERE PartyID = %s AND isOnesPlayer = 1 AND Team = 1", self.party.party_id), DB.field("SELECT UserID FROM SixManUsers WHERE PartyID = %s AND isOnesPlayer = 1 AND Team = 2", self.party.party_id))
                if ones_players[0] == None and ones_players[1] == None:
                    waiting_message = "both team captains to nominate a player.**"
                elif ones_players[0] == None and ones_players[1] != None:
                    waiting_message = f"{self.party.captain_one.mention} to nominate a player.**"
                else:
                    waiting_message = f"{self.party.captain_two.mention} to nominate a player.**"
                description = f"Perfect! We now have our teams sorted. We will start off with the 1v1 match.\n\nTo begin, each team captain needs to nominate a player from their own team to play their 1s match. You can do this by clicking the **Nominate player** button below.\n\n**Currently waiting on {waiting_message}"
                embed: discord.Embed = self.bot.create_embed(f"ScuffBot Six Mans #{self.party.lobby_id}", description, None)
                embed.add_field(name="Team A", value="\n".join(team_one_str))
                embed.add_field(name="Team B", value="\n".join(team_two_str))
                embed.set_footer(text=f"Party {'N/A' if not self.party.party_id else self.party.party_id} | Game {'N/A' if not self.party.game_id else self.party.game_id}")
                return embed
            case SixMansState.PLAYING:
                match self.game:
                    case SixMansMatchType.PRE_MATCH:
                        description = f"Now that we have our 1s players sorted, we are ready to get the ball rolling... *pun intended :D*\n\nAmongst yourselves, please nominate a player to host a private match. Whether you create separate 1v1, 2v2, and 3v3 matches or create a single 3v3 match and re-use it for all matches is entirely up to you.\n\nFrom this point onwards, if you would like to see the entire team composition, click the **View team composition** button below.\n\nThe next screen will show you a breakdown of the matches with specific team compositions for each match.\n\nWhen you are ready to move on, click the **Break out** button below and you will be moved automatically into separate channels. May the best team win!"
                    case SixMansMatchType.ONE_V_ONE | SixMansMatchType.TWO_V_TWO | SixMansMatchType.THREE_V_THREE:
                        match_type = self.get_match_type()
                        description = f"You are now playing the {match_type} match. **Don't forget to come back here before your next game starts.**\n\n{self.generate_match_summary()}\n{self.generate_match_composition()}\n\nOnce you have finished your {match_type} match, click on the **Finish {match_type}** button below. Best of luck!"
            case SixMansState.SCORE_UPLOAD:
                match_type = self.get_match_type()
                
                team_a_reported_score = self.party.reported_scores[self.party.captain_one.id][match_type]
                team_b_reported_score = self.party.reported_scores[self.party.captain_two.id][match_type]

                if team_a_reported_score == (None, None) and team_b_reported_score == (None, None):
                    waiting_message = "both team captains to upload the match score.**"
                elif team_a_reported_score == (None, None) and team_b_reported_score != (None, None):
                    waiting_message = f"{self.party.captain_one.mention} to upload the match score.**"
                elif team_a_reported_score != (None, None) and team_b_reported_score == (None, None):
                    waiting_message = f"{self.party.captain_two.mention} to upload the match score.**"
                else:
                    waiting_message = f"a resolution to a discrepancy between reported match scores.**"

                description = f"Now that the {match_type} match is complete, both team captains must upload the score of the match.\n\nThe score will not be registered if there is a score discrepancy between both teams.\n\n**Currently waiting on {waiting_message}"
            case SixMansState.POST_MATCH:
                match self.party.calculate_winner():
                    case 1:
                        winner = "A"
                    case 2:
                        winner = "B"
                description = f"### Congratulations Team {winner}!\nYou have won the six mans scrims!\n\nPress the **End Game** button below when you are done. Thanks for playing!"
            case _:
                description = "Uh oh! Something has gone wrong."
        embed: discord.Embed = self.bot.create_embed(f"ScuffBot Six Mans #{self.party.lobby_id}", description, None)
        embed.set_footer(text=f"Party {'N/A' if not self.party.party_id else self.party.party_id} | Game {'N/A' if not self.party.game_id else self.party.game_id}")
        return embed

    def add_button(self, label: str, style: discord.ButtonStyle, callback: Callable[[discord.Interaction], Any], **kwargs):
        button = Button(label=label, style=style, row=1, **kwargs)
        button.callback = callback
        self.add_item(button)

    def update_options(self):
        self.clear_items()
        match self.state:
            case SixMansState.CHOOSE_CAPTAIN_ONE | SixMansState.CHOOSE_CAPTAIN_TWO:
                self.add_button("Choose Player(s)", discord.ButtonStyle.blurple, self.choose_button_callback)
                self.add_button("Cancel Game", discord.ButtonStyle.red, self.cancel_button_callback)
            case SixMansState.CHOOSE_1S_PLAYER:
                self.add_button("Nominate Player", discord.ButtonStyle.blurple, self.choose_button_callback)
                self.add_button("Cancel Game", discord.ButtonStyle.red, self.cancel_button_callback)
            case SixMansState.PLAYING:
                match self.game:
                    case SixMansMatchType.PRE_MATCH:
                        self.add_button("Break Out", discord.ButtonStyle.blurple, self.break_out_button_callback)
                        self.add_button("View Team Composition", discord.ButtonStyle.grey, self.team_composition_callback, custom_id="team_comp")
                    case SixMansMatchType.ONE_V_ONE | SixMansMatchType.TWO_V_TWO | SixMansMatchType.THREE_V_THREE:
                        match_label = self.get_match_type()
                        self.add_button(f"Finish {match_label}", discord.ButtonStyle.blurple, self.finish_button_callback)
                        self.add_button("View Team Composition", discord.ButtonStyle.grey, self.team_composition_callback, custom_id="team_comp")
                        self.add_button(f"Surrender {match_label}", discord.ButtonStyle.red, self.surrender_button_callback)
            case SixMansState.SCORE_UPLOAD:
                self.add_button("Upload Scores", discord.ButtonStyle.blurple, self.upload_scores_callback)
                self.add_button("View team composition", discord.ButtonStyle.grey, self.team_composition_callback, custom_id="team_comp")
            case SixMansState.POST_MATCH:
                self.add_button("End Game", discord.ButtonStyle.red, self.cancel_button_callback)

    async def update_view(self, embed=None):
        self.update_options()
        if self.message:
            await self.message.edit(embed=embed or self.generate_embed(), view=self)

    async def cancel_button_callback(self, _: discord.Interaction):
        await self.delete_lobby()
   
    async def choose_button_callback(self, interaction: discord.Interaction):
        match self.state:
            case SixMansState.CHOOSE_CAPTAIN_ONE | SixMansState.CHOOSE_CAPTAIN_TWO:
                users = [interaction.client.get_user(int(user_id)) for user_id in DB.column("SELECT UserID FROM SixManUsers WHERE PartyID = %s AND Team = 0", self.party.party_id)]
                reason = "join your team."
            case SixMansState.CHOOSE_1S_PLAYER:
                users = [interaction.client.get_user(int(user_id)) for user_id in DB.column("SELECT UserID FROM SixManUsers WHERE PartyID = %s AND Team = %s", self.party.party_id, DB.field("SELECT Team FROM SixManUsers WHERE UserID = %s AND PartyID = %s", interaction.user.id, self.party.party_id))]
                reason = "play your 1s match."
        view = UserDropdownView(self, message_interaction=interaction, users=users, amount=1 if self.state in [SixMansState.CHOOSE_CAPTAIN_ONE, SixMansState.CHOOSE_1S_PLAYER] else 2 if self.state == SixMansState.CHOOSE_CAPTAIN_TWO else 0, reason=reason)
        await interaction.response.send_message(view=view, ephemeral=True)
    
    async def break_out_button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.create_break_out_rooms()
        self.game = SixMansMatchType.ONE_V_ONE
        DB.execute("INSERT INTO SixManGames () VALUES ()")
        self.party.game_id = DB.field("SELECT LAST_INSERT_ID()")
        DB.execute("UPDATE SixManParty SET GameID = %s WHERE PartyID = %s", self.party.game_id, self.party.party_id)
        await self.update_view()
    
    async def surrender_button_callback(self, interaction: discord.Interaction):
        match_type = self.get_match_type()
        DB.execute(f"UPDATE SixManGames SET {match_type}_{'A' if interaction.user.id == self.party.captain_one.id else 'B'} = %s WHERE GameID = %s", -1, self.party.game_id)
        if self.party.calculate_winner() == 0:
            self.game = SixMansMatchType.THREE_V_THREE if self.game == SixMansMatchType.TWO_V_TWO else SixMansMatchType.TWO_V_TWO
            self.state = SixMansState.PLAYING
        else:
            self.state = SixMansState.POST_MATCH
        await self.update_view()
        return await interaction.response.send_message(f"You have surrendered the {match_type} match.", ephemeral=True)
        
    async def upload_scores_callback(self, interaction: discord.Interaction):
        match_type = self.get_match_type()
        await interaction.response.send_modal(ScoreUpload(self, match_type))
    
    async def finish_button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.state = SixMansState.SCORE_UPLOAD
        await self.update_view()
    
    async def team_composition_callback(self, interaction: discord.Interaction):
        team_one_players = self.party.get_players(1)
        team_two_players = self.party.get_players(2)
        team_one_str = [f"• **[{self.generate_flag_str(member)}]** {member.display_name}" if member else f"• {member}" for member in team_one_players]
        team_two_str = [f"• **[{self.generate_flag_str(member)}]** {member.display_name}" if member else f"• {member}" for member in team_two_players]
        embed: discord.Embed = self.bot.create_embed(f"ScuffBot Six Mans #{self.party.lobby_id}", "", None)
        embed.add_field(name="Team A", value="\n".join(team_one_str))
        embed.add_field(name="Team B", value="\n".join(team_two_str))
        embed.set_footer(text=f"Party {'N/A' if not self.party.party_id else self.party.party_id} | Game {'N/A' if not self.party.game_id else self.party.game_id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
           
class ScoreUpload(Modal):
    score_a = TextInput(label='Team A Score')
    score_b = TextInput(label='Team B Score')

    def __init__(self, ctx: SixMansPrompt, title: str) -> None:
        self.ctx = ctx
        super().__init__(title=title)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        match_type = self.ctx.get_match_type()

        if self.score_a.value == self.score_b.value:
            return await interaction.followup.send("The team's score cannot be identical. Please re-input your values.", ephemeral=True)
        elif (not self.score_a.value.isnumeric()) or (not self.score_b.value.isnumeric()):
            return await interaction.followup.send("One or more of your scores is not valid. Please ensure they are non-negative numbers.", ephemeral=True)
        else:
            self.ctx.party.reported_scores[interaction.user.id][match_type] = (int(self.score_a.value), int(self.score_b.value))

            # Check if both scores are present and compare
            team_a_reported_score = self.ctx.party.reported_scores[self.ctx.party.captain_one.id][match_type]
            team_b_reported_score = self.ctx.party.reported_scores[self.ctx.party.captain_two.id][match_type]

            if team_a_reported_score == team_b_reported_score:
                # Both scores set and equal
                DB.execute(f"UPDATE SixManGames SET {match_type}_A = %s, {match_type}_B = %s WHERE GameID = %s", team_a_reported_score[0], team_b_reported_score[1], self.ctx.party.game_id)
                match self.ctx.game:
                    case SixMansMatchType.ONE_V_ONE:
                        self.ctx.game = SixMansMatchType.TWO_V_TWO
                        self.ctx.state = SixMansState.PLAYING
                    case SixMansMatchType.TWO_V_TWO:
                        if self.ctx.party.calculate_winner() == 0:
                            self.ctx.game = SixMansMatchType.THREE_V_THREE
                            self.ctx.state = SixMansState.PLAYING
                        else:
                            self.ctx.state = SixMansState.POST_MATCH
                    case SixMansMatchType.THREE_V_THREE:
                        self.ctx.state = SixMansState.POST_MATCH
        await self.ctx.update_view()

class SixMans(commands.Cog):
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.queue = list()
        self.category = config["SIX_MAN"]["CATEGORY"]

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")

    async def check_queue(self):
        if len(self.queue) == PARTY_SIZE:
            party = self.queue[:PARTY_SIZE]
            del self.queue[:PARTY_SIZE]
            lobby_id, party_id = await self.create_party(party)
            await self.start(lobby_id, party_id)

    async def generate_lobby_id(self):
        highest_lobby_num = max([0] + (lobbies := DB.column("SELECT LobbyID FROM SixManParty WHERE LobbyID IS NOT NULL")))
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
        vc_perms = {lobby_role: PermissionOverwrite(speak=True, connect=True, view_channel=True), guild.default_role: PermissionOverwrite(view_channel=True, connect=False)}
        text_perms = {lobby_role: PermissionOverwrite(read_messages=True, send_messages=True), guild.default_role: PermissionOverwrite(read_messages=False)}
        
        # Create voice channel
        voice_channel = await guild.create_voice_channel(name=lobby_name, overwrites=vc_perms, category=self.bot.get_channel(self.category), reason=f"{lobby_name} created")
        
        # Create text channel
        text_channel = await guild.create_text_channel(name=f"six-mans-{lobby_id}", overwrites=text_perms, category=self.bot.get_channel(self.category), reason=f"{lobby_name} created")
        
        # Send preliminary starting message
        message = await text_channel.send(embed=self.bot.create_embed("SCUFFBOT SIX MANS", f"SCUFFBOT is creating the six mans lobby. This message will update once complete.", None))
        
        lobby_invite_link = str(await voice_channel.create_invite(reason=f"{lobby_name} created"))

        DB.execute("INSERT INTO SixManLobby (LobbyID, MessageID, VoiceChannelID, TextChannelID, RoleID) VALUES (%s, %s, %s, %s, %s)", lobby_id, message.id, voice_channel.id, text_channel.id, lobby_role.id)
        DB.execute("INSERT INTO SixManParty (LobbyID) VALUES (%s)", lobby_id)
        party_id = DB.field("SELECT LAST_INSERT_ID()")
        
        # Invite members
        for member in members:
            await member.add_roles(lobby_role, reason=f"{member} added to {lobby_name}")
            await member.send(embed=self.bot.create_embed("SCUFFBOT SIX MANS", f"You have been added into **{lobby_name}**.", None), view=View().add_item(discord.ui.Button(label="Join Six Mans",style=discord.ButtonStyle.link, url=lobby_invite_link)))
            DB.execute("INSERT INTO SixManUsers (PartyID, UserID) VALUES (%s, %s)", party_id, member.id)
        return (lobby_id, party_id)
    
    async def start(self, lobby_id: int, party_id: int):
        text_channel = self.bot.get_channel(int(DB.field("SELECT TextChannelID FROM SixManLobby WHERE LobbyID = %s", lobby_id)))
        message = await text_channel.fetch_message(int(DB.field("SELECT MessageID FROM SixManLobby WHERE LobbyID = %s", lobby_id)))
        view = SixMansPrompt(self.bot, party_id)
        view.message = message
        await view.update_view()
        
    @app_commands.command(name="q", description="Joins the six man queue.")
    @app_commands.guilds(Object(id=422983658257907732))
    async def queue(self, interaction: discord.Interaction):
        if interaction.user in self.queue:
            self.queue.remove(interaction.user)
            await interaction.response.send_message(embed=self.bot.create_embed("SCUFFBOT SIX MANS", f"You have left the six mans queue.", None), ephemeral=True)
        else:
            if str(interaction.user.id) in DB.column("SELECT A.UserID FROM SixManUsers A INNER JOIN SixManParty B WHERE A.PartyID = B.PartyID AND B.LobbyID IS NOT NULL"):
                await interaction.response.send_message(embed=self.bot.create_embed("SCUFFBOT SIX MANS", f"You are already in a six mans lobby. Failed to join queue.", None), ephemeral=True)
            else:
                self.queue.append(interaction.user)
                await interaction.response.send_message(embed=self.bot.create_embed("SCUFFBOT SIX MANS", f"You have joined the six mans queue. ({len(self.queue)}/{PARTY_SIZE})", None), ephemeral=True)
                await self.check_queue()

    @app_commands.command(name="leave", description="Leaves the six man queue.")
    @app_commands.guilds(Object(id=422983658257907732))
    async def leave(self, interaction: discord.Interaction):
        if not interaction.user in self.queue:
            await interaction.response.send_message(embed=self.bot.create_embed("SCUFFBOT SIX MANS", f"You are not in a queue. Type `/q` to join the queue.", None), ephemeral=True)
        else:
            self.queue.remove(interaction.user)
            await interaction.response.send_message(embed=self.bot.create_embed("SCUFFBOT SIX MANS", f"You have left the six mans queue.", None), ephemeral=True)
   
    @app_commands.command(name="status", description="Returns the number of people in the queue.")
    @app_commands.guilds(Object(id=422983658257907732))
    async def status(self, interaction: discord.Interaction):
        queue_len = len(self.queue)
        await interaction.response.send_message(embed=self.bot.create_embed("SCUFFBOT SIX MANS", f"There {'is' if queue_len == 1 else 'are'} currently {len(self.queue)} {'player' if queue_len == 1 else 'players'} in the queue.", None))

async def setup(bot):
    await bot.add_cog(SixMans(bot))


class UserDropdown(Select):
    def __init__(self, users: list[discord.Member], amount: int, reason: str):
        options = [discord.SelectOption(label=user.display_name, value=user.id) for user in users]
        super().__init__(placeholder=f"Choose {amount} {'member' if amount == 1 else 'members'} to {reason}", min_values=amount, max_values=amount, options=options)

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
        
        self.submit_button = discord.ui.Button(label="Submit", style=discord.ButtonStyle.green)
        self.submit_button.callback = self.submit_button_callback
        self.add_item(self.submit_button)

    async def submit_button_callback(self, interaction: discord.Interaction):
        match self.ctx.state:
            case SixMansState.CHOOSE_CAPTAIN_ONE:
                for user_id in self.user_dropdown.values:
                    DB.execute("UPDATE SixManUsers SET Team = 1 WHERE UserID = %s AND PartyID = %s", user_id, self.ctx.party.party_id)
                self.ctx.state = SixMansState.CHOOSE_CAPTAIN_TWO
            case SixMansState.CHOOSE_CAPTAIN_TWO:
                for user_id in self.user_dropdown.values:
                    DB.execute("UPDATE SixManUsers SET Team = 2 WHERE UserID = %s  AND PartyID = %s", user_id, self.ctx.party.party_id)
                # Add last player
                last_player_id = DB.field("SELECT UserID FROM SixManUsers WHERE PartyID = %s AND Team = 0", self.ctx.party.party_id)
                DB.execute("UPDATE SixManUsers SET Team = 1 WHERE UserID = %s", last_player_id)
                self.ctx.state = SixMansState.CHOOSE_1S_PLAYER
            case SixMansState.CHOOSE_1S_PLAYER:
                DB.execute("UPDATE SixManUsers SET isOnesPlayer = 1 WHERE UserID = %s AND PartyID = %s", self.user_dropdown.values[0], self.ctx.party.party_id)
                if len(DB.rows("SELECT UserID FROM SixManUsers WHERE PartyID = %s AND isOnesPlayer = 1", self.ctx.party.party_id)) == 2:
                    DB.execute("UPDATE SixManUsers SET isOnesPlayer = 0 WHERE PartyID = %s AND isOnesPlayer IS NULL", self.ctx.party.party_id)
                    self.ctx.state = SixMansState.PLAYING
        await self.message_interaction.edit_original_response(content=f"You have selected {', '.join([interaction.client.get_user(int(user_id)).mention for user_id in self.user_dropdown.values])} to {self.reason}", view=None)
        await self.ctx.update_view()

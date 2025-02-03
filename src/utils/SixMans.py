from enum import Enum
import random
from typing import Literal, Union

from datetime import datetime, timezone
from discord.ext import tasks
import discord
from src.lib.db import DB

PARTY_SIZE = 6
QUEUE_TIMEOUT = 60  # minutes
LOBBY_TIMEOUT = 5  # minutes


class SixMansState(Enum):
    PRE_LOBBY = 0
    CHOOSE_CAPTAIN_ONE = 1
    CHOOSE_CAPTAIN_TWO = 2
    CHOOSE_1S_PLAYER = 3
    PLAYING = 4
    SCORE_VALIDATION = 5
    POST_MATCH = 6


class SixMansMatchType(Enum):
    PRE_MATCH = 0
    ONE_V_ONE = 1
    TWO_V_TWO = 2
    THREE_V_THREE = 3


class SixMansParty():
    def __init__(self, bot: discord.Client, party_id: int) -> None:
        self.bot = bot
        self.game_id: Union[None, int] = None
        self.party_id = party_id
        self.lobby_id = DB.field(
            "SELECT LobbyID FROM SixManParty WHERE PartyID = %s", self.party_id)
        self.players = self.get_players()
        self.captain_one: Union[None, discord.Member] = None
        self.captain_two: Union[None, discord.Member] = None
        self.generate_captains()

        self.reported_scores = {self.captain_one.id: {"1v1": (None, None), "2v2": (None, None), "3v3": (
            None, None)}, self.captain_two.id: {"1v1": (None, None), "2v2": (None, None), "3v3": (None, None)}}

    async def get_details(self):
        return DB.row("SELECT * FROM SixManLobby WHERE LobbyID = %s", self.lobby_id)

    def get_players(self, team: Literal[None, 1, 2] = None):
        if team == None:
            return [self.bot.get_user(int(user_id)) for user_id in DB.column("SELECT UserID FROM SixManUsers WHERE PartyID = %s", self.party_id)]

        return [self.bot.get_user(int(user_id)) for user_id in DB.column("SELECT UserID FROM SixManUsers WHERE PartyID = %s AND Team = %s", self.party_id, 0 if team == None else team)]

    def generate_captains(self):
        players = self.get_players()
        self.captain_one = players.pop(random.randint(0, len(players)-1))
        self.captain_two = players.pop(random.randint(0, len(players)-1))
        DB.execute(
            "UPDATE SixManUsers SET Type = 1, Team = 1 WHERE UserID = %s", self.captain_one.id)
        DB.execute(
            "UPDATE SixManUsers SET Type = 2, Team = 2 WHERE UserID = %s", self.captain_two.id)

    def calculate_winner(self) -> Literal[0, 1, 2]:
        if self.game_id == None:
            return 0
        data = [0 if x is None else x for x in DB.row(
            "SELECT 1v1_A, 1v1_B, 2v2_A, 2v2_B, 3v3_A, 3v3_B FROM SixManGames WHERE GameID = %s", self.game_id).values()]

        team_a_wins = sum(data[i] > data[i + 1]
                          for i in range(0, len(data), 2))
        team_b_wins = sum(data[i + 1] > data[i]
                          for i in range(0, len(data), 2))

        match (team_a_wins >= 2, team_b_wins >= 2):
            case (True, False):
                return 1
            case (False, True):
                return 2
            case (False, False):
                return 0


class SixMansQueue():
    def __init__(self, queue_prompt):
        self.queue = list()
        self.queue_prompt = queue_prompt
        self.bot = queue_prompt.ctx.bot
        self.purge_queue.start()

    def add(self, player: discord.Member):
        self.queue.append(
            {"player": player, "join_time": datetime.now(timezone.utc)})

    def remove(self, player: discord.Member):
        self.queue = list(filter(lambda e: e["player"] != player, self.queue))

    def get_party(self):
        if len(self.queue) >= PARTY_SIZE:
            party = self.queue[:PARTY_SIZE]
            del self.queue[:PARTY_SIZE]
            return list(map(lambda e: e["player"], party))
        return []

    def __contains__(self, key):
        return key in list(map(lambda e: e["player"], self.queue))

    def __len__(self):
        return len(self.queue)

    @tasks.loop(minutes=1)
    async def purge_queue(self):
        for entry in self.queue:
            if (datetime.now(timezone.utc) - entry["join_time"]).seconds >= (QUEUE_TIMEOUT * 60):
                self.remove(entry["player"])
                await entry["player"].send(embed=self.bot.create_embed("SCUFFBOT SIX MANS", f"You have been removed from the Six Mans queue since a game could not be found in time.", None))
                await self.queue_prompt.update_view()

    @purge_queue.before_loop
    async def before_purge_queue(self):
        await self.bot.wait_until_ready()

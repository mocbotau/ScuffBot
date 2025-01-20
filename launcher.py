from src.lib.bot import SCUFFBOT
from dotenv import find_dotenv, load_dotenv
import argparse
import os

env_file = find_dotenv(".env.local")
load_dotenv(env_file)

with open(os.environ["BOT_TOKEN"], "r", encoding="utf-8") as f:
    bot_token = f.readline().strip()

parser = argparse.ArgumentParser(description='Runs ScuffBot.')
parser.add_argument('--dev', action='store_true', help='Enable development mode.')
args = parser.parse_args()

bot = SCUFFBOT(args.dev)
bot.run(bot_token)

# ScuffBot

This repo will deploy into Kubernetes through CI/CD.

## Running Locally

If you would like to run locally:

1. Copy [config.yaml](./config.yaml) to `config.yaml.local`, and adjust values as necessary. Alternatively, change `CONFIG_FILE` in [.env](./.env) to point to `config.yaml`.
2. Create a `.local-secrets` directory in the root of the project.
3. Populate the directory with the following files:
   | Filename | Description |
   |--------------------|------------------------------------|
   | `bot-token` | Token for Discord bot |
   | `db-password` | Default password for database |
   | `db-root-password` | Root password for the database |
4. Copy [/db/.env.template](./db/.env.template) to `db/.env`, and adjust values as necessary.
5. Run the bot with `docker compose up -d --build`.

If you have something to suggest, whether it is feedback or a bug report, put it in the thread below. As I acknowledge your feedback, I will update this list. This is what I have so far:

# Feedback

- [x] Implement a queue timeout, perhaps 45-60mins?
- [x] Notify the channel when a player has joined the queue
- [ ] Have request to spectate six mans matches
- [x] Wait for all 6 people to join call before starting otherwise cancel after 5 mins
- [ ] Incorporate personal stats page
- [x] Disable general text chat messaging
- [x] Change Team A/B to actual team names
- [ ] Add rematch button
- [x] Disable break out button after clicked
- [x] Ping the six mans lobby channel when the lobby is created
- [ ] Connect up the MMR system
- [ ] Send players back to the general six mans voice channel after the game has been ended
- [x] Convert score reporting to win/loss reporting
- [x] Add administrative commands to manipulate six man lobbies
  - Added `close` command

# Bugs

- [x] Users get kicked from queue even after finding a match
- [x] Captains are able to click select 1s players multiple times resulting in multiple 1s players in the party per team

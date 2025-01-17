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

## 6 Mans Bot

- 1hr timeout 60 mins
- Users would have to nominate winner

- both team capts randomly assigned
- 1st team captain one person
- 2nd team captain two people
- last person gets added to team 1

- bot wont proceed until both parties nominate the same score

- Commands
  !q - This command is used to join the ongoing queue or start your own queue for others to join.
  !leave - Allows you to leave the current queue.
  !status - Shows you all the current players that are in the queue.

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
4. Copy [/db/.env.template](./db/.env.template) to `db/.env`, and adjust values as necessary.
5. Run the bot with `docker compose up -d --build`.

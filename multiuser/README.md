# WARDOGS Squad Controller + Windows Agent

A separate multi-user edition. One Docker controller manages the Discord bot, while Windows agents send only their selected game status over outbound HTTPS. The standalone application at the repository root is unchanged.

The controller maintains **one shared Discord message containing one embed**. Ten players fit the default card layout; use compact templates for larger squads. The browser builder previews your real roster or up to 100 sample players, checks Discord's limits, and explicitly reports overflow. It never creates extra messages to split the roster.

## Get started

1. Follow [Controller deployment](docs/DEPLOYMENT.md): copy `.env.example` to `.env`, set the bot token, channel, and admin secret, connect your existing HTTPS proxy network, then run `docker compose up -d --build` from this directory.
2. Open your controller URL and sign in with the admin secret. Generate a username-bound, single-use PIN for each player.
3. Download `WARDOGS-Agent-Setup.exe` from the **multiuser-agent-installer** artifact on a successful **Multi-user controller and agent** GitHub Actions run. Install on Windows x64. Python and OCR are bundled; players need no Discord credentials.
4. Enter the controller URL, username, and PIN in the agent. Choose what to share and enable reporting. See [Agent guide](docs/AGENT.md).
5. Use **Embed builder** to customize every supported rich-embed section, upload images, and preview your squad. Click **Publish layout** when ready. See [Builder guide](docs/EMBED_BUILDER.md).

## What's included

- Docker controller, persistent SQLite database and private image storage.
- PIN pairing, per-agent credentials, enable/disable and revocation controls.
- Windows agent with tray controls, startup preference, monitor selection, OCR calibration, and privacy switches.
- Cards, compact and minimal presets; editable title, links, description, color, timestamp, author, footer, player templates, and ordered custom fields.
- Main image, thumbnail, author icon and footer icon from authenticated uploads or HTTPS URLs.
- Coalesced message edits, reconnection, stale-player handling and saved message identity across restarts.

Agents open no inbound ports. The provided Compose file publishes no host ports; the controller is reachable through your existing reverse proxy on its Docker network. Use one controller instance / one worker per data volume.

This displays the current status and scores exposed by the game's OCR integration, not historical statistics or a game API. Screenshots stay on the player's computer. Game updates, screen scaling and occlusion can affect OCR. The Windows installer is unsigned.

[Build and verification](docs/BUILDING.md) · [Third-party notices](docs/THIRD_PARTY.md)

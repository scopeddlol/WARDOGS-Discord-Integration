# Controller deployment

## Discord and secrets

Create a Discord application and bot in the [Developer Portal](https://discord.com/developers/applications). Invite it to your server with the `bot` scope and allow **View Channel**, **Send Messages**, **Embed Links**, and **Attach Files** in the chosen text channel. No privileged gateway intents are needed: the controller uses the REST API. Copy the channel ID using Discord's developer mode.

From `multiuser/`, copy `.env.example` to `.env`. Set:

- `CONTROLLER_ADMIN_TOKEN`: a unique random secret of at least 32 characters. For example, generate it locally with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
- `DISCORD_BOT_TOKEN`: your bot token, kept only on the controller.
- `DISCORD_CHANNEL_ID`: the text channel's numeric ID.
- `PROXY_NETWORK`: the name of your existing reverse proxy's external Docker network (default `proxy`).

Keep `.env` private. It is excluded from Git and the Docker build context. Do not send the admin key or bot token to players. A player receives only the URL, username and temporary PIN. Rotating the admin secret invalidates pending PINs but preserves already paired credentials.

## HTTPS reverse proxy

Connect your proxy to the same Docker network as this Compose service. If the network does not already exist, create it and attach your proxy. Start the controller:

```sh
docker compose up -d --build
docker compose logs -f controller
```

The upstream is `http://controller:8080`. Only the existing proxy needs public HTTPS access; the controller Compose file has no `ports` mapping. Do not expose the upstream directly to the internet. Use a valid TLS certificate; agents validate it and reject non-HTTPS remote URLs and redirects.

A Caddy site on the same Docker network:

```caddyfile
wardogs.example.com {
    reverse_proxy controller:8080
}
```

For an existing Nginx TLS virtual host, add:

```nginx
location / {
    client_max_body_size 8m;
    proxy_pass http://controller:8080;
    proxy_set_header Host $host;
    proxy_read_timeout 30s;
}
```

A dedicated hostname is simplest. Subpaths also work if the proxy strips the prefix, and the browser URL ends with `/` (for example `https://example.com/wardogs/`). Forward the Authorization header unchanged. The controller does not trust forwarded IP headers; pairing throttles therefore apply to the proxy address as a group. Set a request-body timeout and sensible rate limits on your public proxy as well.

Visit the HTTPS URL and sign in with the admin key. The key is kept only in tab memory. Reloading or signing out requires it again. This is one host-admin account; there are no public signups. `/healthz` is unauthenticated and returns only service health.

## Pairing and reporting

Generate a PIN for each player's chosen username in **Players**. Names are normalized and case-insensitive for identity; duplicate names refer to the same player UUID. PINs expire after ten minutes, work once, and lock after five incorrect attempts. Generating a new PIN replaces the previous pending PIN. Redeeming it rotates that player's credential and stops an old installation from reporting.

**Disable** blocks reporting until re-enabled; the player then presses Start again. **Revoke** destroys the credential and pending PIN; generate a new PIN to restore access. Stopping the agent posts a paused state. A disconnected agent is marked stale after 90 seconds by default and its old scores are cleared. The controller supports up to 100 registered players; the embed's actual capacity depends on templates and Discord's limits.

The first publish creates the board. Later updates edit its saved message ID, including after restart. A deleted Discord message is recreated. Changes are combined at 15-second intervals by default; Discord rate-limit retries are respected. Initial creation uses a stable nonce to avoid duplicate creates during short response-loss retries. This is not a distributed exactly-once delivery system: run only one instance, and verify the channel after restoring old backups or prolonged ambiguous network failures. Changing the target channel creates a board in the new channel; remove the old one manually if desired.

## Persistence and operations

The named `controller-data` volume contains the database and images under `/data`. Back up the complete volume while the controller is stopped so SQLite and attachments stay consistent. Preserve it during updates (`docker compose up -d --build`); `docker compose down -v` would delete it. The message ID, layout, credentials and player roster survive a normal container restart.

The image runs as UID 10001 with a read-only root filesystem. If replacing the named volume with a bind mount, make `/data` writable by that UID. Do not start multiple replicas or Uvicorn workers: there is deliberately one publisher.

`PUBLISH_INTERVAL_SECONDS` defaults to 15 (minimum 5). `AGENT_TIMEOUT_SECONDS` defaults to 90 (minimum 45). Agents heartbeat every 15 seconds. `DISCORD_DRY_RUN=1` renders and exercises the API without sending to Discord; use it only for testing. Remove it and restart for real delivery. Errors appear in the admin header; check channel permissions, credentials and network connectivity first.

Images are private on the controller; only authenticated admins can retrieve them. Publishing makes attached images visible to the Discord channel. Total stored uploads are capped at 256 MB; there is no automatic asset deletion. Remove unused files only while stopped and after checking the saved layout and taking a backup. Agents never upload screenshots.

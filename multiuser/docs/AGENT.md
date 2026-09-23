# Windows agent

Install `WARDOGS-Agent-Setup.exe` on Windows x64. The installer bundles Python, the desktop interface and Tesseract OCR; no terminal setup is needed. It uses a separate application directory, startup entry and settings file from WARDOGS Discord (the standalone edition). Builds are currently unsigned.

## Connect

Ask the controller host for its HTTPS URL, your username, and an eight-digit PIN. Enter them on the **Controller** page and pair within ten minutes. A PIN works once. Pairing saves a per-agent credential protected with Windows DPAPI for your Windows account. Your Discord account, bot token and controller admin key are not needed.

Choose what to broadcast on **Share**, select your monitor under **Capture**, then enable reporting. The tray menu can start/stop reporting and reopen the window. Configure startup if desired. Closing the window keeps the tray agent available; use Quit to exit. While reporting, stop first before changing settings. A paired username and controller are locked to the credential; use Forget pairing to change them, then pair again. Forgetting locally does not revoke the old credential on the controller; the host can do that.

## Capture and privacy

The agent reads the game's visible screen locally. Run WARDOGS in the foreground on the selected monitor. It pauses detection when another application has focus, avoiding scans of unrelated windows. Use the local screenshot/OCR test and calibration controls if detection misses your HUD or server browser at your resolution.

Choose whether to share server, server ID, team, scores, queue and not-in-game status. Filtering happens before network transmission. Screenshots are never sent to the controller. Turning off one field cannot be overridden by the web embed template. The controller still needs your username and a basic connection/activity state to manage the roster.

The detector debounces readings; scores need repeated agreement. Updates are sent about every 15 seconds and combined by the controller. Background/paused/disconnected states clear stale public score details. OCR depends on the supported game UI; this does not collect kills, historical analytics or statistics absent from the original OCR integration.

## Connectivity and settings

The agent makes outbound HTTPS requests to the configured URL. No port forwarding, listener, or inbound firewall rule is required. Remote HTTP URLs, certificate errors and redirects are rejected. Enter the final HTTPS URL, including any path prefix. HTTP is accepted only on loopback for development.

Network failures retry with backoff. If the host disables or revokes access, reporting stops with a visible message. After re-enabling, press Start; after revocation, get a new PIN and pair again. Starting a second reporting session replaces the first to prevent two machines from overwriting the same player.

Settings and logs are under `%LOCALAPPDATA%\WARDOGS Agent`. The separate Windows startup value is `WARDOGSAgent`. Uninstall preserves your settings for a later reinstall. Do not copy a credential file to another Windows account: DPAPI will not decrypt it there.

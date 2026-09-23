# Windows agent

Install `WARDOGS-Agent-Setup.exe` on Windows x64. The installer bundles Python, the desktop interface and Tesseract OCR; no terminal setup is needed. It uses a separate application directory, startup entry and settings file from WARDOGS Discord (the standalone edition). Builds are currently unsigned.

## Connect

Ask the controller host for its HTTPS URL, your username, and an eight-digit PIN. Enter them on the **Controller** page and pair within ten minutes. A PIN works once. Pairing saves a per-agent credential protected with Windows DPAPI for your Windows account. Your Discord account, bot token and controller admin key are not needed.

Choose what to broadcast on **Share**, select your monitor under **Capture**, then choose **Enable reporting**. The tray menu can enable/disable reporting and reopen the window. By default, enabling waits for the WARDOGS process and starts OCR/reporting when it opens; closing the game stops OCR and reports you offline. Clear **Start reporting when WARDOGS opens** to start immediately instead. For a new agent, **Open the agent when I sign in to Windows** is checked by default so game detection also works after reboot; disable this option if you prefer to open the agent yourself. Disabling reporting removes its Windows startup entry. Closing the window keeps the tray agent available; use Quit to exit. While OCR is active, disable reporting before changing settings. Disabling stops the OCR worker and network heartbeat; only the lightweight tray interface remains to let you re-enable it. A paired username and controller are locked to the credential; use Forget pairing to change them, then pair again. Forgetting locally does not revoke the old credential on the controller; the host can do that.

## Capture and privacy

The agent reads the game's visible screen locally. Run WARDOGS in the foreground on the selected monitor. It pauses detection when another application has focus, avoiding scans of unrelated windows. Use the local screenshot/OCR test and calibration controls if detection misses your HUD or server browser at your resolution.

Choose whether to share server, server ID, team, scores, queue and not-in-game status. Filtering happens before network transmission. Screenshots are never sent to the controller. Turning off one field cannot be overridden by the web embed template. The controller still needs your username and a basic connection/activity state to manage the roster.

The detector debounces readings; scores need repeated agreement. Updates are sent about every 15 seconds and combined by the controller. Closing the game or disabling reporting sends an explicit offline state and clears stale public score details. A network loss is shown as disconnected after the controller timeout. OCR depends on the supported game UI; this does not collect kills, historical analytics or statistics absent from the original OCR integration.

## Connectivity and settings

The agent makes outbound HTTPS requests to the configured URL. No port forwarding, listener, or inbound firewall rule is required. Remote HTTP URLs, certificate errors and redirects are rejected. Enter the final HTTPS URL, including any path prefix. HTTP is accepted only on loopback for development.

Network failures retry with backoff. If the host disables or revokes access, reporting stops with a visible message. After host re-enabling, enable reporting again; after revocation, get a new PIN and pair again. Starting a second reporting session replaces the first to prevent two machines from overwriting the same player.

Settings and logs are under `%LOCALAPPDATA%\WARDOGS Agent`. The separate Windows startup value is `WARDOGSAgent`. Uninstall preserves your settings for a later reinstall. Do not copy a credential file to another Windows account: DPAPI will not decrypt it there.

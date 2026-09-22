# First-time setup

## 1. Create your Discord bot

1. Visit the [Discord Developer Portal](https://discord.com/developers/applications).
2. Choose **New Application**, name it, and open **Bot**.
3. Choose **Reset Token** and copy the token into the app's **Bot token** field.
   The token is the bot's password. Keep it private. No privileged intents are needed.
4. In the app, click **Invite bot to server**. It opens a Discord invite requesting only
   **View Channels**, **Send Messages**, and **Embed Links**.
5. Select your server and authorize the bot. You need permission to add bots to that server.
   Alternatively, use the Developer Portal OAuth2 URL Generator with the `bot` scope and those
   same three permissions.

## 2. Choose a channel

Use a regular text channel, such as `#wardogs-status`. Check its permission overrides allow
those three permissions for your bot. The bot does not need Administrator, Manage Channels,
Manage Messages, or access to the rest of the server.

In Discord, open **User Settings → Advanced → Developer Mode**. Right-click your chosen channel
and select **Copy Channel ID**. Paste that into the app, enter your display name, and click
**Check connection**. This checks the token and channel visibility without posting a message.
It cannot prove send/embed permissions; if the first broadcast fails, Activity shows the problem.

Click **Save settings**. Your token is encrypted with Windows DPAPI for your Windows account;
other ordinary accounts cannot decrypt the saved token. Programs running as you can still access
it, so do not share tokens or the settings folder.

## 3. Decide what to broadcast

Open **Broadcast** and use the checkboxes. Server ID is only included if server details are on.
Queue position can be shared without revealing a server. Disabling a field removes it from the
next outgoing update; it does not edit history while broadcasting is stopped.
With server or queue details disabled, the message uses generic activity text. With not-in-game
status disabled, it uses a neutral waiting message when the game closes.

Click **Start broadcasting**. Start saves your settings first. To change them, click **Stop**,
wait for the current operation to finish, make changes, and Start again.

**Stop leaves the existing message intact.** Delete it in Discord if you want it gone. The app
will create a new status message the next time it broadcasts. Stop and Quit do not send an
extra farewell message. An HTTP request already in flight may finish before Stop completes.

## 4. Check game capture

In **Capture**, choose the display running WARDOGS. After joining a match, briefly open the
pause menu to expose `CURRENT SERVER` and `SERVER ID`.
For faction detection, set the game's **Settings → Interface → Faction → Always On**.

If details are missed:

1. Stop broadcasting and open **Adjust capture boxes**.
2. Click **Capture in 5 seconds** and switch to the game with the pause menu visible.
3. Select **Server / queue text** and drag a box covering the relevant text.
4. Capture again during gameplay and adjust the **Faction icon** and **Scoreboard** boxes.
   The scoreboard box should cover all three equal-width team panels.
5. Click **Done**, then **Save settings**. Use **Read screen in 5 seconds** to verify locally.

Screenshots stay in memory. The automatic broadcaster only scans when the actual game client
is in the foreground, so switching to Discord or another app pauses screen reading. The last
status stays visible until another reading or game closure updates it. OCR is not perfect:
UI scale, display resolution, hidden HUD elements, and future game updates can affect readings.

## Running in the background

Close the window to keep the app in the Windows tray. Double-click its icon to reopen it;
right-click for Start, Stop, or Quit. The two startup options are independent: you can open the
app at sign-in without automatically broadcasting, or auto-broadcast only on manual launch.
Both are off by default. A second shortcut click opens the existing app.

## Troubleshooting

- **401 / token rejected:** reset the token in Discord, Stop, paste the new token, and Save.
- **403 / missing permissions:** allow View Channel, Send Messages, and Embed Links in the
  selected channel's permission overrides. Check the bot is actually in that server.
- **Channel not found:** copy the ID of a regular server text channel, not a server, category,
  forum, thread, or voice channel.
- **OCR engine missing:** reinstall with the complete Windows installer.
- **Wrong or missing readings:** use Capture calibration; briefly open the pause menu.
- **Broadcast needs attention:** open **Activity** for the error. Retries respect Discord rate
  limits. Other API failures back off for 30 seconds.
- **Cannot load saved settings:** the file may be corrupt or belong to another Windows account.
  Re-enter the settings in the app and save; it does not silently erase the file on startup.

## Updates and uninstall

Run the newer installer to upgrade. It retains your per-user settings and encrypted token.
Quit the app from its tray menu before upgrading or uninstalling.

Uninstall from **Windows Settings → Apps → Installed apps → WARDOGS Discord**. This removes the
application, shortcuts, and sign-in entry. Settings are deliberately retained for reinstall.
To remove all saved data, after uninstall delete `%LOCALAPPDATA%\WARDOGS Discord` in Explorer.
That folder contains `settings.json`, `last_status.json`, and rotated diagnostic logs. Logs may
contain server details; review them before sharing. If you exposed a token, reset it in Discord.

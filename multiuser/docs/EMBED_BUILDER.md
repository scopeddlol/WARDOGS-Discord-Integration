# Embed builder

Open **Embed builder** after signing in. Choose **Player cards**, **Compact roster**, or **Minimal**, then customize the draft. Preview updates as you type. **Publish layout** saves the draft and queues an edit of the shared message; **Discard unsaved changes** restores the last saved layout. Changing preview population never creates agents or publishes fake data.

## Editable sections

- Title (optional), title HTTPS link, description, accent color, timestamp visibility.
- Player name and stats templates, ordering, maximum players, disconnected-player visibility, and inline card columns.
- Main image and thumbnail, supplied by upload or HTTPS URL.
- Author name, HTTPS link and icon; footer text and icon.
- Up to 20 custom fields with editable name, text, inline setting, order, and position before/after the roster.

Discord controls the bot identity, client rendering, image dimensions, embed type and generated proxy URLs; these are not writable rich-embed fields. The timestamp is the board's latest publication time. To hide author/footer/image sections, clear their text or image reference. Author/footer icons require their corresponding text.

Use placeholder buttons to insert variables. Quick-stat rows can be dragged or moved with arrows, and checked to include a stat. These rows rebuild the standard player template; use the text editor for custom prose or additional variables.

Squad text and custom fields accept `{total}`, `{online}`, `{playing}`, `{updated}`. Player templates accept `{username}`, `{icon}`, `{status}`, `{activity}`, `{team}`, `{scores}`, `{connection}`, `{updated}`, `{server}`, `{server_id}`, `{queue_position}`, `{queue_total}`, `{lonestar_score}`, `{valkyra_score}`, and `{manticore_score}`. Use `{{` and `}}` for literal braces. Only named placeholders are allowed; expressions and Python formatting are rejected. Hidden agent data remains unavailable to templates.

Example player stats:

```text
{activity} · {server}
Team: {team}
Lonestar {lonestar_score} | Valkyra {valkyra_score} | Manticore {manticore_score}
{connection} · last seen {updated}
```

`{status}` is the combined readable status. Individual server/queue variables are extracted from the privacy-filtered status; unsupported or unshared values are empty. Blank lines are removed, but literal labels remain, so choose templates suited to the data your squad shares.

## Images and previews

Upload PNG, JPEG, GIF or WebP, or enter an HTTPS image URL. Each upload is limited to 8 MiB and 16 million pixels; the distinct uploaded files referenced by one embed must total no more than 8 MiB. The same image reused in several sections is attached once. Uploaded references are content-addressed and remain available across restarts. SVG and arbitrary attachments are not accepted. External images must be accessible to Discord; the controller does not download them. External preview images are loaded by your browser with no referrer.

Choose **Sample players** and set 0–100, or **Live roster**. The preview and publisher use the same server-side embed payload and limits. The browser approximates Discord's appearance and supports line breaks, bold and inline code; other Markdown and responsive columns may look different in Discord. Images, text, custom fields and the character budget are visible before saving.

## One message has finite capacity

Discord currently limits rich embeds to 25 fields and 6,000 combined text characters, with additional per-field limits, including a 4,096-character description. See [Discord's message documentation](https://docs.discord.com/developers/resources/message#embed-object).

This builder reserves space for an explicit overflow notice, accepts up to 5,500 characters of fixed content, clips expanded field text when needed, and reports every omitted player. Cards normally allow 24 players minus custom fields. Compact layouts fit more players by using the description; concise templates matter more than the number of columns. Ten players fit the default full-stat layout. Arbitrarily many players with arbitrarily long stats cannot fit in one embed.

The budget meter, shown/total counts and warnings explain the result. Increase the player limit, shorten templates, reduce custom fields, or switch to Compact. The complete registered roster remains available in **Players**. No additional Discord messages are created to handle overflow.

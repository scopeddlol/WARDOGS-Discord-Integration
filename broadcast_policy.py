"""Apply broadcast preferences at the outbound boundary, including old saved state."""
import re


def filter_status(text, scores, settings, offline_text):
    team = None
    for faction in ("Lonestar", "Valkyra", "Manticore"):
        if text.startswith(faction + " · "):
            team, text = faction, text[len(faction) + 3:]
            break
    if text == offline_text:
        return (text if settings.offline else "Offline"), None
    if text.startswith("Queued"):
        if not settings.queue:
            return "WARDOGS is running", None
        if not settings.server:
            match = re.search(r"position \d+ of \d+", text)
            return "Queued" + (f" ({match[0]})" if match else ""), None
        if not settings.server_id:
            text = re.sub(r"ID [\d -]+, ", "", text)
        return text, None
    if not settings.server:
        text = "In a match"
    elif not settings.server_id:
        text = re.sub(r"\s*· ID [\d -]+$", "", text)
    if settings.team and team:
        text = f"{team} · {text}"
    return text, scores if settings.scores else None

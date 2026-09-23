"""Isolated snapshot of the standalone OCR detector. No Discord/network code.

Copied from the standalone detector at 448eb24; changes here do not affect it.
"""
import colorsys
import logging
import math
import os
import re
import sys
import mss
import psutil
import pytesseract
from PIL import Image, ImageOps

log = logging.getLogger('wardogs-agent')
GAME_PROCESS_SUBSTRING = 'wardogsclient'
DISPLAY_NAME = 'Player'
CAPTURE_REGION = '0,0.65,1,1'
TEAM_ICON_REGION = '0.960,0.925,0.990,0.965'
SCORE_REGION = '0.0169,0.9139,0.1497,0.9514'
MONITOR_INDEX = 1
DESKTOP_SETTINGS = None
_warned_bad_monitor = False


def configure(settings, ocr):
    global DESKTOP_SETTINGS, DISPLAY_NAME, NOT_IN_GAME, MONITOR_INDEX
    global CAPTURE_REGION, TEAM_ICON_REGION, SCORE_REGION
    DESKTOP_SETTINGS = settings
    DISPLAY_NAME = settings.username
    NOT_IN_GAME = DISPLAY_NAME + ' is not in a game'
    MONITOR_INDEX = settings.monitor
    CAPTURE_REGION, TEAM_ICON_REGION, SCORE_REGION = settings.capture_region, settings.team_region, settings.score_region
    pytesseract.pytesseract.tesseract_cmd = str(ocr)

NAME_RE = re.compile(r"CURRENT\s*SERVER[:.\s]*(.+)", re.IGNORECASE)
# [I1l] tolerates "ID" getting OCR'd as "1D" (seen in practice), same idea
# as the [0-9OolI] digit class below tolerating O/0 and l/I/1 mixups. The
# dash is optional - most servers show "NNN-NNN" but some show a plain
# 6-digit "NNNNNN" with no separator at all (seen in practice too).
ID_RE = re.compile(r"SERVER\s*[I1l]D[^0-9OolI]*([0-9OolI]{3}\s*-?\s*[0-9OolI]{3})", re.IGNORECASE)
REGION_RE = re.compile(r"\(([^)|#]+)\)?")
NUM_RE = re.compile(r"#\s*(\d+)")
# Markers for "not actually in a match": the "EARLY ACCESS" watermark on the
# main menu / server browser (version number deliberately excluded, so this
# keeps matching across game updates), and the "PRESS ANY BUTTON TO START"
# splash screen shown before the main menu. Anchored on "ANY BUTTON TO
# START" rather than including "PRESS" - that busy photo background makes
# Tesseract's PSM 6 fallback (see capture_and_parse) merge "PRESS" with
# adjacent image noise in practice, while the rest stays intact.
MENU_RE = re.compile(r"EARLY\s*ACCESS|ANY\s*BUTTON\s*TO\s*START", re.IGNORECASE)
# "SERVER BROWSER" shows up as the main menu button's subtitle AND as the
# browser list screen's own page header (with or without a queue active) -
# covering the whole menu/browsing flow on its own, so it doesn't need to
# be paired with "DEPLOY" (which isn't safe alone - many shooters show a
# "REDEPLOY" prompt mid-match - but was never the issue; dropping it fixed
# a bug where leaving a queue without joining left the status stuck on
# "Queued for..." forever, since the plain server list has no DEPLOY text).
SERVER_BROWSER_RE = re.compile(r"SERVER\s*BROWSER", re.IGNORECASE)
# The server-browser queue bar: "IN SERVER QUEUE... Position N of M",
# followed on the next line by the target server's name (region + number,
# no dashed ID there) and map. Capturing everything after "of M" lets
# region/num be pulled from just that line - not searched globally - so it
# can't accidentally match one of the many other server entries listed
# above it on the same screen.
QUEUE_RE = re.compile(r"SERVER\s*QUEUE.*?POSITION\s*(\d+)\s*OF\s*(\d+)(.*)", re.IGNORECASE | re.DOTALL)

NOT_IN_GAME = f"{DISPLAY_NAME} is not in a game"


def is_game_running() -> bool:
    needle = GAME_PROCESS_SUBSTRING.lower()
    for proc in psutil.process_iter(["name"]):
        name = (proc.info.get("name") or "").lower()
        if proc.pid != os.getpid() and needle in name:
            return True
    return False


def is_game_foreground():
    """Desktop mode never reads another app while WARDOGS is in the background."""
    if DESKTOP_SETTINGS is None or sys.platform != "win32":
        return True
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    try:
        return GAME_PROCESS_SUBSTRING.lower() in psutil.Process(pid.value).name().lower()
    except psutil.Error:
        return False


def parse_region(region_str: str):
    """Parses "left,top,right,bottom" (0-1 screen fractions). Raises
    ValueError with a readable message if it's malformed or nonsensical."""
    try:
        left, top, right, bottom = (float(x) for x in region_str.split(","))
    except ValueError:
        raise ValueError(f'"{region_str}" isn\'t four comma-separated numbers (left,top,right,bottom)')
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise ValueError(f'"{region_str}" needs 0 <= left < right <= 1 and 0 <= top < bottom <= 1')
    return left, top, right, bottom


_warned_bad_monitor = False


class CaptureInterrupted(Exception):
    """The game lost focus while a multi-region reading was in progress."""


def grab_region(region_str: str = CAPTURE_REGION, require_foreground=False) -> Image.Image:
    global _warned_bad_monitor
    left_f, top_f, right_f, bottom_f = parse_region(region_str)
    with mss.MSS() as sct:
        index = MONITOR_INDEX
        if not 1 <= index < len(sct.monitors):
            if not _warned_bad_monitor:
                log.warning(
                    "MONITOR_INDEX=%d doesn't exist (this machine has monitors 1-%d) - falling back to monitor 1.",
                    index, len(sct.monitors) - 1,
                )
                _warned_bad_monitor = True
            index = 1
        mon = sct.monitors[index]
        w, h = mon["width"], mon["height"]
        box = {
            "left": mon["left"] + int(w * left_f),
            "top": mon["top"] + int(h * top_f),
            "width": int(w * (right_f - left_f)),
            "height": int(h * (bottom_f - top_f)),
        }
        if require_foreground and not is_game_foreground():
            raise CaptureInterrupted()
        shot = sct.grab(box)
        if require_foreground and not is_game_foreground():
            raise CaptureInterrupted()
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def preprocess(img: Image.Image) -> Image.Image:
    # No upscaling here: on this high-res capture it roughly quadrupled the
    # pixels Tesseract has to process (a large chunk of per-poll CPU time),
    # and a direct comparison found it detected LESS text, not more - so it
    # was pure overhead with no accuracy benefit on a display this sharp.
    # Only reintroduce upscaling if real gameplay testing shows misreads on
    # a lower-resolution display.
    img = img.convert("L")
    return ImageOps.autocontrast(img)


# Reference hues (degrees) for each faction's icon color, from the
# "SELECT FACTION" screen and a live sample of the in-HUD icon (Lonestar
# measured at RGB(80,228,255) -> hue ~189). Valkyra/Manticore are educated
# guesses from their icon colors (red/green) - not yet confirmed against a
# live sample, since detect_team was built while on the Lonestar team.
TEAM_HUE_DEGREES = {"Lonestar": 189, "Valkyra": 0, "Manticore": 120}
# Actual faction logos from the official Wardogs Discord (guild
# 1464219389913071646: "blue"/"red"/"green"), re-uploaded into Milk Cult -
# bots can only render custom emoji from guilds they're a member of.
TEAM_EMOJIS = {
    "Lonestar": "🔵",
    "Valkyra": "🔴",
    "Manticore": "🟢",
}


def detect_team(img: Image.Image):
    """Samples the small team-faction icon in the bottom-right HUD corner
    and classifies its color. Returns "Lonestar"/"Valkyra"/"Manticore", or
    None if no confidently-colored icon is found there (HUD not showing,
    icon occluded, wrong region for this resolution, etc)."""
    rgb_img = img.convert("RGB")
    pixels = list(rgb_img.getdata())

    # Circular mean of hue, weighted by how "colorful" each pixel is
    # (saturation * value), so washed-out background pixels barely count
    # and the icon's own color dominates the average. Threshold of 0.35 -
    # a real capture with a bright blue-ish sky visible around the icon
    # had background pixels topping out around 0.20 (still "colorful"
    # enough to swamp the old 0.15 threshold and skew the whole average
    # toward blue, misreading a red Valkyra icon as Lonestar), while the
    # icon's own pixels measured 0.41-0.68 on the same capture - a wide,
    # safe margin above 0.35.
    sin_sum = cos_sum = weight_sum = 0.0
    colorful_count = 0
    for r, g, b in pixels:
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        weight = s * v
        if weight < 0.35:  # skip near-black/gray/background pixels
            continue
        colorful_count += 1
        angle = h * 2 * math.pi
        sin_sum += weight * math.sin(angle)
        cos_sum += weight * math.cos(angle)
        weight_sum += weight

    # Require a minimum number of confidently-colored pixels rather than a
    # percentage of the whole box - icon shapes vary a lot (a blocky square
    # fills more of the box than a thin chevron), so a fixed count is more
    # robust across factions than a proportion (a proportion threshold that
    # worked for Lonestar's filled-square icon wrongly discarded Valkyra's
    # thinner chevron as "not enough signal" even though its color was
    # completely unambiguous - seen in practice).
    if colorful_count < 40 or weight_sum <= 0:
        return None

    mean_hue_deg = math.degrees(math.atan2(sin_sum, cos_sum)) % 360

    def circular_distance(a, b):
        d = abs(a - b) % 360
        return min(d, 360 - d)

    return min(TEAM_HUE_DEGREES, key=lambda team: circular_distance(mean_hue_deg, TEAM_HUE_DEGREES[team]))


SCORE_TEAMS = ("Lonestar", "Valkyra", "Manticore")  # left-to-right order on the scoreboard (blue, red, green)
# Share of each team panel (from its left edge) that holds the big digits;
# the rest is the person icon + team-size number, which must not be read.
SCORE_DIGITS_WIDTH_FRACTION = 0.74
SCORE_DIGITS_MIN_HEIGHT_PX = 60  # upscale smaller crops (lower-res displays) up to about this tall


def read_scores(img: Image.Image):
    """Reads the three big team scores from a SCORE_REGION capture. Returns
    (lonestar, valkyra, manticore) as ints, or None unless all three panels
    read as exactly three digits (the HUD always shows 001/000/095-style
    padded numbers) - that strictness is what keeps a non-HUD screen (menus,
    loading) from producing phantom scores."""
    third = img.width / 3
    scores = []
    for i in range(3):
        left = round(i * third)
        cell = img.crop((left, 0, left + round(third * SCORE_DIGITS_WIDTH_FRACTION), img.height))
        if cell.height < SCORE_DIGITS_MIN_HEIGHT_PX:
            factor = -(-SCORE_DIGITS_MIN_HEIGHT_PX // cell.height)  # ceil
            cell = cell.resize((cell.width * factor, cell.height * factor), Image.LANCZOS)
        cell = ImageOps.autocontrast(cell.convert("L"))
        text = pytesseract.image_to_string(cell, config="--psm 7 -c tessedit_char_whitelist=0123456789", timeout=10).strip()
        if not re.fullmatch(r"\d{3}", text):
            return None
        scores.append(int(text))  # int() drops the leading zeros
    return tuple(scores)


def parse_server(text: str):
    """Returns the formatted status, or None if the OCR text doesn't contain
    a complete reading (region, number, AND server id). Requiring all three
    avoids treating a partial/flaky OCR pass (e.g. one that misses the
    SERVER ID line) as a genuinely different status."""
    name_match = NAME_RE.search(text)
    if not name_match:
        return None
    full_name = name_match.group(1).strip()

    region_match = REGION_RE.search(full_name)
    num_match = NUM_RE.search(full_name)
    id_match = ID_RE.search(text)
    if not (region_match and num_match and id_match):
        return None
    region = region_match.group(1).strip()
    num = num_match.group(1).strip()

    fixed = id_match.group(1).translate(str.maketrans("OolI", "0011"))
    server_id = re.sub(r"\s*-\s*", "-", fixed)

    return f"{region} #{num} \u00b7 ID {server_id}"


def parse_queue(text: str):
    """Returns a "queued for server X, position N of M" status, or None if
    no queue bar is showing. Deliberately excludes the queue's countdown
    timer (it ticks every second, which would turn into a spurious status
    "change" - and therefore a Discord update - on nearly every poll)."""
    m = QUEUE_RE.search(text)
    if not m:
        return None
    position, total, tail = m.group(1), m.group(2), m.group(3)

    region_match = REGION_RE.search(tail)
    num_match = NUM_RE.search(tail)
    if region_match and num_match:
        region = region_match.group(1).strip()
        num = num_match.group(1).strip()
        return f"Queued for {region} #{num} (position {position} of {total})"

    # The queue bar doesn't always repeat the target server's name/number
    # right after "Position N of M" - seen in practice, the layout varies
    # (e.g. a countdown timer or "SERVER ID" line can sit there instead).
    # Fall back to the server ID: it's unambiguous (only ever one in the
    # captured text) even without the friendlier region/# label.
    id_match = ID_RE.search(text)
    if id_match:
        fixed = id_match.group(1).translate(str.maketrans("OolI", "0011"))
        server_id = re.sub(r"\s*-\s*", "-", fixed)
        return f"Queued (ID {server_id}, position {position} of {total})"

    return f"Queued (position {position} of {total})"


def determine_status(text: str):
    """Returns a server status, a queue status, NOT_IN_GAME, or None
    (ambiguous - e.g. actively playing with the pause menu closed, where
    none of the above are visible; leave whatever status is already
    showing alone rather than guessing)."""
    status = parse_server(text)
    if status:
        return status
    queue_status = parse_queue(text)
    if queue_status:
        return queue_status
    if MENU_RE.search(text):
        return NOT_IN_GAME
    if SERVER_BROWSER_RE.search(text):
        return NOT_IN_GAME
    return None




def capture_and_parse(require_foreground=False):
    """Returns (raw_ocr_text, server_status, team, scores). server_status is a
    server string / NOT_IN_GAME / a Queued string / None (see
    determine_status). team is sampled independently on every call (not
    gated on server_status succeeding) - the team icon lives in the
    regular gameplay HUD and is NOT visible while the pause menu is open
    (confirmed in practice), i.e. the exact moment server_status usually
    comes from, so the two can almost never be read together in the same
    poll. Callers combine the latest known value of each themselves.
    scores is the (lonestar, valkyra, manticore) HUD scoreboard tuple, or
    None if it isn't readable right now."""
    img = preprocess(grab_region(CAPTURE_REGION, require_foreground))
    text = pytesseract.image_to_string(img, timeout=10)
    if not text.strip():
        # Default page segmentation (--psm 3, full automatic layout
        # analysis) can give up entirely on a busy/noisy background - seen
        # on the "PRESS ANY BUTTON TO START" splash, which sits over a
        # detailed rendered scene. --psm 6 is slower but far more reliable
        # there, so it's only worth paying for as a fallback when the fast
        # pass found nothing at all.
        text = pytesseract.image_to_string(img, config="--psm 6", timeout=10)
    status = determine_status(text)
    team = detect_team(grab_region(TEAM_ICON_REGION, require_foreground)) if DESKTOP_SETTINGS is None or DESKTOP_SETTINGS.team else None
    scores = read_scores(grab_region(SCORE_REGION, require_foreground)) if DESKTOP_SETTINGS is None or DESKTOP_SETTINGS.scores else None
    return text, status, team, scores


def is_in_match(status) -> bool:
    """True for a real server status (not None / not-in-game / queued) - the
    only time a team or score is meaningful."""
    return status is not None and status != NOT_IN_GAME and not status.startswith("Queued")


def compose_status(server_status, team):
    """Combines the last known server status with the last known team into
    the single string that actually gets displayed/compared/persisted.
    Team is only relevant while genuinely in a match - not shown for
    NOT_IN_GAME or a Queued status, even if a team happens to be known
    from a previous match."""
    if not is_in_match(server_status):
        return server_status
    if team:
        return f"{team} · {server_status}"
    return server_status

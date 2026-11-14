import base64
import html
import re
import os
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw, ImageFont
from typing import Literal

from pydantic import BaseModel
from google import genai
from google.genai import types
from gtts import gTTS

import reminders as R

# -----------------------------------------------------------------------------
# 0. CONFIG (secrets.toml or environment variables — works locally and in Coder)
# -----------------------------------------------------------------------------
def _setting(name: str, default: str | None = None) -> str | None:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass  # no secrets.toml — fall back to env vars
    return os.environ.get(name, default)

GEMINI_API_KEY = _setting("GEMINI_API_KEY")
# Free tier: Flash-Lite models allow ~500 requests/day each; 3.8 Flash only ~20/day.
# Each model has its own daily quota, so we try them in order and skip any that are used up.
GEMINI_MODEL = _setting("GEMINI_MODEL", "gemini-3.5-flash-lite")
MODEL_CHAIN = list(dict.fromkeys(
    [GEMINI_MODEL, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-3.6-flash"]
))
# Cloud workspaces (Coder) usually run in UTC. A person with dementia must see THEIR clock time.
LOCAL_TZ = ZoneInfo(_setting("REWIND_TIMEZONE", "America/New_York"))
GEMINI_MIN_GAP_S = 3.0  # never call Gemini for automatic look-ins more often than this
# The camera asks Gemini to look when something changes (item appears / is picked up / put down),
# plus a slow "heartbeat" look. This keeps us well inside free-tier limits.
AUTO_LOOK_EVERY_S = float(_setting("REWIND_LOOK_EVERY_S", "25"))


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def clock() -> str:
    return now_local().strftime("%I:%M %p").lstrip("0")


# -----------------------------------------------------------------------------
# 1. PAGE CONFIG & DEMENTIA-ACCESSIBLE NEUTRAL PALETTE
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Rewind — Live Spatial Memory Companion",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    #MainMenu, footer, header {visibility: hidden;}
    .block-container { max-width: 1180px; padding-top: 1.5rem; padding-bottom: 3rem; }

    /* Warm, low-glare neutral surface + deep charcoal high-contrast text */
    .stApp, [data-testid="stAppViewContainer"] { background-color: #F6F3EC !important; color: #18222F !important; }
    h1, h2, h3, p, label, span, div {
        color: #18222F !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    }
    p, li, label { font-size: 19px !important; line-height: 1.55 !important; }
    [data-testid="stIconMaterial"], .material-symbols-rounded, [class*="material-symbols"] {
        font-family: "Material Symbols Rounded" !important;
    }

    .top-header {
        background-color: #FFFFFF; border: 2px solid #D8D1C5; border-radius: 18px;
        padding: 18px 26px; margin-bottom: 20px; display: flex; justify-content: space-between;
        align-items: center; flex-wrap: wrap; gap: 12px;
    }
    .clock-big { font-size: 26px !important; font-weight: 700 !important; }
    .greet { font-size: 40px !important; font-weight: 800 !important; line-height: 1.15 !important; margin: 0 !important; }
    .reassure { font-size: 24px !important; line-height: 1.45 !important; margin: 8px 0 6px 0 !important; color: #23403F !important; }
    .rem-chip { background: #F2EFE9; border-radius: 10px; padding: 10px 14px; margin-bottom: 8px; font-size: 18px !important; line-height: 1.4; }
    .rem-chip.taken { background: #E4F0EE; border-left: 6px solid #2E7D6B; }
    .rem-chip.due { background: #FFF6E5; border-left: 6px solid #B7791F; }
    .rem-chip.later { border-left: 6px solid #C9C0B1; }
    .rem-chip.event { border-left: 6px solid #0F5E6B; }
    .pill-line { font-size: 21px !important; font-weight: 600 !important; line-height: 1.45 !important; margin: 0 0 10px 0 !important; }
    /* Big, warm call button */
    [data-testid="stLinkButton"] a {
        background: #A8471A !important; color: #FFFFFF !important; border: none !important; border-radius: 16px !important;
        font-size: 24px !important; font-weight: 800 !important; padding: 18px 20px !important; width: 100% !important;
        justify-content: center !important; min-height: 70px;
    }
    [data-testid="stLinkButton"] a * { color: #FFFFFF !important; font-size: 24px !important; }
    [data-testid="stLinkButton"] a:hover { background: #8C3A14 !important; }
    .status-pill {
        display: inline-block; background-color: #E4F0EE; color: #174E4F !important;
        border: 1.5px solid #9EC4C1; font-size: 15px !important; font-weight: 700 !important;
        padding: 6px 14px; border-radius: 999px; margin-left: 8px;
    }

    .panel-card {
        background-color: #FFFFFF; border: 2px solid #D8D1C5; border-radius: 18px;
        padding: 20px 22px; margin-bottom: 16px; box-shadow: 0 3px 10px rgba(24, 34, 47, 0.04);
    }
    .panel-title {
        font-size: 14px !important; font-weight: 800 !important; letter-spacing: 0.08em;
        text-transform: uppercase; color: #4A5868 !important; margin: 0 0 10px 0 !important;
    }
    .seen-chip {
        background-color: #F2EFE9; border-left: 6px solid #0F5E6B; border-radius: 10px;
        padding: 12px 14px; margin-bottom: 10px; font-size: 19px !important; line-height: 1.45;
    }
    .seen-chip.person { border-left-color: #A8471A; }
    .seen-chip .when { font-size: 15px !important; color: #4A5868 !important; }
    .now-chip {
        display: inline-block; background: #0F5E6B; color: #FFFFFF !important; border-radius: 999px;
        padding: 6px 14px; margin: 0 6px 6px 0; font-size: 17px !important; font-weight: 700;
    }
    .now-chip.person { background: #A8471A; }
    .now-chip * { color: #FFFFFF !important; }
    .privacy-box { background-color: #F9F7F3; border: 1.5px solid #D8D1C5; border-radius: 16px; padding: 16px 18px; }

    .stButton > button, .stFormSubmitButton > button {
        background-color: #0F5E6B !important; color: #FFFFFF !important; border: none !important;
        border-radius: 12px !important; padding: 14px 20px !important; font-size: 19px !important;
        font-weight: 600 !important; width: 100%; min-height: 56px;
    }
    .stButton > button *, .stFormSubmitButton > button * { color: #FFFFFF !important; }
    .stButton > button:hover, .stFormSubmitButton > button:hover { background-color: #0B4652 !important; }

    [data-testid="stFileUploader"] {
        background-color: #FFFFFF !important; border: 2px solid #C9C0B1 !important;
        border-radius: 18px !important; padding: 12px !important;
    }
    input, select, [data-baseweb="select"] > div {
        background-color: #FFFFFF !important; color: #18222F !important; border: 2px solid #C9C0B1 !important;
        border-radius: 12px !important; font-size: 19px !important;
    }
</style>
""", unsafe_allow_html=True)

if not GEMINI_API_KEY:
    st.error("Gemini API key missing. Add GEMINI_API_KEY to .streamlit/secrets.toml or set it as an environment variable.")
    st.stop()

client = genai.Client(api_key=GEMINI_API_KEY)

# Live camera component (plain HTML/JS, no build step)
live_camera = components.declare_component(
    "rewind_live_camera",
    path=str(Path(__file__).parent / "components" / "live_camera"),
)

# Reminder alerts (banner + chime + voice + desktop notification)
reminder_alerts = components.declare_component(
    "rewind_alerts",
    path=str(Path(__file__).parent / "components" / "alerts"),
)

# Family settings, pills and reminders (saved in caregiver_profile.json)
profile = R.load_profile(LOCAL_TZ)
PATIENT = profile["patient_name"]
RELATIVE = profile["caregiver_name"].split(" (")[0]
RELATIONSHIP = (re.search(r"\(([^)]+)\)", profile["caregiver_name"]) or [None, ""])[1]

# -----------------------------------------------------------------------------
# 2. SESSION MEMORY STATE (IN-MEMORY ONLY — PRIVACY FIRST)
# -----------------------------------------------------------------------------
defaults = {
    "last_seen": [],            # [{item, where, state, room, time}]
    "item_state": {},           # item -> last state, to log changes ("put down", "picked up")
    "what_happened": [{"time": clock(), "event": "Rewind started"}],
    "annotated_img": None,
    "last_answer": None,
    "last_audio": None,
    "processed_ids": set(),
    "ack": 0,
    "visible_now": [],
    "camera_on": False,
    "gemini_last_call": 0.0,
    "gemini_objs": [],          # sent back to the camera so it can draw Gemini's boxes
    "gemini_id": 0,
    "latest_frame": None,       # newest camera still (kept in memory only)
    "latest_frame_at": 0.0,
    "latest_scene": "",
    "last_error": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v.copy() if isinstance(v, (list, dict, set)) else v

# -----------------------------------------------------------------------------
# 3. GEMINI SCHEMAS + HELPERS
# -----------------------------------------------------------------------------
class ParsedReminder(BaseModel):
    title: str                      # short: "Doctor's appointment with Dr. Lee"
    kind: Literal["appointment", "medicine", "visit", "task", "other"]
    date: str                       # YYYY-MM-DD
    time: str                       # HH:MM, 24-hour
    repeat: Literal["none", "daily", "weekly"]
    remind_before_minutes: int      # extra early alert (e.g. 60 for appointments), 0 for none
    spoken_message: str             # warm sentence read aloud when it's time
    confirmation: str               # "Okay. I'll remind you on Monday at 3 PM about ..."


State = Literal["in someone's hand", "on a surface", "being worn", "on the floor", "other"]


class SeenObject(BaseModel):
    label: str          # simple 1-2 word lowercase noun: "water bottle", "glasses", "keys"
    state: State        # in hand vs on a table etc.
    short_place: str    # 2-4 words for the on-screen label: "on the couch", "in right hand", "on the table"
    where_it_is: str    # "on the wooden kitchen table, next to the fruit bowl"
    box_2d: list[int]   # [ymin, xmin, ymax, xmax] normalized 0-1000


class SceneAnalysis(BaseModel):
    objects: list[SeenObject]
    people_count: int
    scene_summary: str  # one short sentence


PERSON_WORDS = {"person", "man", "woman", "people", "child", "boy", "girl"}
SAME_THING = {
    "water bottle": "bottle", "bottle": "bottle", "drink bottle": "bottle",
    "cell phone": "phone", "mobile phone": "phone", "smartphone": "phone", "phone": "phone",
    "mug": "cup", "coffee mug": "cup", "cup": "cup",
    "eyeglasses": "glasses", "reading glasses": "glasses", "glasses": "glasses",
    "tv remote": "remote", "remote control": "remote", "remote": "remote",
    "key": "keys", "keys": "keys", "car keys": "keys",
}


def canon(name: str) -> str:
    n = name.strip().lower()
    return SAME_THING.get(n, n)


def set_error(msg: str | None):
    st.session_state.last_error = msg


def gemini(contents, config=None):
    """Call Gemini, moving to the next model if one is out of quota or unavailable."""
    dead = st.session_state.setdefault("dead_models", {})
    last_exc = None
    for model in MODEL_CHAIN:
        if dead.get(model, 0) > time.time():
            continue
        try:
            res = client.models.generate_content(model=model, contents=contents, config=config)
            st.session_state.active_model = model
            return res
        except Exception as e:
            msg = str(e)
            last_exc = e
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                # per-day limit -> skip for 1 hour; per-minute limit -> skip for 60 s
                dead[model] = time.time() + (3600 if "per day" in msg.lower() or "PerDay" in msg else 60)
                continue
            if "404" in msg or "NOT_FOUND" in msg or "not found" in msg.lower():
                dead[model] = time.time() + 24 * 3600
                continue
            raise
    raise last_exc or RuntimeError("No Gemini model available")


def friendly_error(prefix: str, e: Exception) -> str:
    msg = str(e)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        return (f"{prefix}: every Gemini model is out of free requests right now. "
                "Wait a minute (or until tomorrow for daily limits), use a new API key from a different Google "
                "project, or turn on billing in Google AI Studio.")
    if "401" in msg or "403" in msg or "API key" in msg or "UNAUTHENTICATED" in msg:
        return f"{prefix}: the API key was rejected. Make a new key at aistudio.google.com. ({msg[:200]})"
    return f"{prefix}: {type(e).__name__}: {msg[:400]}"


def data_url_to_image(data_url: str) -> Image.Image | None:
    try:
        b64 = data_url.split(",", 1)[1]
        return Image.open(BytesIO(base64.b64decode(b64))).convert("RGB")
    except Exception:
        return None


def look_at_scene(img: Image.Image, room: str) -> SceneAnalysis:
    """One Gemini call: what everyday things are here, and is each one in a hand or on a surface?"""
    prompt = (
        f"You help a person living with dementia keep track of their belongings. This image is from a camera in the {room}.\n"
        "List the people and the everyday personal items you can see. Pay special attention to: water bottle, cup or mug, "
        "glasses (eyeglasses), keys, phone, wallet, purse, pill bottle or pill organizer, TV remote, hearing aid, watch, book.\n"
        "Ignore furniture, walls, windows and large appliances (but use them to describe locations).\n"
        "For every item give:\n"
        "- label: simple 1-2 word lowercase name (e.g. 'water bottle', 'glasses', 'keys', 'phone', 'person')\n"
        "- state: exactly one of \"in someone's hand\", \"on a surface\", \"being worn\", \"on the floor\", \"other\". "
        "Use \"in someone's hand\" ONLY if fingers are clearly wrapped around it. Glasses on a face are \"being worn\".\n"
        "- short_place: 2-4 words for an on-screen label, naming the furniture or body part: "
        "'on the couch', 'on the table', 'on the counter', 'in right hand', 'on the floor', 'on her face'. "
        "For a person say where they are: 'sitting on the couch', 'standing by the door'.\n"
        "- where_it_is: under 12 words using landmarks a person would recognise, e.g. 'on the wooden table, next to the lamp'. "
        "For held items say who/where, e.g. 'in the person's right hand, by the sofa'.\n"
        "Be careful: do not guess. Glasses are not a remote; only say 'cat' or 'dog' if an animal is clearly visible.\n"
        "- box_2d: [ymin, xmin, ymax, xmax] scaled 0 to 1000.\n"
        "Only include items you are reasonably sure about. Set people_count, and scene_summary to one short calm sentence."
    )
    res = gemini(
        [img, prompt],
        types.GenerateContentConfig(response_mime_type="application/json", response_schema=SceneAnalysis),
    )
    if res.parsed is None:
        raise RuntimeError(f"Gemini returned no structured result: {res.text[:200] if res.text else 'empty'}")
    return res.parsed


def where_phrase(state: str, where: str) -> str:
    if state == "in someone's hand":
        return where if "hand" in where.lower() else f"in someone's hand, {where}"
    if state == "being worn":
        return where if "wear" in where.lower() or "face" in where.lower() else f"being worn, {where}"
    return where


def remember_item(item: str, where: str, room: str, time_label: str, state: str = ""):
    key = canon(item)
    st.session_state.last_seen = [x for x in st.session_state.last_seen if canon(x["item"]) != key]
    st.session_state.last_seen.insert(0, {
        "item": item[:1].upper() + item[1:],
        "where": where,
        "state": state,
        "room": room,
        "time": time_label,
    })
    st.session_state.last_seen = st.session_state.last_seen[:12]


def log_event(text: str, time_label: str | None = None):
    if st.session_state.what_happened and st.session_state.what_happened[0]["event"] == text:
        return  # don't repeat the same line
    st.session_state.what_happened.insert(0, {"time": time_label or clock(), "event": text})
    st.session_state.what_happened = st.session_state.what_happened[:10]


def apply_scene(scene: SceneAnalysis, room: str, time_label: str):
    """Update LAST SEEN + WHAT HAPPENED from a Gemini look, logging only real changes."""
    people = [o for o in scene.objects if o.label.strip().lower() in PERSON_WORDS]
    people_now = ", ".join(f"someone {o.short_place}" for o in people) if people else ""
    if people_now and people_now != st.session_state.get("people_now"):
        log_event(f"{people_now[:1].upper() + people_now[1:]} ({room})", time_label)
    st.session_state.people_now = people_now
    for obj in scene.objects:
        name = obj.label.strip().lower()
        if not name or name in PERSON_WORDS:
            continue
        where = where_phrase(obj.state, obj.where_it_is)
        remember_item(name, where, room, time_label, obj.state)
        prev = st.session_state.item_state.get(canon(name))
        if prev != obj.state:
            nice = name.capitalize()
            if obj.state == "in someone's hand":
                log_event(f"{nice} was picked up ({room})", time_label)
            elif obj.state == "on a surface" and prev == "in someone's hand":
                log_event(f"{nice} was put down {obj.where_it_is} ({room})", time_label)
            elif prev is None:
                log_event(f"Saw the {name} {where} ({room})", time_label)
            st.session_state.item_state[canon(name)] = obj.state


def draw_boxes(image: Image.Image, objects: list[SeenObject]) -> Image.Image:
    """High-contrast corner brackets & labels (terracotta = people, teal = things)."""
    canvas = image.copy().convert("RGB")
    draw = ImageDraw.Draw(canvas)
    w, h = canvas.size
    stroke = max(4, int(min(w, h) * 0.008))
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(18, int(h * 0.035)))
    except Exception:
        font = ImageFont.load_default()

    for obj in objects:
        if len(obj.box_2d) != 4:
            continue
        accent = (168, 71, 26) if obj.label.lower() in PERSON_WORDS else (15, 94, 107)
        ymin, xmin, ymax, xmax = obj.box_2d
        x1, y1 = int(max(0, min(1000, xmin)) / 1000 * w), int(max(0, min(1000, ymin)) / 1000 * h)
        x2, y2 = int(max(0, min(1000, xmax)) / 1000 * w), int(max(0, min(1000, ymax)) / 1000 * h)
        if x2 <= x1 or y2 <= y1:
            continue
        corner = max(16, int(min(x2 - x1, y2 - y1) * 0.25))
        for color, width in (((255, 255, 255), stroke + 4), (accent, stroke)):
            for (ax, ay), (bx, by) in [
                ((x1, y1), (x1 + corner, y1)), ((x1, y1), (x1, y1 + corner)),
                ((x2, y1), (x2 - corner, y1)), ((x2, y1), (x2, y1 + corner)),
                ((x1, y2), (x1 + corner, y2)), ((x1, y2), (x1, y2 - corner)),
                ((x2, y2), (x2 - corner, y2)), ((x2, y2), (x2, y2 - corner)),
            ]:
                draw.line([(ax, ay), (bx, by)], fill=color, width=width)
        short = f" · {obj.short_place}" if obj.short_place else ""
        label_text = f" {obj.label.capitalize()}{short} "
        bbox = draw.textbbox((0, 0), label_text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        ly = y1 - th - 14 if y1 - th - 14 > 4 else y1 + 6
        draw.rounded_rectangle([x1, ly, x1 + tw + 10, ly + th + 10], radius=8, fill=accent, outline=(255, 255, 255), width=2)
        draw.text((x1 + 5, ly + 3), label_text, fill=(255, 255, 255), font=font)
    return canvas


def process_camera_events(payload: dict | None, room: str):
    """Turn live-camera events into RIGHT NOW / LAST SEEN / WHAT HAPPENED."""
    if not payload:
        return
    st.session_state.visible_now = payload.get("visible", [])
    st.session_state.camera_on = bool(payload.get("camera_on"))

    events = sorted(payload.get("events", []), key=lambda e: e.get("id", 0))
    # Only the newest automatic look matters — skip older ones (saves Gemini calls)
    autos = [e for e in events if e.get("type") == "auto" and e.get("id") not in st.session_state.processed_ids]
    newest_auto = autos[-1]["id"] if autos else None

    for ev in events:
        ev_id = ev.get("id")
        if not ev_id or ev_id in st.session_state.processed_ids:
            continue
        ev_room = ev.get("room") or room
        t = ev.get("time_label") or clock()
        kind, label = ev.get("type"), ev.get("label", "Item")

        if kind == "arrived":
            log_event(f"Someone came into view ({ev_room})", t)
        elif kind == "left":
            log_event(f"Someone left the view ({ev_room})", t)
        elif kind in ("placed", "lost"):
            # The in-browser detector noticed a change. Note it now with rough words;
            # the next Gemini look-in replaces it with a proper place ("on the table…").
            held = bool(ev.get("held"))
            rough = ev.get("position", "in view")
            if canon(label) not in st.session_state.item_state:  # Gemini hasn't described it yet
                remember_item(label, f"in someone's hand, {rough}" if held else rough, ev_room, t,
                              "in someone's hand" if held else "")
            if kind == "lost":
                log_event(f"{label} {'was carried out of view' if held else 'went out of view'} ({ev_room})", t)
        elif kind == "auto" and ev_id == newest_auto:
            img = data_url_to_image(ev.get("snapshot", ""))
            if img is not None:
                st.session_state.latest_frame = img
                st.session_state.latest_frame_at = time.time()
                if ev.get("manual") or time.time() - st.session_state.gemini_last_call > GEMINI_MIN_GAP_S:
                    st.session_state.gemini_last_call = time.time()
                    try:
                        scene = look_at_scene(img, ev_room)
                        st.session_state.latest_scene = scene.scene_summary
                        st.session_state.gemini_objs = [
                            {"label": o.label, "state": o.state, "place": o.short_place,
                             "where": o.where_it_is, "box": o.box_2d}
                            for o in scene.objects
                        ]
                        st.session_state.gemini_id = ev_id
                        apply_scene(scene, ev_room, t)
                        if ev.get("manual"):
                            st.session_state.annotated_img = draw_boxes(img, scene.objects)
                        set_error(None)
                    except Exception as e:
                        set_error(friendly_error("Gemini look-in failed", e))
                        print("Gemini look-in failed:", repr(e))

        # mark done right away so a rerun can't repeat it
        st.session_state.processed_ids.add(ev_id)
        st.session_state.ack = max(st.session_state.ack, ev_id)


def parse_reminder(text: str) -> dict:
    """Turn 'dentist with Dr. Lee next Tuesday at 2' into a real timed reminder (Gemini, with a simple backup)."""
    now = now_local()
    prompt = (
        f"Right now it is {now.strftime('%A, %B %d, %Y, %I:%M %p')} ({LOCAL_TZ.key}).\n"
        f"A caregiver or a person living with dementia ({PATIENT}) wants a reminder: \"{text}\"\n"
        "Turn it into a reminder. Rules: pick the next matching date in the future; if no time is given choose a sensible "
        "one (morning tasks 09:00, appointments 10:00); appointments get remind_before_minutes=60 (or 120 if travel is "
        "mentioned); medicine taken every day => kind 'medicine' and repeat 'daily'. "
        f"spoken_message: one warm, simple sentence spoken to {PATIENT} at that moment, e.g. "
        "'It's time for your dentist appointment with Dr. Lee. Your coat is by the door.' "
        "confirmation: one short sentence confirming when you'll remind them, using the weekday and a 12-hour time."
    )
    try:
        res = gemini(prompt, types.GenerateContentConfig(response_mime_type="application/json",
                                                         response_schema=ParsedReminder))
        r = res.parsed
        datetime.strptime(r.date, "%Y-%m-%d")
        datetime.strptime(r.time, "%H:%M")
        return {"title": r.title, "message": r.spoken_message, "kind": r.kind, "date": r.date, "time": r.time,
                "repeat": r.repeat, "remind_before_minutes": max(0, r.remind_before_minutes),
                "confirmation": r.confirmation}
    except Exception as e:
        print("Gemini reminder parse failed, using simple parser:", repr(e))
        parsed = R.simple_parse(text, now)
        if parsed is None:
            raise ValueError("no time found")
        return parsed


def say(text: str) -> bytes | None:
    try:
        buf = BytesIO()
        gTTS(text, lang="en", slow=False).write_to_fp(buf)
        return buf.getvalue()
    except Exception:
        return None


def schedule_lines() -> list[str]:
    now = now_local()
    lines = ["PILLS TODAY: " + R.pills_sentence(R.med_status(profile, now))]
    for u in R.upcoming(profile, now, LOCAL_TZ, days=14)[:6]:
        lines.append(f"- {u['title']}: {R.when_words(u['at'], now)}")
    return lines


def answer_from_notes(question: str) -> str:
    """Simple answer straight from LAST SEEN — works even when Gemini is unavailable."""
    q = question.lower()
    if re.search(r"pill|medic|tablet", q):
        return R.pills_sentence(R.med_status(profile, now_local()))
    if re.search(r"appointment|doctor|today|tomorrow|next|plan|schedule", q):
        ups = R.upcoming(profile, now_local(), LOCAL_TZ, days=14)
        if ups:
            u = ups[0]
            return f"Next is {u['title'].lower()}, {R.when_words(u['at'], now_local())}."
        return "There is nothing else planned. You can rest."
    if "who" in q:
        people = [e for e in st.session_state.what_happened if "someone" in e["event"].lower()]
        if people:
            return f"{people[0]['event']} at {people[0]['time']}."
        return "I haven't seen anyone yet."
    for e in st.session_state.last_seen:
        name = e["item"].lower()
        if name in q or canon(name) in q or any(w in q for w in canon(name).split()):
            return f"Your {name} was {e['where']}, in the {e['room'].lower()}, at {e['time']}."
    return "I haven't seen that yet. Let's show the camera around the room together."


def answer_spatial_question(question: str):
    frame_fresh = (
        st.session_state.latest_frame is not None
        and st.session_state.camera_on
        and time.time() - st.session_state.latest_frame_at < 60
    )
    if False:
        pass
    else:
        seen_lines = [
            f"- {x['item']}: {x['where']} ({x['state'] or 'state unknown'}), {x['room']}, last seen {x['time']}"
            for x in st.session_state.last_seen
        ]
        event_lines = [f"- {e['time']}: {e['event']}" for e in st.session_state.what_happened]
        prompt = (
            "You are Rewind, a calm, reassuring memory helper for someone living with dementia or Alzheimer's.\n"
            + ("The attached image is what the camera sees RIGHT NOW. Look at it first: if the item is visible, "
               "say exactly where it is and whether it is in someone's hand or sitting on something.\n" if frame_fresh else "")
            + "If it is not visible now, use the notes below and say where and when it was last seen.\n"
            "Reply in 1-2 short, warm, simple sentences. Say the place first, then the time. "
            "Never blame or correct the person. If you truly don't know, say so gently and suggest showing the camera around.\n\n"
            f"CURRENT TIME: {now_local().strftime('%A')} {clock()}\n"
            f"PERSON'S NAME: {PATIENT}. FAMILY: {RELATIVE} ({RELATIONSHIP}).\n\n"
            "REMINDERS AND PILLS:\n" + "\n".join(schedule_lines()) + "\n\n"
            f"LAST SEEN ITEMS:\n{chr(10).join(seen_lines) if seen_lines else 'None yet'}\n\n"
            f"WHAT HAPPENED:\n{chr(10).join(event_lines)}\n\n"
            f"QUESTION: {question}"
        )
        contents = [st.session_state.latest_frame, prompt] if frame_fresh else prompt
        try:
            res = gemini(contents)
            ans = (res.text or "").strip() or answer_from_notes(question)
            set_error(None)
        except Exception as e:
            set_error(friendly_error("Gemini answer failed", e))
            print("Gemini answer failed:", repr(e))
            ans = answer_from_notes(question)

    st.session_state.last_answer = ans
    st.session_state.last_audio = say(ans)


# -----------------------------------------------------------------------------
# 4. TOP HEADER
# -----------------------------------------------------------------------------
# Handle "Done" presses from reminder alerts before drawing anything
for act in (st.session_state.get("rem_alerts") or {}).get("actions", []):
    if act.get("id", 0) <= st.session_state.get("alerts_ack", 0):
        continue
    if act.get("action") == "done" and act.get("alert"):
        R.complete_alert(profile, act["alert"], now_local())
        log_event(f"Reminder done: {act['alert'].get('title', '')}")
    st.session_state.alerts_ack = act["id"]

_now = now_local()
part_of_day = "morning" if _now.hour < 12 else ("afternoon" if _now.hour < 17 else "evening")
visit_today = next((u for u in R.upcoming(profile, _now, LOCAL_TZ, days=1)
                    if u.get("kind") == "visit" and u["at"].date() == _now.date() and u["at"] > _now), None)
reassure = profile.get("home_note") or "You are safe. You are at home."
if visit_today:
    reassure += f" {RELATIVE} is coming to see you at {R.nice_time(visit_today['at'])}."
greeting = f"Good {part_of_day}, {PATIENT}."

h_left, h_right = st.columns([2.6, 1], gap="medium")
with h_left:
    st.markdown(f"""
    <div class="top-header" style="display:block;">
        <p class="greet">👋 {html.escape(greeting)}</p>
        <p class="reassure">{html.escape(reassure)}</p>
        <p class="clock-big" style="margin:4px 0 0 0;">It is {_now.strftime("%A, %B ")}{_now.day} &nbsp;•&nbsp; {clock()}</p>
        <div style="margin-top:10px;">
            <span class="status-pill" style="margin-left:0;">🧭 REWIND LIVE</span>
            <span class="status-pill">{html.escape(st.session_state.get("active_model", GEMINI_MODEL).upper())}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
with h_right:
    phone = profile.get("caregiver_phone", "")
    digits = re.sub(r"[^\d+]", "", phone)
    if digits and not digits.startswith("+") and len(digits) == 10:
        digits = "+1" + digits
    st.link_button(f"📞 Call {RELATIVE}", f"tel:{digits}", width="stretch")
    st.markdown(f"<p style='text-align:center; font-size:20px !important; margin:6px 0 10px 0;'>"
                f"{html.escape(RELATIVE)}{' · ' + html.escape(RELATIONSHIP) if RELATIONSHIP else ''}<br/>"
                f"<strong>{html.escape(phone)}</strong></p>", unsafe_allow_html=True)
    if st.button("🔊 Say hello", width="stretch"):
        st.session_state.hello_audio = say(f"{greeting} {reassure} It is {_now.strftime('%A')}, {clock()}.")
    if st.session_state.get("hello_audio"):
        st.audio(st.session_state.hello_audio, format="audio/mp3", autoplay=True)

# Reminder alerts appear here, big, when something is due
reminder_alerts(
    alerts=R.alert_schedule(profile, _now, LOCAL_TZ),
    ack=st.session_state.get("alerts_ack", 0),
    key="rem_alerts",
    default=None,
)

# -----------------------------------------------------------------------------
# 5. MAIN TWO-COLUMN: LIVE CAMERA + MEMORY
# -----------------------------------------------------------------------------
left_col, right_col = st.columns([1.5, 1], gap="large")

with left_col:
    c_room, c_mode = st.columns([1, 1])
    with c_room:
        current_room = st.selectbox("I am in:", ["Kitchen", "Living Room", "Bedroom", "Bathroom", "Hallway"])
    with c_mode:
        source_mode = st.radio("Camera:", ["Live camera", "Use a photo"], horizontal=True)

    if source_mode == "Live camera":
        # Handle what the camera sent BEFORE drawing it, so Gemini's boxes reach the camera straight away
        process_camera_events(st.session_state.get("live_cam"), current_room)
        live_camera(
            ack=st.session_state.ack,
            room=current_room,
            gemini=st.session_state.gemini_objs,
            gemini_id=st.session_state.gemini_id,
            scan_every_ms=int(AUTO_LOOK_EVERY_S * 1000),
            key="live_cam",
            default=None,
        )
    else:
        photo = st.file_uploader("Upload a room photo", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
        if photo is not None and st.button("🔍 Look closely at this photo"):
            with st.spinner("Looking around calmly..."):
                img = Image.open(photo).convert("RGB")
                try:
                    scene = look_at_scene(img, current_room)
                    st.session_state.annotated_img = draw_boxes(img, scene.objects)
                    st.session_state.latest_frame, st.session_state.latest_frame_at = img, time.time()
                    apply_scene(scene, current_room, clock())
                    set_error(None)
                except Exception as e:
                    set_error(friendly_error("Gemini photo look failed", e))

    if st.session_state.annotated_img is not None:
        st.image(st.session_state.annotated_img, caption=f"Gemini's closer look — {current_room}", width="stretch")

with right_col:
    # TODAY'S REMINDERS
    with st.container(border=True):
        st.markdown("<p class='panel-title'>💊 PILLS TODAY</p>", unsafe_allow_html=True)
        meds = R.med_status(profile, _now)
        st.markdown(f"<p class='pill-line'>{html.escape(R.pills_sentence(meds))}</p>", unsafe_allow_html=True)
        for m in meds:
            if m["state"] == "taken":
                st.markdown(f"<div class='rem-chip taken'>✅ <strong>{html.escape(m['name'])}</strong> — taken at {m['taken_at']}</div>",
                            unsafe_allow_html=True)
            else:
                label = {"due": "it's time now", "missed": "not taken yet", "later": "later"}[m["state"]]
                cls = "due" if m["state"] in ("due", "missed") else "later"
                st.markdown(f"<div class='rem-chip {cls}'>⏳ <strong>{html.escape(m['name'])}</strong> · "
                            f"{R.nice_time(m['due'])} — {label}</div>", unsafe_allow_html=True)
                if m["state"] in ("due", "missed"):
                    if st.button(f"✅ I took my {m['name'].lower()}", key=f"took_{m['id']}"):
                        R.mark_taken(profile, m["id"], now_local())
                        log_event(f"{m['name']} taken")
                        st.rerun()

        st.markdown("<p class='panel-title' style='margin-top:14px !important;'>📅 COMING UP</p>", unsafe_allow_html=True)
        ups = R.upcoming(profile, _now, LOCAL_TZ, days=30)[:5]
        icons = {"appointment": "🩺", "visit": "🤗", "medicine": "💊", "task": "📝", "other": "🔔"}
        if ups:
            for u in ups:
                st.markdown(f"<div class='rem-chip event'>{icons.get(u.get('kind'), '🔔')} <strong>{html.escape(u['title'])}</strong>"
                            f"<br/>{html.escape(R.when_words(u['at'], _now))}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='rem-chip'>Nothing planned. You can rest.</div>", unsafe_allow_html=True)

        with st.form("add_reminder", clear_on_submit=True, border=False):
            new_rem = st.text_input("➕ Add a reminder in your own words",
                                    placeholder="e.g. Dentist with Dr. Lee next Tuesday at 2pm")
            add_pressed = st.form_submit_button("Add reminder", width="stretch")
        if add_pressed and new_rem.strip():
            with st.spinner("Setting up your reminder…"):
                try:
                    parsed = parse_reminder(new_rem.strip())
                    R.add_reminder(profile, title=parsed["title"], message=parsed["message"], kind=parsed["kind"],
                                   day=parsed["date"], time_hm=parsed["time"], repeat=parsed["repeat"],
                                   remind_before_minutes=parsed["remind_before_minutes"])
                    st.session_state.reminder_msg = ("ok", parsed["confirmation"])
                    st.session_state.reminder_audio = say(parsed["confirmation"])
                    log_event(f"New reminder: {parsed['title']}")
                except Exception:
                    st.session_state.reminder_msg = ("err", "I couldn't tell when. Try adding a day and time, "
                                                            "like “tomorrow at 3pm”.")
            st.rerun()
        if st.session_state.get("reminder_msg"):
            kind_, msg_ = st.session_state.reminder_msg
            (st.success if kind_ == "ok" else st.warning)(msg_)
        if st.session_state.get("reminder_audio"):
            st.audio(st.session_state.reminder_audio, format="audio/mp3", autoplay=True)

    # RIGHT NOW
    if st.session_state.camera_on:
        gem_by_kind = {canon(g["label"]): g for g in st.session_state.gemini_objs if g["label"].lower() not in PERSON_WORDS}

        def live_chip(v):
            g = gem_by_kind.get(canon(v["label"]))
            name = g["label"].capitalize() if g else v["label"]
            place = (g.get("place") if g else "") or ("in hand" if v.get("held") else "")
            cls = "person" if v["label"] == "Person" else ""
            return f"<span class='now-chip {cls}'>{html.escape(name)}{' · ' + html.escape(place) if place else ''}</span>"

        chips = "".join(live_chip(v) for v in st.session_state.visible_now)
        if st.session_state.get("people_now"):
            chips = chips.replace(">Person</span>", f">Person · {html.escape(st.session_state.people_now.split(',')[0].replace('someone ', ''))}</span>", 1)
        seen_names = {canon(v["label"]) for v in st.session_state.visible_now}
        for g in st.session_state.gemini_objs:
            if g["label"].lower() in PERSON_WORDS or canon(g["label"]) in seen_names:
                continue
            short = f" · {g['place']}" if g.get("place") else ""
            chips += f"<span class='now-chip'>{html.escape(g['label'].capitalize())}{html.escape(short)}</span>"
        chips = chips or "<p style='margin:0; color:#4A5868 !important;'>Nothing I recognise right now.</p>"
    else:
        chips = "<p style='margin:0; color:#4A5868 !important;'>Camera is off.</p>"
    st.markdown(f"<div class='panel-card'><p class='panel-title'>RIGHT NOW</p>{chips}</div>", unsafe_allow_html=True)

    # LAST SEEN
    if st.session_state.last_seen:
        seen_html = "".join(
            f"<div class='seen-chip'><strong>{html.escape(e['item'])}:</strong> {html.escape(e['where'])}"
            f"<br/><span class='when'>{html.escape(e['room'])} · {html.escape(e['time'])}</span></div>"
            for e in st.session_state.last_seen
        )
    else:
        seen_html = ("<p style='margin:0; color:#4A5868 !important;'>Nothing yet. Turn on the camera and "
                     "show me your things, like a water bottle or your glasses.</p>")
    st.markdown(f"""
    <div class="panel-card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <p class="panel-title" style="margin:0 !important;">LAST SEEN</p>
            <span style="font-size:15px !important; color:#4A5868 !important;">{len(st.session_state.last_seen)} things remembered</span>
        </div>
        {seen_html}
    </div>
    """, unsafe_allow_html=True)

    # WHAT HAPPENED
    happened_html = "".join(
        f"<p style='margin:6px 0; font-size:18px !important;'><strong>{html.escape(ev['time'])}</strong> &nbsp; {html.escape(ev['event'])}</p>"
        for ev in st.session_state.what_happened
    )
    st.markdown(f"<div class='panel-card'><p class='panel-title'>WHAT HAPPENED</p>{happened_html}</div>", unsafe_allow_html=True)

    st.markdown("""
    <div class="privacy-box">
        <p style="font-size:16px !important; margin:0;">
            <strong>Nothing is saved permanently.</strong> The moving boxes are worked out on this device.
            When something changes (and every half minute), one still photo is sent to Gemini to find small things and where they are.
            Notes like <em>“Glasses: on the kitchen table, 1:54 PM”</em> are erased when you close this tab.
            Only reminders and family settings are saved.
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.write("")
    if st.button("🗑️ Erase memory now"):
        st.session_state.last_seen = []
        st.session_state.item_state = {}
        st.session_state.gemini_objs = []
        st.session_state.annotated_img = None
        st.session_state.last_answer = None
        st.session_state.last_audio = None
        st.session_state.latest_frame = None
        st.session_state.what_happened = [{"time": clock(), "event": "Memory erased"}]
        st.rerun()

# -----------------------------------------------------------------------------
# 6. ASK BAR + ONE-TAP QUICK QUESTIONS + SPOKEN ANSWER
# -----------------------------------------------------------------------------
with st.container(border=True):
    st.markdown("<p class='panel-title'>ASK ABOUT YOUR THINGS</p>", unsafe_allow_html=True)
    with st.form("ask_form", clear_on_submit=True, border=False):
        q_col1, q_col2 = st.columns([3.5, 1])
        with q_col1:
            user_q = st.text_input("Ask a question", placeholder="Where is my bottle?", label_visibility="collapsed")
        with q_col2:
            ask_pressed = st.form_submit_button("🔊 Ask", width="stretch")

    quick = ["Where is my bottle?", "Where are my glasses?", "Where is my phone?",
             "Did I take my pills?", "What's next today?", "Who was here?"]
    for row in (quick[:3], quick[3:]):
        cols = st.columns(3)
        for col, q in zip(cols, row):
            with col:
                if st.button(q, key=f"quick_{q}"):
                    with st.spinner("Thinking…"):
                        answer_spatial_question(q)

    if ask_pressed and user_q.strip():
        with st.spinner("Thinking…"):
            answer_spatial_question(user_q.strip())

    if st.session_state.last_answer:
        st.markdown(
            f"<div class='seen-chip' style='margin-top:14px; font-size:23px !important;'>"
            f"<strong>Rewind:</strong> {html.escape(st.session_state.last_answer)}</div>",
            unsafe_allow_html=True,
        )
    if st.session_state.last_audio:
        st.audio(st.session_state.last_audio, format="audio/mp3", autoplay=True)

# -----------------------------------------------------------------------------
# 7. FAMILY SETTINGS (collapsed)
# -----------------------------------------------------------------------------
with st.expander("👪 For family: names, phone number, pills and reminders"):
    with st.form("family_settings", border=False):
        c1, c2 = st.columns(2)
        with c1:
            f_name = st.text_input("Name of the person using Rewind", profile["patient_name"])
            f_home = st.text_input("Reassuring words shown at the top", profile.get("home_note", ""))
        with c2:
            f_rel = st.text_input("Family member to call (name and relationship)", profile["caregiver_name"],
                                  help="For example: Sarah (Daughter)")
            f_phone = st.text_input("Their phone number", profile["caregiver_phone"])
        st.markdown("**Pill times** (24-hour, like 08:00 or 20:00)")
        med_cols = st.columns(max(1, len(profile["meds"])))
        new_times = {}
        for col, m in zip(med_cols, profile["meds"]):
            with col:
                new_times[m["id"]] = st.text_input(m["name"], m["time"], key=f"medtime_{m['id']}")
        if st.form_submit_button("Save settings"):
            profile.update(patient_name=f_name.strip() or profile["patient_name"], home_note=f_home.strip(),
                           caregiver_name=f_rel.strip() or profile["caregiver_name"], caregiver_phone=f_phone.strip())
            for m in profile["meds"]:
                t = new_times.get(m["id"], m["time"]).strip()
                if re.fullmatch(r"\d{1,2}:\d{2}", t):
                    m["time"] = t.zfill(5)
            R.save_profile(profile)
            st.rerun()

    st.markdown("**All reminders** (tap 🗑 to remove)")
    for r in profile["reminders"] + [dict(m, title=m["name"], repeat="daily", date="", kind="medicine") for m in profile["meds"]]:
        when = f"every day at {r['time']}" if r.get("repeat") == "daily" else (
            f"every week, {r['date']} {r['time']}" if r.get("repeat") == "weekly" else f"{r['date']} {r['time']}")
        cc1, cc2 = st.columns([5, 1])
        with cc1:
            st.write(f"{'✔️ ' if r.get('done') else ''}{r['title']} — {when}")
        with cc2:
            if st.button("🗑", key=f"del_{r['id']}"):
                R.delete_reminder(profile, r["id"])
                st.rerun()
    taken_today = [m for m in R.med_status(profile, now_local()) if m["state"] == "taken"]
    for m in taken_today:
        if st.button(f"Undo: {m['name']} marked as taken", key=f"undo_{m['id']}"):
            R.undo_taken(profile, m["id"], now_local())
            st.rerun()

# -----------------------------------------------------------------------------
# 8. TEAM-ONLY TROUBLESHOOTING (collapsed so it doesn't distract the user)
# -----------------------------------------------------------------------------
with st.expander("🛠 For the team: connection check"):
    if st.session_state.last_error:
        st.error(st.session_state.last_error)
    else:
        st.write("No errors so far.")
    dead = st.session_state.get("dead_models", {})
    resting = [m for m, until in dead.items() if until > time.time()]
    st.caption(f"Using: {st.session_state.get('active_model', GEMINI_MODEL)} · Backup order: {', '.join(MODEL_CHAIN)} · "
               f"Resting (out of quota): {', '.join(resting) or 'none'} · Heartbeat look every {AUTO_LOOK_EVERY_S:g}s · "
               f"Key starts with: {GEMINI_API_KEY[:4]}…")
    if st.button("Test Gemini now"):
        try:
            r = gemini("Reply with the single word: ready")
            st.session_state.gemini_test = ("ok", f"Gemini works ✅ using {st.session_state.active_model} "
                                                  f"(it said: {(r.text or '').strip()[:40]})")
            set_error(None)
        except Exception as e:
            st.session_state.gemini_test = ("err", friendly_error("Gemini failed", e))
    if st.session_state.get("gemini_test"):
        kind, msg = st.session_state.gemini_test
        (st.success if kind == "ok" else st.error)(msg)

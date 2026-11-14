import base64
import html
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
GEMINI_MODEL = _setting("GEMINI_MODEL", "gemini-3.8-flash")
# Cloud workspaces (Coder) usually run in UTC. A person with dementia must see THEIR clock time.
LOCAL_TZ = ZoneInfo(_setting("REWIND_TIMEZONE", "America/New_York"))
GEMINI_MIN_GAP_S = 3.0  # never call Gemini for automatic look-ins more often than this
AUTO_LOOK_EVERY_S = float(_setting("REWIND_LOOK_EVERY_S", "8"))  # how often the camera asks Gemini to look


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
State = Literal["in someone's hand", "on a surface", "being worn", "on the floor", "other"]


class SeenObject(BaseModel):
    label: str          # simple 1-2 word lowercase noun: "water bottle", "glasses", "keys"
    state: State        # in hand vs on a table etc.
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
        "- where_it_is: under 12 words using landmarks a person would recognise, e.g. 'on the wooden table, next to the lamp'. "
        "For held items say who/where, e.g. 'in the person's right hand, by the sofa'.\n"
        "- box_2d: [ymin, xmin, ymax, xmax] scaled 0 to 1000.\n"
        "Only include items you are reasonably sure about. Set people_count, and scene_summary to one short calm sentence."
    )
    res = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[img, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SceneAnalysis,
        ),
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
        short = {"in someone's hand": " · in hand", "on a surface": " · on a surface",
                 "being worn": " · being worn", "on the floor": " · on the floor"}.get(obj.state, "")
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
                            {"label": o.label, "state": o.state, "where": o.where_it_is, "box": o.box_2d}
                            for o in scene.objects
                        ]
                        st.session_state.gemini_id = ev_id
                        apply_scene(scene, ev_room, t)
                        if ev.get("manual"):
                            st.session_state.annotated_img = draw_boxes(img, scene.objects)
                        set_error(None)
                    except Exception as e:
                        set_error(f"Gemini look-in failed: {type(e).__name__}: {e}")
                        print("Gemini look-in failed:", repr(e))

        # mark done right away so a rerun can't repeat it
        st.session_state.processed_ids.add(ev_id)
        st.session_state.ack = max(st.session_state.ack, ev_id)


def answer_spatial_question(question: str):
    frame_fresh = (
        st.session_state.latest_frame is not None
        and st.session_state.camera_on
        and time.time() - st.session_state.latest_frame_at < 60
    )
    if not st.session_state.last_seen and not frame_fresh:
        ans = "I haven't seen anything yet. Turn on the camera and show me around the room."
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
            f"CURRENT TIME: {clock()}\n\n"
            f"LAST SEEN ITEMS:\n{chr(10).join(seen_lines) if seen_lines else 'None yet'}\n\n"
            f"WHAT HAPPENED:\n{chr(10).join(event_lines)}\n\n"
            f"QUESTION: {question}"
        )
        contents = [st.session_state.latest_frame, prompt] if frame_fresh else prompt
        try:
            res = client.models.generate_content(model=GEMINI_MODEL, contents=contents)
            ans = (res.text or "").strip() or "I'm not sure right now. Let's look around the room together."
            set_error(None)
        except Exception as e:
            set_error(f"Gemini answer failed: {type(e).__name__}: {e}")
            print("Gemini answer failed:", repr(e))
            ans = "I'm having trouble thinking right now. Please try again in a moment."

    st.session_state.last_answer = ans
    try:
        buf = BytesIO()
        gTTS(ans, lang="en", slow=False).write_to_fp(buf)
        st.session_state.last_audio = buf.getvalue()
    except Exception:
        st.session_state.last_audio = None


# -----------------------------------------------------------------------------
# 4. TOP HEADER
# -----------------------------------------------------------------------------
st.markdown(f"""
<div class="top-header">
    <div>
        <h1 style="margin:0; font-size:30px !important;">🧭 REWIND LIVE</h1>
        <p class="clock-big" style="margin:4px 0 0 0;">{now_local().strftime("%A, %B ")}{now_local().day} &nbsp;•&nbsp; {clock()}</p>
    </div>
    <div>
        <span class="status-pill">● LIVE DETECTION ON THIS DEVICE</span>
        <span class="status-pill">{html.escape(GEMINI_MODEL.upper())}</span>
    </div>
</div>
""", unsafe_allow_html=True)

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
                    set_error(f"Gemini photo look failed: {type(e).__name__}: {e}")

    if st.session_state.annotated_img is not None:
        st.image(st.session_state.annotated_img, caption=f"Gemini's closer look — {current_room}", width="stretch")

with right_col:
    # RIGHT NOW
    if st.session_state.camera_on:
        chips = "".join(
            f"<span class='now-chip {'person' if v['label'] == 'Person' else ''}'>"
            f"{html.escape(v['label'])}{' · in hand' if v.get('held') else ''}</span>"
            for v in st.session_state.visible_now
        )
        seen_names = {canon(v["label"]) for v in st.session_state.visible_now}
        for g in st.session_state.gemini_objs:
            if g["label"].lower() in PERSON_WORDS or canon(g["label"]) in seen_names:
                continue
            short = {"in someone's hand": " · in hand", "on a surface": " · on a surface",
                     "being worn": " · being worn", "on the floor": " · on the floor"}.get(g["state"], "")
            chips += f"<span class='now-chip'>{html.escape(g['label'].capitalize())}{short}</span>"
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
            Every few seconds one still photo is sent to Gemini to find small things and where they are.
            Notes like <em>“Glasses: on the kitchen table, 1:54 PM”</em> are erased when you close this tab.
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

    quick = ["Where is my bottle?", "Where are my glasses?", "Where is my phone?", "Who was here?"]
    for row in (quick[:2], quick[2:]):
        cols = st.columns(2)
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
# 7. TEAM-ONLY TROUBLESHOOTING (collapsed so it doesn't distract the user)
# -----------------------------------------------------------------------------
with st.expander("🛠 For the team: connection check"):
    if st.session_state.last_error:
        st.error(st.session_state.last_error)
    else:
        st.write("No errors so far.")
    st.caption(f"Model: {GEMINI_MODEL} · Gemini look-in every {AUTO_LOOK_EVERY_S:g}s · "
               f"Key starts with: {GEMINI_API_KEY[:4]}…")
    if st.button("Test Gemini now"):
        try:
            r = client.models.generate_content(model=GEMINI_MODEL, contents="Reply with the single word: ready")
            st.session_state.gemini_test = ("ok", f"Gemini works ✅  (it said: {(r.text or '').strip()[:40]})")
            set_error(None)
        except Exception as e:
            st.session_state.gemini_test = ("err", f"Gemini failed: {type(e).__name__}: {e}")
    if st.session_state.get("gemini_test"):
        kind, msg = st.session_state.gemini_test
        (st.success if kind == "ok" else st.error)(msg)

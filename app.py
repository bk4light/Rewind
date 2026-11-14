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
GEMINI_MIN_GAP_S = 4.0  # don't call Gemini more often than this for automatic look-ups


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

    .stButton > button {
        background-color: #0F5E6B !important; color: #FFFFFF !important; border: none !important;
        border-radius: 12px !important; padding: 14px 20px !important; font-size: 19px !important;
        font-weight: 600 !important; width: 100%; min-height: 56px;
    }
    .stButton > button * { color: #FFFFFF !important; }
    .stButton > button:hover { background-color: #0B4652 !important; }

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
    "last_seen": [],          # [{item, where, room, time, held}]
    "what_happened": [{"time": clock(), "event": "Rewind started"}],
    "annotated_img": None,
    "last_answer": None,
    "last_audio": None,
    "processed_ids": set(),
    "ack": 0,
    "visible_now": [],
    "camera_on": False,
    "gemini_last_call": 0.0,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# -----------------------------------------------------------------------------
# 3. GEMINI SCHEMAS + HELPERS
# -----------------------------------------------------------------------------
class DetectedObject(BaseModel):
    label: str
    where_it_is: str
    box_2d: list[int]  # [ymin, xmin, ymax, xmax] normalized 0-1000


class FrameAnalysis(BaseModel):
    objects: list[DetectedObject]
    person_present: bool
    event_summary: str


class ItemLocation(BaseModel):
    item_name: str     # more specific name, e.g. "water bottle"
    where_it_is: str   # e.g. "on the kitchen counter, next to the sink"


def data_url_to_image(data_url: str) -> Image.Image | None:
    try:
        b64 = data_url.split(",", 1)[1]
        return Image.open(BytesIO(base64.b64decode(b64))).convert("RGB")
    except Exception:
        return None


def describe_item_location(img: Image.Image, label: str, box: list[int], room: str, held: bool) -> ItemLocation | None:
    """Ask Gemini for a human description of where a tracked item is (landmarks, not pixels)."""
    prompt = (
        f"This photo is from a home camera in the {room or 'home'}. "
        f"There is a {label.lower()} inside the box [ymin, xmin, ymax, xmax] = {box} (0-1000 scale). "
        "Say where it is using furniture and landmarks a person would recognise, in under 12 words, "
        "for example 'on the kitchen counter, next to the sink'. "
        + ("It appears to be held by a person: say 'in someone's hand' and where they are standing. " if held else "")
        + "Also give item_name: a more specific 1-3 word name if obvious (e.g. 'water bottle'), else the same word."
    )
    try:
        res = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[img, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ItemLocation,
            ),
        )
        return res.parsed
    except Exception as e:  # network / quota — fall back to rough position words
        print("Gemini location lookup failed:", e)
        return None


def remember_item(item: str, where: str, room: str, time_label: str, held: bool = False):
    key = item.lower()
    st.session_state.last_seen = [x for x in st.session_state.last_seen if x["item"].lower() != key]
    st.session_state.last_seen.insert(0, {
        "item": item[:1].upper() + item[1:],
        "where": where,
        "room": room,
        "time": time_label,
        "held": held,
    })
    st.session_state.last_seen = st.session_state.last_seen[:10]


def log_event(text: str, time_label: str | None = None):
    st.session_state.what_happened.insert(0, {"time": time_label or clock(), "event": text})
    st.session_state.what_happened = st.session_state.what_happened[:8]


def draw_corner_brackets(image: Image.Image, objects: list[DetectedObject]) -> Image.Image:
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
        accent = (168, 71, 26) if obj.label.lower() in ("person", "man", "woman", "people") else (15, 94, 107)
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
        label_text = f" {obj.label.capitalize()} "
        bbox = draw.textbbox((0, 0), label_text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        ly = y1 - th - 14 if y1 - th - 14 > 4 else y1 + 6
        draw.rounded_rectangle([x1, ly, x1 + tw + 10, ly + th + 10], radius=8, fill=accent, outline=(255, 255, 255), width=2)
        draw.text((x1 + 5, ly + 3), label_text, fill=(255, 255, 255), font=font)
    return canvas


def full_room_scan(img: Image.Image, room: str, time_label: str):
    """Gemini 'look closely': finds small things the live detector can't (keys, glasses, pills, wallet)."""
    detect_prompt = (
        f"You are a spatial memory detector helping someone with dementia in the {room}. "
        "Identify up to 8 important everyday objects or people visible in this image "
        "(such as: person, water bottle, keys, phone, glasses, pill bottle, pill organizer, mug, remote, wallet). "
        "For each item return:\n"
        "- label: simple 1-2 word lowercase noun (e.g., 'person', 'bottle', 'keys', 'glasses')\n"
        "- where_it_is: short plain-English location (e.g., 'on the wooden counter', 'next to the sink')\n"
        "- box_2d: bounding box [ymin, xmin, ymax, xmax] scaled 0 to 1000.\n"
        "Also set person_present=true if a person is visible, and event_summary to a short reassuring note."
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[img, detect_prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FrameAnalysis,
        ),
    )
    analysis = response.parsed
    st.session_state.annotated_img = draw_corner_brackets(img, analysis.objects)
    for obj in reversed(analysis.objects):
        if obj.label.lower() != "person":
            remember_item(obj.label, obj.where_it_is, room, time_label)
    log_event(f"{analysis.event_summary} ({room})", time_label)


def process_camera_events(payload: dict, room: str):
    """Turn live-camera events into LAST SEEN / WHAT HAPPENED notes."""
    if not payload:
        return
    st.session_state.visible_now = payload.get("visible", [])
    st.session_state.camera_on = bool(payload.get("camera_on"))

    for ev in sorted(payload.get("events", []), key=lambda e: e.get("id", 0)):
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
            held = bool(ev.get("held"))
            rough = ev.get("position", "in view")
            where = f"in someone's hand, {rough}" if held else rough
            item_name = label
            img = data_url_to_image(ev["snapshot"]) if ev.get("snapshot") else None
            if img is not None and time.time() - st.session_state.gemini_last_call > GEMINI_MIN_GAP_S:
                st.session_state.gemini_last_call = time.time()
                loc = describe_item_location(img, label, ev.get("box", [0, 0, 1000, 1000]), ev_room, held)
                if loc:
                    where, item_name = loc.where_it_is, loc.item_name or label
            remember_item(item_name, where, ev_room, t, held)
            if kind == "placed":
                log_event(f"{item_name.capitalize()} was put down {where} ({ev_room})", t)
            else:
                verb = "was carried out of view" if held else "went out of view"
                log_event(f"{item_name.capitalize()} {verb} ({ev_room})", t)
        elif kind == "scan":
            img = data_url_to_image(ev.get("snapshot", ""))
            if img is not None:
                try:
                    full_room_scan(img, ev_room, t)
                except Exception as e:
                    log_event("Could not take a closer look just now. Please try again.", t)
                    print("Gemini scan failed:", e)

        # mark done immediately (before any further st.* call) so a rerun can't repeat it
        st.session_state.processed_ids.add(ev_id)
        st.session_state.ack = max(st.session_state.ack, ev_id)


def answer_spatial_question(question: str):
    if not st.session_state.last_seen and len(st.session_state.what_happened) <= 1:
        ans = "I haven't seen anything yet. Turn on the camera and show me around the room."
    else:
        seen_lines = [
            f"- {x['item']}: {x['where']} in the {x['room']} at {x['time']}"
            for x in st.session_state.last_seen
        ]
        event_lines = [f"- {e['time']}: {e['event']}" for e in st.session_state.what_happened]
        now_lines = ", ".join(v["label"] + (" (in hand)" if v.get("held") else "") for v in st.session_state.visible_now)
        prompt = (
            "You are Rewind, a calm, reassuring memory helper for someone living with dementia or Alzheimer's. "
            "Answer their question using ONLY the notes below. Use 1-2 short, warm, simple sentences. "
            "Say the place first, then the time. Never blame or correct the person. "
            "If you don't know, say so gently and suggest showing the camera around the room.\n\n"
            f"CURRENT TIME: {clock()}\n"
            f"VISIBLE ON CAMERA RIGHT NOW: {now_lines or 'nothing'}\n\n"
            f"LAST SEEN ITEMS:\n{chr(10).join(seen_lines) if seen_lines else 'None yet'}\n\n"
            f"WHAT HAPPENED:\n{chr(10).join(event_lines)}\n\n"
            f"USER QUESTION: {question}"
        )
        try:
            res = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            ans = res.text.strip()
        except Exception as e:
            print("Gemini answer failed:", e)
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
        payload = live_camera(ack=st.session_state.ack, room=current_room, key="live_cam", default=None)
        process_camera_events(payload, current_room)
    else:
        photo = st.file_uploader("Upload a room photo", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
        if photo is not None and st.button("🔍 Look closely at this photo"):
            with st.spinner("Looking around calmly..."):
                full_room_scan(Image.open(photo).convert("RGB"), current_room, clock())

    if st.session_state.annotated_img is not None:
        st.image(
            st.session_state.annotated_img,
            caption=f"Gemini's closer look — {current_room}",
            width="stretch",
        )

with right_col:
    # RIGHT NOW
    if st.session_state.camera_on:
        chips = "".join(
            f"<span class='now-chip {'person' if v['label'] == 'Person' else ''}'>"
            f"{html.escape(v['label'])}{' · in hand' if v.get('held') else ''}</span>"
            for v in st.session_state.visible_now
        ) or "<p style='margin:0; color:#4A5868 !important;'>Nothing I recognise right now.</p>"
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
                     "put something down, like a bottle or your phone.</p>")
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
            <strong>Nothing is saved permanently.</strong> The live boxes are worked out on this device.
            Only when something is put down, or you press “Look closely”, is one still photo sent to Gemini to describe where it is.
            Notes like <em>“Bottle: on the kitchen counter, 1:54 PM”</em> are erased when you close this tab.
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.write("")
    if st.button("🗑️ Erase memory now"):
        for k in ("last_seen", "annotated_img", "last_answer", "last_audio"):
            st.session_state[k] = defaults[k] if k != "last_seen" else []
        st.session_state.what_happened = [{"time": clock(), "event": "Memory erased"}]
        st.rerun()

# -----------------------------------------------------------------------------
# 6. ASK BAR + ONE-TAP QUICK QUESTIONS + SPOKEN ANSWER
# -----------------------------------------------------------------------------
with st.container(border=True):
    st.markdown("<p class='panel-title'>ASK ABOUT YOUR THINGS</p>", unsafe_allow_html=True)
    q_col1, q_col2 = st.columns([3.5, 1])
    with q_col1:
        user_q = st.text_input("Ask a question", placeholder="Where is my bottle?", label_visibility="collapsed")
    with q_col2:
        ask_pressed = st.button("🔊 Ask")

    chip1, chip2, chip3 = st.columns(3)
    with chip1:
        if st.button("Where is my bottle?"):
            answer_spatial_question("Where is my bottle?")
    with chip2:
        if st.button("Where did I leave my phone?"):
            answer_spatial_question("Where did I leave my phone?")
    with chip3:
        if st.button("Who was here?"):
            answer_spatial_question("Who was here with me, and when?")

    if ask_pressed and user_q.strip():
        answer_spatial_question(user_q.strip())

    if st.session_state.last_answer:
        st.markdown(
            f"<div class='seen-chip' style='margin-top:14px; font-size:23px !important;'>"
            f"<strong>Rewind:</strong> {html.escape(st.session_state.last_answer)}</div>",
            unsafe_allow_html=True,
        )
    if st.session_state.last_audio:
        st.audio(st.session_state.last_audio, format="audio/mp3", autoplay=True)

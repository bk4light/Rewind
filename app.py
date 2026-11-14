from datetime import datetime
from io import BytesIO
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel
from google import genai
from google.genai import types
from gtts import gTTS

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
    .block-container {
        max-width: 1120px;
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }

    /* Warm, low-glare neutral surface + deep charcoal high-contrast text */
    .stApp, [data-testid="stAppViewContainer"] {
        background-color: #F6F3EC !important;
        color: #18222F !important;
    }
    h1, h2, h3, p, label, span, div {
        color: #18222F !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    }
    p, li, label {
        font-size: 19px !important;
        line-height: 1.55 !important;
    }

    /* Top Header Bar */
    .top-header {
        background-color: #FFFFFF;
        border: 2px solid #D8D1C5;
        border-radius: 18px;
        padding: 18px 26px;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 12px;
    }
    .status-pill {
        display: inline-block;
        background-color: #E4F0EE;
        color: #174E4F !important;
        border: 1.5px solid #9EC4C1;
        font-size: 15px !important;
        font-weight: 700 !important;
        padding: 6px 14px;
        border-radius: 999px;
        margin-left: 8px;
    }

    /* Right-hand Memory Cards (LAST SEEN / WHAT HAPPENED / PRIVACY) */
    .panel-card {
        background-color: #FFFFFF;
        border: 2px solid #D8D1C5;
        border-radius: 18px;
        padding: 20px 22px;
        margin-bottom: 16px;
        box-shadow: 0 3px 10px rgba(24, 34, 47, 0.04);
    }
    .panel-title {
        font-size: 14px !important;
        font-weight: 800 !important;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #4A5868 !important;
        margin-bottom: 10px !important;
    }
    .seen-chip {
        background-color: #F2EFE9;
        border-left: 5px solid #1E5C6B;
        border-radius: 10px;
        padding: 10px 14px;
        margin-bottom: 8px;
        font-size: 18px !important;
    }
    .privacy-box {
        background-color: #F9F7F3;
        border: 1.5px solid #D8D1C5;
        border-radius: 16px;
        padding: 18px 20px;
    }

    /* Primary & Quick-Ask Buttons */
    .stButton > button {
        background-color: #1E5C6B !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 14px 20px !important;
        font-size: 19px !important;
        font-weight: 600 !important;
        width: 100%;
    }
    .stButton > button * {
        color: #FFFFFF !important;
    }
    .stButton > button:hover {
        background-color: #164652 !important;
    }

    /* Camera & Inputs */
    [data-testid="stCameraInput"], [data-testid="stFileUploader"] {
        background-color: #FFFFFF !important;
        border: 2px solid #C9C0B1 !important;
        border-radius: 18px !important;
        padding: 12px !important;
    }
    input, select, [data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        color: #18222F !important;
        border: 2px solid #C9C0B1 !important;
        border-radius: 12px !important;
        font-size: 19px !important;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. SESSION MEMORY STATE (IN-MEMORY ONLY — PRIVACY FIRST)
# -----------------------------------------------------------------------------
if "last_seen" not in st.session_state:
    st.session_state.last_seen = []  # list of dicts: {item, location, room, time}
if "what_happened" not in st.session_state:
    st.session_state.what_happened = [
        {"time": datetime.now().strftime("%I:%M %p"), "event": "Memory viewfinder started"}
    ]
if "annotated_img" not in st.session_state:
    st.session_state.annotated_img = None
if "last_answer" not in st.session_state:
    st.session_state.last_answer = None
if "last_audio" not in st.session_state:
    st.session_state.last_audio = None

# -----------------------------------------------------------------------------
# 3. GEMINI STRUCTURED SPATIAL DETECTION SCHEMA
# -----------------------------------------------------------------------------
class DetectedObject(BaseModel):
    label: str
    where_it_is: str
    box_2d: list[int]  # [ymin, xmin, ymax, xmax] normalized 0-1000

class FrameAnalysis(BaseModel):
    objects: list[DetectedObject]
    person_present: bool
    event_summary: str

client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

def draw_corner_brackets(image: Image.Image, objects: list[DetectedObject]) -> Image.Image:
    """Draws high-contrast calm teal corner brackets & labels on detected items."""
    canvas = image.copy().convert("RGB")
    draw = ImageDraw.Draw(canvas)
    w, h = canvas.size
    accent = (30, 92, 107)       # #1E5C6B calm deep teal
    badge_bg = (24, 34, 47)      # #18222F deep charcoal
    text_fg = (255, 255, 255)
    stroke = max(3, int(min(w, h) * 0.006))

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(16, int(h * 0.028)))
    except Exception:
        font = ImageFont.load_default()

    for obj in objects:
        if len(obj.box_2d) != 4:
            continue
        ymin, xmin, ymax, xmax = obj.box_2d
        x1 = int(max(0, min(1000, xmin)) / 1000 * w)
        y1 = int(max(0, min(1000, ymin)) / 1000 * h)
        x2 = int(max(0, min(1000, xmax)) / 1000 * w)
        y2 = int(max(0, min(1000, ymax)) / 1000 * h)
        if x2 <= x1 or y2 <= y1:
            continue

        corner = max(14, int(min(x2 - x1, y2 - y1) * 0.22))
        # Top-left
        draw.line([(x1, y1), (x1 + corner, y1)], fill=accent, width=stroke)
        draw.line([(x1, y1), (x1, y1 + corner)], fill=accent, width=stroke)
        # Top-right
        draw.line([(x2, y1), (x2 - corner, y1)], fill=accent, width=stroke)
        draw.line([(x2, y1), (x2, y1 + corner)], fill=accent, width=stroke)
        # Bottom-left
        draw.line([(x1, y2), (x1 + corner, y2)], fill=accent, width=stroke)
        draw.line([(x1, y2), (x1, y2 - corner)], fill=accent, width=stroke)
        # Bottom-right
        draw.line([(x2, y2), (x2 - corner, y2)], fill=accent, width=stroke)
        draw.line([(x2, y2), (x2, y2 - corner)], fill=accent, width=stroke)

        # Label pill above box
        label_text = f" {obj.label} "
        bbox = draw.textbbox((0, 0), label_text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        ly = max(4, y1 - th - 10)
        draw.rectangle([x1, ly, x1 + tw + 8, ly + th + 6], fill=badge_bg)
        draw.text((x1 + 4, ly + 2), label_text, fill=text_fg, font=font)

    return canvas

def answer_spatial_question(question: str):
    if not st.session_state.last_seen and len(st.session_state.what_happened) <= 1:
        ans = "I haven't scanned the room yet. Take a quick camera snapshot first so I can help you look."
    else:
        seen_lines = [
            f"- {x['item']} ({x['where']}) in the {x['room']} at {x['time']}"
            for x in st.session_state.last_seen
        ]
        event_lines = [f"- {e['time']}: {e['event']}" for e in st.session_state.what_happened]
        prompt = (
            "You are Rewind, a calm, reassuring spatial memory helper for someone living with dementia or Alzheimer's. "
            "Answer their question using ONLY the recent room notes below. Use 1-2 short, warm, clear sentences.\n\n"
            f"LAST SEEN ITEMS:\n{chr(10).join(seen_lines) if seen_lines else 'None yet'}\n\n"
            f"WHAT HAPPENED:\n{chr(10).join(event_lines)}\n\n"
            f"USER QUESTION: {question}"
        )
        res = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
        )
        ans = res.text.strip()

    st.session_state.last_answer = ans
    tts = gTTS(ans, lang="en")
    buf = BytesIO()
    tts.write_to_fp(buf)
    st.session_state.last_audio = buf.getvalue()

# -----------------------------------------------------------------------------
# 4. TOP HEADER
# -----------------------------------------------------------------------------
now_str = datetime.now().strftime("%A, %B %d • %I:%M %p")
st.markdown(f"""
<div class="top-header">
    <div>
        <h1 style="margin:0; font-size:30px !important;">🧭 REWIND LIVE</h1>
        <p style="margin:2px 0 0 0; font-size:18px !important;">Point the camera around. Ask later: <em>"Where is my bottle?"</em> • {now_str}</p>
    </div>
    <div>
        <span class="status-pill">● DETECTOR READY</span>
        <span class="status-pill">GEMINI 2.5 FLASH</span>
    </div>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 5. MAIN TWO-COLUMN VIEWFINDER + MEMORY LOG LAYOUT
# -----------------------------------------------------------------------------
left_col, right_col = st.columns([1.45, 1], gap="large")

with left_col:
    c_room, c_mode = st.columns([1, 1])
    with c_room:
        current_room = st.selectbox(
            "I am in:",
            ["Kitchen", "Living Room", "Bedroom", "Bathroom", "Hallway"],
        )
    with c_mode:
        source_mode = st.radio(
            "Camera source:",
            ["Live Camera", "Upload Photo"],
            horizontal=True,
        )

    frame_file = (
        st.camera_input("Look around the room", label_visibility="collapsed")
        if source_mode == "Live Camera"
        else st.file_uploader("Upload a room photo", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
    )

    if frame_file is not None:
        raw_img = Image.open(frame_file)
        if st.button("🔍 Scan Room & Remember Where Things Are"):
            with st.spinner("Looking around calmly..."):
                detect_prompt = (
                    f"You are a spatial memory detector helping someone with dementia in the {current_room}. "
                    "Identify up to 6 important everyday objects or people visible in this image "
                    "(such as: person, water bottle, keys, phone, glasses, pill bottle, mug, remote, wallet, table). "
                    "For each item return:\n"
                    "- label: simple 1-2 word lowercase noun (e.g., 'person', 'bottle', 'keys', 'glasses')\n"
                    "- where_it_is: short plain-English location (e.g., 'on the wooden counter', 'next to the sink')\n"
                    "- box_2d: bounding box [ymin, xmin, ymax, xmax] scaled 0 to 1000.\n"
                    "Also set person_present=true if a person is visible, and event_summary to a short reassuring note "
                    "(e.g., 'Someone was with you' or 'Scanned the kitchen counter')."
                )
                response = client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=[raw_img, detect_prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=FrameAnalysis,
                    ),
                )
                analysis = response.parsed
                timestamp = datetime.now().strftime("%I:%M %p")

                st.session_state.annotated_img = draw_corner_brackets(raw_img, analysis.objects)

                for obj in analysis.objects:
                    # Update or insert into LAST SEEN
                    st.session_state.last_seen = [
                        x for x in st.session_state.last_seen if x["item"].lower() != obj.label.lower()
                    ]
                    st.session_state.last_seen.insert(0, {
                        "item": obj.label.capitalize(),
                        "where": obj.where_it_is,
                        "room": current_room,
                        "time": timestamp,
                    })
                st.session_state.last_seen = st.session_state.last_seen[:8]

                event_text = "Someone was with you" if analysis.person_present else analysis.event_summary
                st.session_state.what_happened.insert(0, {"time": timestamp, "event": f"{event_text} ({current_room})"})
                st.session_state.what_happened = st.session_state.what_happened[:6]

    if st.session_state.annotated_img is not None:
        st.image(st.session_state.annotated_img, caption=f"Detected objects in {current_room}", use_container_width=True)

with right_col:
    # LAST SEEN CARD
    seen_count = len(st.session_state.last_seen)
    st.markdown(f"""
    <div class="panel-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <p class="panel-title" style="margin:0;">LAST SEEN</p>
            <span style="font-size:15px !important; color:#4A5868 !important;">{seen_count} things remembered</span>
        </div>
    """, unsafe_allow_html=True)

    if not st.session_state.last_seen:
        st.markdown("<p style='margin:8px 0 0 0; color:#4A5868 !important;'>Nothing yet. Take a photo or scan the room to remember where items are.</p>", unsafe_allow_html=True)
    else:
        for entry in st.session_state.last_seen:
            st.markdown(
                f"<div class='seen-chip'><strong>{entry['item']}:</strong> {entry['where']} "
                f"<span style='font-size:15px !important; color:#4A5868 !important;'>({entry['room']}, {entry['time']})</span></div>",
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)

    # WHAT HAPPENED CARD
    st.markdown("""
    <div class="panel-card">
        <p class="panel-title">WHAT HAPPENED</p>
    """, unsafe_allow_html=True)
    for ev in st.session_state.what_happened:
        st.markdown(
            f"<p style='margin:4px 0; font-size:18px !important;'><strong>{ev['time']}</strong> &nbsp; {ev['event']}</p>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    # PRIVACY NOTICE + ERASE BUTTON
    st.markdown("""
    <div class="privacy-box">
        <p style="font-size:16px !important; margin-bottom:12px;">
            <strong>Nothing is saved permanently.</strong> No video or photos are stored on disk.
            Only short text notes like <em>"Bottle: on the kitchen counter, 1:54 PM"</em> are kept in this tab's memory,
            and they are erased when you close it.
        </p>
    </div>
    """, unsafe_allow_html=True)
    if st.button("🗑️ Erase memory now"):
        st.session_state.last_seen = []
        st.session_state.what_happened = [{"time": datetime.now().strftime("%I:%M %p"), "event": "Memory erased"}]
        st.session_state.annotated_img = None
        st.session_state.last_answer = None
        st.session_state.last_audio = None
        st.rerun()

# -----------------------------------------------------------------------------
# 6. BOTTOM ASK BAR + ONE-TAP QUICK CHIPS + SPOKEN AUDIO
# -----------------------------------------------------------------------------
st.markdown("<div class='panel-card'><p class='panel-title'>ASK ABOUT YOUR ITEMS</p>", unsafe_allow_html=True)

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
    if st.button("Where are my keys?"):
        answer_spatial_question("Where are my keys?")

if ask_pressed and user_q.strip():
    answer_spatial_question(user_q.strip())

if st.session_state.last_answer:
    st.markdown(
        f"<div class='seen-chip' style='margin-top:14px; font-size:21px !important;'><strong>Rewind:</strong> {st.session_state.last_answer}</div>",
        unsafe_allow_html=True,
    )
if st.session_state.last_audio:
    st.audio(st.session_state.last_audio, format="audio/mp3", autoplay=True)

st.markdown("</div>", unsafe_allow_html=True)

# Rewind 🧭: a calm memory companion for people living with dementia

**Built with the Google Gemini API** · developed and hosted in **Coder** · Emory Hacks 2026

Rewind is a gentle helper for someone living with Alzheimer's or dementia. It greets them by name and reminds them they are safe at home. A live camera keeps track of everyday things (*"Glasses · on the table"*, *"Bottle · in hand"*), so they can ask *"Where are my glasses?"* and hear a short, kind answer. It also tracks pills, announces appointments with a chime and a calm voice, and has one big button to call a family member.

---

## ✨ How we use Gemini

Gemini is the "understanding" layer of Rewind. Every Gemini call is in [`app.py`](app.py) and goes through one helper, `gemini()`.

| Feature | What Gemini does | Gemini features used |
|---|---|---|
| **Camera look-ins** (`look_at_scene`) | Looks at one still photo from the live camera and returns each person and item, whether it's **in someone's hand, on a surface, being worn or on the floor**, a short place label (*"on the couch"*), a landmark description (*"on the coffee table, next to the lamp"*) and a bounding box | Multimodal **image understanding** + **structured JSON output** (`response_schema=SceneAnalysis`) + **spatial bounding boxes** |
| **Ask Rewind** (`answer_spatial_question`) | Answers *"Where is my bottle?"*, *"Did I take my pills?"* or *"What's next today?"* using the **current camera image**, the memory log and the pill/reminder schedule, in 1–2 warm sentences (then read aloud) | Multimodal reasoning over image + text context |
| **Reminders in your own words** (`parse_reminder`) | Turns *"dentist with Dr. Lee next Tuesday at 2"* into a real reminder: date, time, repeat, early warning, a spoken message and a confirmation | **Structured output** (`response_schema=ParsedReminder`) + date/time reasoning |
| **Look closely / photo upload** | Finds small items that the on-device detector can't (keys, glasses, pills, wallet, hearing aid) and draws them on the photo | Image understanding + bounding boxes |

**Built to be reliable and free-tier friendly:**
- **Automatic model fallback:** `gemini-3.5-flash-lite → gemini-3.1-flash-lite → gemini-3.8-flash → gemini-3.6-flash`. If a model hits its quota, Rewind quietly switches to the next one, so the person never sees an error.
- **Event-driven calls:** a fast on-device detector (TensorFlow.js) watches the video, and Rewind only asks Gemini to look **when something changes** (an item is picked up or put down, someone arrives), plus a slow heartbeat. That's about 3–8 calls a minute instead of a constant stream.
- **Graceful offline mode:** if Gemini is unavailable, Ask still answers from memory and reminders still parse with a simple backup parser.
- **Privacy:** the API key stays on the server (never in the browser or in git), video is never uploaded (only an occasional still photo), and memory notes are erased when the tab closes.

## 🏗 How it works

```
Browser (on the user's device)                   Streamlit server (in a Coder workspace)
───────────────────────────────                  ───────────────────────────────────────
Live camera + TensorFlow.js COCO-SSD             app.py
  • moving boxes for people and things   ──────▶   • Gemini look-ins → in hand / on table / where
  • notices "picked up / put down"   still photo   • Last seen · What happened · Right now
Reminder alerts (chime + voice + notification)     • Ask Rewind (Gemini) → spoken answer (gTTS)
                                       ◀──────   reminders.py → pills, appointments, alerts
                                       schedule    caregiver_profile.json (family settings)
```

## 💛 Designed for dementia
- Large text, plain words, one action per button, and a big clock with the day and date.
- A warm, low-glare background with high-contrast text.
- Only two box colours that stay distinct for older eyes: **terracotta = people**, **teal = things**. No red, so nothing feels like an alarm.
- Nothing flashes: boxes fade in gently and only after the item has been seen steadily for a moment.
- Reassurance first: *"Good evening, Eleanor. You are safe. You are at home."*
- Answers say the place first, then the time, and never blame the person.

## ▶️ Run it

### In Coder (how we built it)
1. Create a workspace from this repo (`.devcontainer/` is included).
2. `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
3. `echo 'GEMINI_API_KEY = "YOUR_KEY"' > .streamlit/secrets.toml` (get a free key at [aistudio.google.com](https://aistudio.google.com))
4. `streamlit run app.py`, then open port **8501** from the Coder dashboard (https, so the camera works).

Optional settings in `secrets.toml`: `GEMINI_MODEL` (first model to try), `REWIND_TIMEZONE` (default `America/New_York`), `REWIND_LOOK_EVERY_S` (heartbeat, default 25).

## 📁 Files
- `app.py`: the app, including every Gemini call
- `reminders.py`: pills, appointments, alerts and the backup reminder parser
- `components/live_camera/`: the on-device live camera, tracker and overlay
- `components/alerts/`: the reminder banner with chime, voice and notifications
- `caregiver_profile.json`: name, family contact, pill times and reminders (sample data)

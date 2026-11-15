# Rewind 🧭: a calm memory companion for people living with dementia

**Powered by the Google Gemini API** · built with **Claude** as our AI coding partner · developed in **Coder** · deployed on **Streamlit Community Cloud** · Emory Hacks 2026

### 👉 [Try Rewind live](https://YOUR-APP-NAME.streamlit.app)

Rewind is a gentle, always-on helper for someone living with Alzheimer's or dementia:

- **Greets them by name and reassures them:** *"Good evening, Eleanor. You are safe. You are at home. Sarah is coming to see you at 4:00 PM."*
- **Keeps track of everyday things** with a live camera: *"Glasses · on the table"*, *"Bottle · in hand"*, *"Person · sitting on the couch"*.
- **Answers questions kindly and out loud:** *"Where are my glasses?"*, *"Did I take my pills?"*, *"What's next today?"*
- **Tracks pills:** *"You already took your morning pills at 8:12 AM. 1 left today: night (8:00 PM)."*
- **Reminds them about appointments and visits** with a big, calm banner, a soft chime, a spoken message and a desktop notification.
- **Lets anyone add a reminder in their own words:** *"dentist with Dr. Lee next Tuesday at 2"* becomes a real, timed reminder.
- **Calls family with one big button:** 📞 *Call Sarah*.

---

## ✨ How we use Gemini (inside the app)

Gemini is Rewind's "understanding" layer. Every Gemini call is in [`app.py`](app.py) and goes through one helper, `gemini()`.

| Feature | What Gemini does | Gemini features used |
|---|---|---|
| **Camera look-ins** (`look_at_scene`) | Looks at one still photo from the live camera and returns each person and item, whether it's **in someone's hand, on a surface, being worn or on the floor**, a short place label (*"on the couch"*), a landmark description (*"on the coffee table, next to the lamp"*) and a bounding box | Multimodal **image understanding** + **structured JSON output** (`response_schema=SceneAnalysis`) + **bounding boxes** |
| **Ask Rewind** (`answer_spatial_question`) | Answers questions using the **current camera image**, the memory log and the pill/reminder schedule, in 1–2 warm sentences that are then read aloud | Multimodal reasoning over image + text |
| **Reminders in your own words** (`parse_reminder`) | Turns everyday sentences into a real reminder: date, time, repeat, early warning, a spoken message and a confirmation | **Structured output** (`response_schema=ParsedReminder`) + date/time reasoning |
| **Look closely / photo upload** | Finds small items the on-device detector can't (keys, glasses, pills, wallet, hearing aid) and draws them on the photo | Image understanding + bounding boxes |

**Built to be reliable and free-tier friendly:**
- **Automatic model fallback:** `gemini-3.5-flash-lite → gemini-3.1-flash-lite → gemini-3.8-flash → gemini-3.6-flash`. If one model hits its quota, Rewind quietly switches to the next, so the person never sees an error.
- **Event-driven calls:** a fast on-device detector watches the video, and Rewind only asks Gemini to look **when something changes** (an item is picked up or put down, someone arrives), plus a slow heartbeat. That's about 3–8 calls a minute instead of a constant stream.
- **Graceful offline mode:** if Gemini is unavailable, Ask still answers from memory and reminders still parse with a simple built-in parser.

## 🤖 How we built it (Claude + Coder)

- **Claude (Anthropic)** was our AI pair programmer. We described what a person with dementia needs, and Claude helped design and write the code: the live camera and object tracker, the dementia-friendly interface, the Gemini prompts and model fallback, pills and reminders with alerts, and the call button. It also helped us test and debug as we went. Earlier prototypes were drafted with help from Gemini.
- **Coder** was our development environment. We edited, ran and pushed the project from a Coder cloud workspace (VS Code connected to Coder), and a [`.devcontainer`](.devcontainer/devcontainer.json) is included so anyone can open the repo in Coder.
- **Streamlit Community Cloud** hosts the live app and redeploys automatically on every push to `main`.

## 🏗 How it works

```
Browser (on the user's device)                   Streamlit app (Streamlit Cloud / Coder)
───────────────────────────────                  ───────────────────────────────────────
Live camera + TensorFlow.js COCO-SSD             app.py
  • moving boxes for people and things   ──────▶   • Gemini look-ins → in hand / on table / where
  • notices "picked up / put down"   still photo   • Right now · Last seen · What happened
Reminder banner (chime + voice + notification)     • Ask Rewind (Gemini) → spoken answer (gTTS)
📞 Call button (opens the phone app)   ◀──────   reminders.py → pills, appointments, alert times
                                       schedule    caregiver_profile.json → names, phone, reminders
```

## 💛 Designed for dementia

- Large text, plain words, one action per button, and a big clock with the day and date.
- Reassurance first, in a warm, low-glare palette with high-contrast text.
- Only two box colours that stay distinct for older eyes: **terracotta = people**, **teal = things**. No red, so nothing feels like an alarm.
- Nothing flashes: boxes fade in gently and only after the item has been seen steadily for a moment.
- Slow, short spoken phrases. Answers say the place first, then the time, and never blame the person.
- Reminder banners offer just two choices: **✅ Done** or **⏰ Remind me in 10 minutes**.

## 🔒 Privacy

- The Gemini API key stays on the server: never in the browser, never in git.
- Video is never uploaded. The live boxes are computed on the user's device, and only an occasional still photo is sent to Gemini.
- Camera memory notes are kept only for the browser session. Only reminders and family settings are saved.

## ▶️ Run it yourself

1. `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
2. `echo 'GEMINI_API_KEY = "YOUR_KEY"' > .streamlit/secrets.toml` (get a free key at [aistudio.google.com](https://aistudio.google.com))
3. `streamlit run app.py`
   - **In Coder:** open port **8501** from the Coder dashboard.
   - **On Streamlit Cloud:** add the same key under **Settings → Secrets**.

Optional settings: `GEMINI_MODEL` (first model to try), `REWIND_TIMEZONE` (default `America/New_York`), `REWIND_LOOK_EVERY_S` (heartbeat, default 25).

Family details (name, who to call, phone number, pill times, reminders) can be changed in the app under **👪 For family**.

## 📁 Files

| File | What it is |
|---|---|
| `app.py` | The Streamlit app: greeting, call button, camera, memory, Ask, and every Gemini call |
| `reminders.py` | Pills, appointments, alert scheduling and the backup reminder parser |
| `components/live_camera/` | On-device live camera, object tracker and calm overlay |
| `components/alerts/` | Reminder banner with chime, voice and notifications |
| `caregiver_profile.json` | Sample family settings, pills and reminders |
| `.devcontainer/` | One-click setup for Coder |

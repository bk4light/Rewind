# Rewind 🧭

A calm, live "memory camera" for people living with Alzheimer's and dementia.
Point a camera at the room and Rewind **boxes and names people and things in real time**
("Person", "Bottle · in hand"), says them out loud, and **remembers where things were put down**,
so later you can ask *"Where is my bottle?"* and hear a short, kind answer.

## How it works

| Part | What it does | Where it runs |
|---|---|---|
| Live detector (`components/live_camera/`) | TensorFlow.js COCO-SSD finds people, bottles, cups, phones, remotes, books, glasses… ~10–20 times a second, tracks each one, and works out "in hand", "put down" and "went out of view" | In the browser, on the user's device (no video is uploaded) |
| Gemini (`app.py`) | When an item is put down, one still photo goes to Gemini, which describes the place in human words ("on the kitchen counter, next to the sink"). **Look closely** asks Gemini to find small things the live model can't (keys, glasses, pills). Gemini also answers questions. | Streamlit server |
| Memory panel | RIGHT NOW · LAST SEEN · WHAT HAPPENED, kept only in the browser session | Streamlit |

### Dementia-friendly design
- Large text (19–32px), plain words, one action per button, a large clock with day and date.
- Warm off-white background (less glare) and dark charcoal text for high contrast.
- Only **two** box colours, chosen to stay easy to tell apart for older eyes: **terracotta = people**, **deep teal = things**. No red (it feels like an alarm).
- Every box has a white halo, so it shows up in both dark and bright rooms. Each label has an icon and a word.
- **Nothing flashes**: a box only appears after the item has been seen for a few frames, then fades in and out gently.
- Slow, short spoken phrases, with a cooldown so the same thing isn't repeated. One tap turns the voice off.
- Answers say the place first, then the time, and never blame the person.

## Run it

### In Coder (recommended for the hackathon)
1. Create a workspace from this repo (the `.devcontainer/` installs Python deps + the Entire CLI).
2. Add your key: `mkdir -p .streamlit && echo 'GEMINI_API_KEY = "YOUR_KEY"' > .streamlit/secrets.toml`
   (or set `GEMINI_API_KEY` as a workspace environment variable).
3. `streamlit run app.py`
4. Open port **8501** from the Coder dashboard (or `coder port-forward <workspace> --tcp 8501` and visit `http://localhost:8501`).
   The camera only works over **https** or **localhost**, and both of these are.

### Locally
```bash
pip install -r requirements.txt
echo 'GEMINI_API_KEY = "YOUR_KEY"' > .streamlit/secrets.toml
streamlit run app.py
```

Optional settings (secrets.toml or env vars): `GEMINI_MODEL` (default `gemini-3.8-flash`), `REWIND_TIMEZONE` (default `America/New_York`).
Cloud workspaces run in UTC, so the timezone setting keeps the clock right for the person using the app.

## Entire
Entire is enabled in this repo (`.entire/`, plus hooks in `.claude/` and `.agents/`). Each AI coding session is saved as a checkpoint
when you commit, so judges can see how Rewind was built: `entire status`, then commit and push as usual.

## Demo script (60 seconds)
1. Press **Start camera**. Walk in and you'll see the orange box and hear "Person".
2. Pick up a water bottle: **"Bottle · in hand"**.
3. Put it on the counter and step away. After 3 seconds, LAST SEEN shows *"Bottle: on the kitchen counter…"*.
4. Press **Where is my bottle?**: you hear *"Your bottle is on the kitchen counter, next to the sink. You put it there at 2:14 PM."*
5. Press **Look closely** to find keys or glasses.

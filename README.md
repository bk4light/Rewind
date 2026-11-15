# Rewind — An AI-Powered Memory Companion for People Living with Dementia

**Emory Hacks 2026 | Google Gemini API | Claude | Coder | Streamlit Community Cloud**

### [Try Rewind Live](https://YOUR-APP-NAME.streamlit.app)

## About Rewind

Imagine waking up and not remembering what day it is, where you left your glasses, or whether you've already taken your medication. For millions of people living with Alzheimer's or dementia, situations like these are part of everyday life.

We created **Rewind** to make those moments a little less overwhelming.

Rewind is an AI-powered memory companion that helps people living with dementia stay connected to their surroundings, manage daily routines, and feel more confident at home.

Instead of expecting users to remember everything, Rewind remembers the little things for them.

It uses a live camera to track everyday objects, answers questions in simple language, provides medication and appointment reminders, and makes it easier to reach family members when needed.

Most importantly, we wanted Rewind to feel less like complicated technology and more like a familiar, reassuring presence.

## What Rewind Can Do

### 1. A Familiar and Reassuring Welcome

Rewind greets users by name and provides useful information about their day.

For example:

*"Good evening, Eleanor. You are safe. You are at home. Sarah is coming to visit you at 4:00 PM."*

These small reminders can help someone feel more comfortable and oriented in their surroundings.

### 2. Real-Time Object Tracking

Misplacing everyday belongings can be especially frustrating for someone experiencing memory loss.

Rewind uses a live camera and object detection to recognize people and objects in the user's environment.

It can identify situations such as:

- Glasses on the table
- A water bottle being held
- A person sitting on the couch
- An object being picked up or placed down

The application maintains a temporary record of where objects were last seen, helping users find their belongings without having to search repeatedly.

### 3. Ask Rewind — Your Everyday Memory Assistant

We wanted interacting with Rewind to be as simple as asking someone a question.

Users can ask:

- "Where are my glasses?"
- "Did I take my morning pills?"
- "What do I have planned today?"

Rewind uses Gemini to understand the question, check the available information, and respond in one or two short sentences.

For example:

*"Your glasses were last seen on the coffee table, next to the lamp."*

Answers can also be spoken aloud, making the experience easier for users who may struggle with reading or navigating screens.

### 4. Medication Tracking

Remembering whether medication has already been taken can be challenging.

Rewind helps users keep track of their medication schedule and recorded doses.

For example:

*"Your morning medication was marked as taken at 8:12 AM. Your next scheduled dose is at 8:00 PM."*

This feature helps users review their medication records without relying entirely on memory.

### 5. Smart Reminders and Appointments

Rewind allows users to create reminders using everyday language.

Instead of filling out multiple fields, someone can simply enter:

*"Dentist appointment with Dr. Lee next Tuesday at 2 PM."*

Gemini interprets the request and creates a structured reminder with the appropriate date, time, and notification details.

When it's time, Rewind displays a large reminder banner, plays a gentle chime, and reads the message aloud.

Users can choose to mark the reminder as **Done** or ask to be reminded again in **10 minutes**.

### 6. One-Button Family Contact

Sometimes, the most helpful thing is being able to reach someone familiar.

Rewind includes a large, clearly labeled button that opens the device's calling application with a designated family member's phone number.

This makes contacting a loved one easier without navigating multiple screens.

## How We Use Google Gemini

Google Gemini is at the center of Rewind's AI functionality.

While TensorFlow.js handles basic object detection directly in the browser, Gemini helps the application understand the context behind what the camera sees.

All Gemini API requests are managed through a centralized `gemini()` helper in `app.py`.

| Feature | How Gemini Helps |
|---|---|
| Camera Analysis | Examines camera snapshots to identify people, objects, and their locations |
| Spatial Understanding | Determines whether objects are being held, worn, placed on furniture, or lying on the floor |
| Ask Rewind | Combines camera information, object history, and reminders to answer questions |
| Natural-Language Reminders | Converts everyday sentences into structured reminders with dates and times |
| Detailed Object Search | Helps locate smaller items such as keys, glasses, wallets, and hearing aids |

### Making Gemini More Efficient

One challenge we considered was how to use AI continuously without making unnecessary API requests.

Instead of sending every camera frame to Gemini, Rewind uses **TensorFlow.js and COCO-SSD** to monitor the environment locally.

When the system detects a meaningful change, such as someone picking up an object or placing it down, it can send a still image to Gemini for further analysis.

Periodic check-ins help keep the object's last-known location updated.

We also implemented automatic model fallback. If a configured Gemini model reaches its quota or becomes unavailable, Rewind attempts another supported model.

If Gemini cannot be reached, the application can still use previously recorded information and a basic reminder parser.

## How We Built Rewind

We developed Rewind during **Emory Hacks 2026**, combining AI-assisted development with cloud-based tools.

### Claude — Our AI Coding Partner

We used Claude by Anthropic as an AI pair programmer throughout development.

We started by thinking about the everyday challenges someone living with dementia might experience. From there, Claude helped us translate our ideas into working features.

It assisted with developing the camera tracking system, designing the accessible interface, integrating Gemini, implementing medication reminders, and debugging the application.

We also explored earlier prototypes with help from Gemini.

### Coder — Our Development Environment

We used Coder as our cloud-based development environment.

Through a VS Code-connected Coder workspace, we could write, run, test, and push our code without depending on a specific local machine.

The repository also includes a `.devcontainer/` configuration to make setting up the development environment easier.

### Streamlit Community Cloud — Deployment

We built the user interface using Streamlit and deployed the application through Streamlit Community Cloud.

The deployment is connected to our GitHub repository, allowing the application to redeploy when updates are pushed to the `main` branch.

## Tech Stack

| Technology | Purpose |
|---|---|
| Python | Application logic and backend functionality |
| Streamlit | User interface and web application |
| Google Gemini API | Image understanding, spatial reasoning, and natural-language processing |
| TensorFlow.js | Browser-based object detection |
| COCO-SSD | Recognizing common objects and people |
| gTTS | Converting responses into speech |
| Claude | AI-assisted development and debugging |
| Coder | Cloud development environment |
| Streamlit Community Cloud | Application deployment |
| JSON | Caregiver settings, reminders, and structured AI responses |

## How Rewind Works

Rewind combines real-time object detection with AI reasoning and a lightweight memory system.

**Step 1 — Observe**

The browser uses the device's camera and TensorFlow.js to detect everyday objects and people.

**Step 2 — Detect Changes**

The application watches for meaningful changes, such as objects being moved or picked up.

**Step 3 — Understand**

Selected camera snapshots are analyzed by Gemini to identify object locations, nearby landmarks, and spatial relationships.

**Step 4 — Remember**

Rewind updates its temporary memory with information about where objects were last seen and what changed.

**Step 5 — Respond**

When a user asks a question, Gemini combines the current camera image, memory records, and reminder information to generate a short response.

**Step 6 — Assist**

The application reads answers aloud, displays reminders, and provides quick access to family contact information.

## Designed With Accessibility in Mind

We believe technology should adapt to the person using it, not the other way around.

Because Rewind is intended for people living with dementia, we focused on creating an interface that feels calm, familiar, and easy to understand.

Some of our design choices include:

- Large text and clearly labeled buttons.
- A prominent clock showing the day, date, and time.
- Simple language without unnecessary technical terms.
- Warm backgrounds and high-contrast text.
- Terracotta highlights for people and teal highlights for objects.
- Gentle transitions instead of flashing animations.
- Short, slowly spoken responses.
- Reminder notifications with only two clear actions.

We also paid attention to the language Rewind uses.

Rather than making users feel embarrassed about forgetting something, the application responds patiently and provides reassurance.

For us, accessibility wasn't just about making buttons bigger. It was about creating an experience that respects the person using it.

## Privacy and Reliability

Privacy was an important consideration because Rewind interacts with a user's personal surroundings.

We designed the application with the following protections:

- **Server-side API credentials:** The Gemini API key is stored securely on the server rather than in browser code or GitHub.
- **Local video processing:** Live object detection runs in the browser.
- **Selective image analysis:** Only occasional still images are sent to Gemini, rather than continuous video.
- **Temporary camera memory:** Object-location notes are retained only for the active browser session.
- **Separate caregiver settings:** Family contacts, medication schedules, and reminders are managed separately from temporary camera records.

We also included fallback functionality so that previously recorded information and basic reminder features can remain available when Gemini is unavailable.

**Note:** Rewind is a hackathon prototype intended to demonstrate assistive technology. It is not a medical device and should not replace professional care, medication verification, or emergency assistance.

## Getting Started

### Prerequisites

Before running Rewind, make sure you have:

- Python 3 installed.
- A Google Gemini API key.
- A compatible browser with camera permissions.
- A local Python environment or Coder workspace.

### Installation

**1. Clone the repository**

```bash
git clone <YOUR_REPOSITORY_URL>
cd <YOUR_REPOSITORY_FOLDER>
```

**2. Create and activate a virtual environment**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

For Windows:

```powershell
.venv\Scripts\activate
```

**3. Install the required dependencies**

```bash
pip install -r requirements.txt
```

**4. Configure your Gemini API key**

Create a file named `.streamlit/secrets.toml` and add:

```toml
GEMINI_API_KEY = "YOUR_API_KEY"
```

You can generate an API key through [Google AI Studio](https://aistudio.google.com).

Make sure your secrets file is excluded from Git.

**5. Run the application**

```bash
streamlit run app.py
```

If you're using Coder, open port `8501` from your workspace dashboard.

For Streamlit Community Cloud, add the API key under **Settings → Secrets**.

### Optional Configuration

You can also customize the following settings:

```toml
REWIND_TIMEZONE = "America/New_York"
REWIND_LOOK_EVERY_S = 25
```

- `GEMINI_MODEL` — Selects the first Gemini model to attempt.
- `REWIND_TIMEZONE` — Sets the timezone for reminders.
- `REWIND_LOOK_EVERY_S` — Controls periodic camera analysis.

Family contact information, medication times, and reminders can be updated through the **For Family** section of the application.

## Project Structure

```text
Rewind/
├── app.py
├── reminders.py
├── caregiver_profile.json
├── requirements.txt
├── .devcontainer/
│   └── devcontainer.json
├── components/
│   ├── live_camera/
│   └── alerts/
└── README.md
```

| File | Description |
|---|---|
| `app.py` | Main Streamlit application, Gemini integration, camera analysis, memory, and question answering |
| `reminders.py` | Medication tracking, appointment reminders, scheduling, and backup parsing |
| `components/live_camera/` | Browser-based camera, object detection, tracking, and visual overlays |
| `components/alerts/` | Reminder banners, chimes, spoken messages, and notifications |
| `caregiver_profile.json` | Sample family information, medication schedules, and reminder settings |
| `.devcontainer/` | Development environment configuration for Coder |

## What We Hope to Improve

Rewind started as a hackathon project, but we see opportunities to make it more useful and accessible.

Some features we'd like to explore include:

- Tracking objects across multiple rooms.
- Supporting more languages and personalized voices.
- Improving recognition of smaller everyday objects.
- Adding more reliable caregiver notifications.
- Expanding offline functionality.
- Conducting usability testing with caregivers and people living with dementia.
- Strengthening privacy controls for sensitive camera information.

## Why This Project Matters to Us

When we started brainstorming ideas for Emory Hacks, we wanted to build something that could make a meaningful difference in someone's everyday life.

We kept coming back to one question:

**What if AI could help someone feel a little more independent, even when their memory becomes unreliable?**

That question became Rewind.

We know an application cannot replace the comfort of a loved one, the support of a caregiver, or the importance of human connection.

But if it can help someone find their glasses without feeling frustrated, remember an appointment without feeling anxious, or reach a family member with a single button, we believe that's a meaningful start.

**Rewind is our attempt to make technology a little more human, one reminder at a time.**

---

**Developed for Emory Hacks 2026.**

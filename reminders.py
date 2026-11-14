"""Reminders, pills and family settings for Rewind.

Everything is stored in caregiver_profile.json so it is still there after a restart.
(Camera photos are never saved — only these reminders and settings.)
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PROFILE_PATH = Path(__file__).parent / "caregiver_profile.json"
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def nice_time(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def _hm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


# -----------------------------------------------------------------------------
# Load / save
# -----------------------------------------------------------------------------
def load_profile(tz: ZoneInfo) -> dict:
    try:
        p = json.loads(PROFILE_PATH.read_text())
    except Exception:
        p = {}
    changed = False
    today = datetime.now(tz).date()

    defaults = {
        "patient_name": "Eleanor",
        "caregiver_name": "Sarah (Daughter)",
        "caregiver_phone": "(404) 555-0194",
        "home_note": "You are safe. You are at home.",
        "daily_notes": "",
        "recent_logs": [],
    }
    for k, v in defaults.items():
        if k not in p:
            p[k] = v
            changed = True

    if "meds" not in p:
        p["meds"] = [
            {"id": "morning", "name": "Morning pills", "time": "08:00",
             "note": "in the blue Monday–Sunday organizer on the kitchen counter"},
            {"id": "afternoon", "name": "Afternoon pills", "time": "13:00", "note": ""},
            {"id": "night", "name": "Night pills", "time": "20:00", "note": ""},
        ]
        changed = True
    p.setdefault("taken", {})

    if "reminders" not in p:
        visit_name = p["caregiver_name"].split(" (")[0]
        p["reminders"] = [
            {"id": "demo-doctor", "title": "Doctor's appointment with Dr. Patel",
             "message": "You have a doctor's appointment with Dr. Patel. Sarah will drive you.",
             "kind": "appointment", "date": (today + timedelta(days=2)).isoformat(), "time": "10:30",
             "repeat": "none", "remind_before_minutes": 120, "done": False},
            {"id": "demo-visit", "title": f"{visit_name} visits",
             "message": f"{visit_name} is coming to visit you at 4 PM.",
             "kind": "visit", "date": today.isoformat(), "time": "16:00",
             "repeat": "daily", "remind_before_minutes": 15, "done": False},
        ]
        changed = True

    if changed:
        save_profile(p)
    return p


def save_profile(p: dict) -> None:
    try:
        PROFILE_PATH.write_text(json.dumps(p, indent=2))
    except Exception as e:  # read-only disk etc. — keep working in memory
        print("Could not save caregiver_profile.json:", e)


# -----------------------------------------------------------------------------
# Words people understand: "today at 3 PM", "in 2 days (Monday, November 16) at 10:30 AM"
# -----------------------------------------------------------------------------
def when_words(dt: datetime, now: datetime) -> str:
    days = (dt.date() - now.date()).days
    t = nice_time(dt)
    if days == 0:
        return f"today at {t}"
    if days == 1:
        return f"tomorrow ({dt.strftime('%A')}) at {t}"
    if days < 7:
        return f"in {days} days ({dt.strftime('%A, %B')} {dt.day}) at {t}"
    return f"on {dt.strftime('%A, %B')} {dt.day} at {t}"


# -----------------------------------------------------------------------------
# Pills
# -----------------------------------------------------------------------------
def med_status(p: dict, now: datetime) -> list[dict]:
    taken_today = p["taken"].get(now.date().isoformat(), {})
    out = []
    for m in sorted(p["meds"], key=lambda m: m["time"]):
        h, mi = _hm(m["time"])
        due = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        taken_at = taken_today.get(m["id"])
        if taken_at:
            state = "taken"
        elif now >= due + timedelta(hours=3):
            state = "missed"
        elif now >= due - timedelta(minutes=30):
            state = "due"
        else:
            state = "later"
        out.append({**m, "due": due, "taken_at": taken_at, "state": state})
    return out


def mark_taken(p: dict, med_id: str, now: datetime) -> None:
    p["taken"].setdefault(now.date().isoformat(), {})[med_id] = nice_time(now)
    # keep only the last 14 days
    for d in sorted(p["taken"])[:-14]:
        p["taken"].pop(d, None)
    save_profile(p)


def undo_taken(p: dict, med_id: str, now: datetime) -> None:
    p["taken"].get(now.date().isoformat(), {}).pop(med_id, None)
    save_profile(p)


def pills_sentence(meds: list[dict]) -> str:
    taken = [m for m in meds if m["state"] == "taken"]
    missed = [m for m in meds if m["state"] == "missed"]
    left = [m for m in meds if m["state"] in ("due", "later")]
    parts = []
    if taken:
        last = taken[-1]
        parts.append(f"You already took your {last['name'].lower()} at {last['taken_at']}.")
    if missed:
        names = [m["name"].lower().replace(" pills", "") for m in missed]
        joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        parts.append(f"Your {joined} pills haven't been marked as taken yet.")
    if left:
        names = [f"{m['name'].lower().replace(' pills', '')} ({nice_time(m['due'])})" for m in left]
        joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        parts.append(f"{len(left)} left today: {joined}.")
    elif not missed:
        parts.append("You have taken all your pills for today. Well done.")
    return " ".join(parts)


# -----------------------------------------------------------------------------
# Reminders
# -----------------------------------------------------------------------------
def next_occurrence(r: dict, now: datetime, tz: ZoneInfo) -> datetime | None:
    try:
        d = date.fromisoformat(r["date"])
        h, mi = _hm(r["time"])
    except Exception:
        return None
    start = datetime(d.year, d.month, d.day, h, mi, tzinfo=tz)
    rep = r.get("repeat", "none")
    if rep == "none":
        return None if r.get("done") else start
    step = timedelta(days=1 if rep == "daily" else 7)
    occ = start
    while occ < now - timedelta(minutes=30):
        occ += step
    return occ


def upcoming(p: dict, now: datetime, tz: ZoneInfo, days: int = 30) -> list[dict]:
    out = []
    for r in p["reminders"]:
        occ = next_occurrence(r, now, tz)
        if occ and now - timedelta(minutes=30) <= occ <= now + timedelta(days=days):
            out.append({**r, "at": occ})
    return sorted(out, key=lambda r: r["at"])


def alert_schedule(p: dict, now: datetime, tz: ZoneInfo) -> list[dict]:
    """Every alert from 3 hours ago to 2 days ahead, as epoch-ms for the browser."""
    alerts = []
    lo, hi = now - timedelta(hours=3), now + timedelta(days=2)

    for m in med_status(p, now):
        for day_offset in (0, 1):
            due = m["due"] + timedelta(days=day_offset)
            if day_offset == 0 and m["state"] == "taken":
                continue
            if lo <= due <= hi:
                note = f" They are {m['note']}." if m.get("note") else ""
                alerts.append({
                    "key": f"med:{m['id']}:{due.date().isoformat()}",
                    "rid": m["id"], "kind": "medicine", "title": f"Time for your {m['name'].lower()}",
                    "message": f"It's time to take your {m['name'].lower()}.{note}",
                    "due_ms": int(due.timestamp() * 1000), "final": True,
                })

    for r in p["reminders"]:
        occ = next_occurrence(r, now, tz)
        if not occ:
            continue
        for k in range(0, 3):  # this and the next couple of repeats
            o = occ if r.get("repeat", "none") == "none" else occ + timedelta(days=k * (1 if r["repeat"] == "daily" else 7))
            if k > 0 and r.get("repeat", "none") == "none":
                break
            before = int(r.get("remind_before_minutes") or 0)
            if before > 0:
                early = o - timedelta(minutes=before)
                if lo <= early <= hi:
                    alerts.append({
                        "key": f"rem:{r['id']}:{early.isoformat()}", "rid": r["id"], "kind": r.get("kind", "other"),
                        "title": f"Coming up at {nice_time(o)}: {r['title']}",
                        "message": f"In {before // 60} hours: {r['message']}" if before >= 120 else
                                   (f"In {before} minutes: {r['message']}" if before < 60 else
                                    f"In one hour: {r['message']}"),
                        "due_ms": int(early.timestamp() * 1000), "final": False,
                    })
            if lo <= o <= hi:
                alerts.append({
                    "key": f"rem:{r['id']}:{o.isoformat()}", "rid": r["id"], "kind": r.get("kind", "other"),
                    "title": r["title"], "message": r["message"],
                    "due_ms": int(o.timestamp() * 1000), "final": True,
                })
    return sorted(alerts, key=lambda a: a["due_ms"])


def add_reminder(p: dict, *, title: str, message: str, kind: str, day: str, time_hm: str,
                 repeat: str = "none", remind_before_minutes: int = 0) -> dict:
    if kind == "medicine" and repeat == "daily":
        med = {"id": "med-" + uuid.uuid4().hex[:6], "name": title, "time": time_hm, "note": ""}
        p["meds"].append(med)
        save_profile(p)
        return med
    r = {"id": uuid.uuid4().hex[:8], "title": title, "message": message, "kind": kind,
         "date": day, "time": time_hm, "repeat": repeat,
         "remind_before_minutes": int(remind_before_minutes), "done": False}
    p["reminders"].append(r)
    save_profile(p)
    return r


def complete_alert(p: dict, alert: dict, now: datetime) -> None:
    """Called when the person presses 'Done' on an alert."""
    if alert.get("kind") == "medicine":
        mark_taken(p, alert["rid"], now)
        return
    if alert.get("final"):
        for r in p["reminders"]:
            if r["id"] == alert["rid"] and r.get("repeat", "none") == "none":
                r["done"] = True
        save_profile(p)


def delete_reminder(p: dict, rid: str) -> None:
    p["reminders"] = [r for r in p["reminders"] if r["id"] != rid]
    p["meds"] = [m for m in p["meds"] if m["id"] != rid]
    save_profile(p)


# -----------------------------------------------------------------------------
# Simple backup parser (used only if Gemini is unavailable)
# "dentist tomorrow at 3pm", "call Sarah on Sunday at 6:30 pm", "take vitamin D every day at 9am"
# -----------------------------------------------------------------------------
def simple_parse(text: str, now: datetime) -> dict | None:
    t = text.lower()
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", t) or re.search(r"\bat (\d{1,2})(?::(\d{2}))?\b", t)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    ampm = (m.group(3) or "") if m.lastindex and m.lastindex >= 3 else ""
    if "p" in ampm and h < 12:
        h += 12
    if "a" in ampm and h == 12:
        h = 0
    if not ampm and h < 8:  # "at 3" most likely means 3 PM
        h += 12
    day = now.date()
    if "tomorrow" in t:
        day += timedelta(days=1)
    else:
        for i, wd in enumerate(WEEKDAYS):
            if wd in t:
                ahead = (i - now.weekday()) % 7 or 7
                day += timedelta(days=ahead)
                break
    repeat = "daily" if re.search(r"every ?day|daily|each day", t) else ("weekly" if "every week" in t else "none")
    kind = ("medicine" if re.search(r"pill|medic|tablet|vitamin", t) else
            "appointment" if re.search(r"doctor|dentist|appointment|clinic|hospital|dr\.?\s", t) else "task")
    title = re.sub(r"\b(remind me to|remind me|please|i have|my)\b", "", text, flags=re.I)
    title = re.sub(r"\b(today|tomorrow|on \w+day|every ?day|daily|at \d.*$|\d{1,2}(:\d{2})?\s*(am|pm).*$)", "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip(" ,.") or text
    title = title[:1].upper() + title[1:]
    when = datetime(day.year, day.month, day.day, h, mi, tzinfo=now.tzinfo)
    if repeat == "none" and when < now:
        when += timedelta(days=1)
    return {
        "title": title, "message": f"Reminder: {title}.", "kind": kind,
        "date": when.date().isoformat(), "time": f"{when.hour:02d}:{when.minute:02d}",
        "repeat": repeat, "remind_before_minutes": 60 if kind == "appointment" else 0,
        "confirmation": (f"Okay. I'll remind you every day at {nice_time(when)}: {title}." if repeat == "daily"
                         else f"Okay. I'll remind you {when_words(when, now)}: {title}."),
    }

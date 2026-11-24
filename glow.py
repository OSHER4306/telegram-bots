"""Glow — opt-in photo rating bot for Telegram (18+, consent only).

People upload their OWN selfie, prove it is them with a live round video, the owner approves it,
and strangers rate it 1-10. To see your score you rate 10 others first (give-to-get), which keeps
the pool of ratings growing. A personal link brings friends in: they rate you first, then join.

Runs as a thread inside the Derby bot process with its own token and its own SQLite file.
Stdlib only.
"""
import json
import math
import random
import sqlite3
import threading
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Jerusalem")
GIVE = 10            # ratings you give before you see your score
MIN_SCORE = 12       # ratings a photo needs before it has a score
PRIOR, PRIOR_W = 6.0, 5.0
TRIM_FROM = 20       # above this many ratings, drop the top and bottom 10%
MAX_PHOTOS = 3
MAX_RATES_DAY = 300
MIN_GAP = 1.2        # seconds between two ratings by one person
REPORT_HIDE = 3      # reports that hide a photo until the owner reviews it
NOTIFY_DAY = 3       # score notifications per user per day
AGE_SPAN = 6         # raters see photos within +-6 years of their own age

SCHEMA = """
CREATE TABLE IF NOT EXISTS gusers(id INTEGER PRIMARY KEY, name TEXT, lang TEXT, state TEXT, year INTEGER,
  gender TEXT, pref TEXT, karma INTEGER DEFAULT 0, ref INTEGER, blocked INTEGER DEFAULT 0, live TEXT,
  last_rate REAL DEFAULT 0, msg INTEGER, joined INTEGER, ref_paid INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS gphotos(id INTEGER PRIMARY KEY AUTOINCREMENT, owner INTEGER, file TEXT,
  status TEXT, created INTEGER, notified INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS gratings(rater INTEGER, photo INTEGER, value INTEGER, friend INTEGER, ts INTEGER,
  day TEXT, PRIMARY KEY(rater, photo));
CREATE TABLE IF NOT EXISTS greports(reporter INTEGER, photo INTEGER, reason TEXT, ts INTEGER, PRIMARY KEY(reporter, photo));
CREATE TABLE IF NOT EXISTS gnotes(user INTEGER, day TEXT, n INTEGER, PRIMARY KEY(user, day));
CREATE TABLE IF NOT EXISTS gmeta(k TEXT PRIMARY KEY, v TEXT);
"""

STATE_HE = {"terms": "לא אישר תנאים", "year": "שנת לידה", "gender": "בחירת מין", "pref": "בחירת העדפה",
            "live": "חסר וידאו אימות", "ready": "פעיל"}

T = {
    "he": {
        "welcome": "✨ <b>Glow — מה הציון האמיתי שלך?</b>\n\nמעלים סלפי, אנשים זרים מדרגים 1–10, ואתה מגלה את הציון שלך ובאיזה אחוזון אתה.\n\n"
                   "📜 <b>הכללים:</b> רק מגיל 18. רק תמונה שלך. בלי עירום. הציון נראה רק לך. אפשר למחוק הכול בכל רגע עם /delete.",
        "agree": "✅ אני מעל 18 ומסכים/ה",
        "year": "באיזו שנה נולדת? (למשל 1998)",
        "year_bad": "כתוב שנה בת 4 ספרות, למשל 1998.",
        "minor": "⛔ Glow מיועד רק למי שמעל גיל 18. אי אפשר להשתמש בבוט.",
        "gender": "אתה/את…",
        "g_m": "👨 גבר", "g_f": "👩 אישה", "g_o": "🌈 אחר",
        "pref": "את מי תרצה/י לדרג?",
        "p_m": "גברים", "p_f": "נשים", "p_a": "את כולם",
        "photo": "📸 שלח סלפי אחד שלך: פנים ברורות, בלי פילטרים כבדים, בלי עירום.\nאפשר גם לדלג ולהתחיל לדרג: /rate",
        "live": "🎥 עכשיו אימות קצר: שלח <b>וידאו עגול</b> של 2–3 שניות (לחיצה ארוכה על המיקרופון ← מצלמה). זה רק בשביל לוודא שזה באמת אתה, ואף אחד מלבד המנהל לא רואה אותו.",
        "live_need": "שלח וידאו עגול (לא תמונה ולא קובץ) כדי לאמת שזה אתה.",
        "pending": "⏳ התמונה בבדיקה ותיכנס לדירוג בקרוב.\nבינתיים: דרג {n} אנשים כדי לפתוח את הציון שלך 👇",
        "approved": "✅ התמונה שלך אושרה ונכנסה לדירוג! תקבל הודעה כשיהיה ציון.",
        "rejected": "❌ התמונה לא אושרה (צריך סלפי ברור שלך, בלי עירום). שלח תמונה אחרת.",
        "full": "יש לך כבר {n} תמונות. כדי להעלות חדשה, מחק אחת: /delete",
        "rate_cap": "🔥 {i}/{n} — כמה תיתן/י?",
        "rate_free": "🔥 כמה תיתן/י?",
        "sample": "🧪 תמונת דוגמה · ",
        "none": "😴 אין כרגע תמונות חדשות לדרג. נסה שוב עוד קצת — ושתף את הקישור שלך כדי שיגיעו עוד: /link",
        "slow": "לאט 🙂",
        "cap": "הגעת למקסימום הדירוגים להיום. נתראה מחר!",
        "unlocked": "🔓 פתחת את הציון שלך! כתוב /me",
        "me_none": "עוד אין לך תמונה בדירוג. שלח סלפי כדי להתחיל.",
        "me_lock": "🔒 דרג עוד {k} אנשים כדי לראות את הציון שלך: /rate",
        "me_wait": "📊 תמונה {i}: {n}/{m} דירוגים — עוד מעט יש ציון.",
        "me_score": "📊 תמונה {i}: <b>{s}</b> ({n} דירוגים){pct}",
        "pct": " · טופ {p}%",
        "me_friends": "\n👥 ממוצע מהחברים שלך: {f}",
        "me_status": "\n⏳ תמונה {i}: {st}",
        "st_pending": "בבדיקה", "st_hidden": "מוסתרת לבדיקה",
        "me_tail": "\n\n📣 שתף את הכרטיס שלך: /card",
        "score_ready": "🎉 יש לך ציון! {s} · כתוב /me לפרטים",
        "score_moved": "✨ {k} אנשים חדשים דירגו אותך: הציון עכשיו {s}",
        "score_locked": "🎉 התמונה שלך קיבלה ציון — דרג עוד {k} אנשים כדי לראות אותו: /rate",
        "link": "🔗 הקישור האישי שלך — מי שנכנס דרכו מדרג אותך קודם:\n{url}",
        "card": "✨ <b>הציון שלי ב-Glow: {s}</b>{pct}\nכמה אתה מקבל? 👇\n{url}",
        "card_none": "עוד אין לך ציון. קודם תמונה ו-{n} דירוגים.",
        "share": "📤 שתף",
        "friend_in": "👋 {name} הזמין/ה אותך. דרג/י אותו/ה קודם, ואז תקבל/י ציון משלך!",
        "ref_paid": "🎁 חבר שהזמנת התחיל לשחק! התמונה שלך תוצג ל-20 אנשים נוספים.",
        "report": "🚩",
        "report_ask": "למה לדווח?",
        "r_minor": "נראה/ית קטין/ה", "r_fake": "זה לא הוא/היא", "r_nsfw": "עירום / לא הולם", "r_other": "אחר",
        "reported": "תודה, הדיווח התקבל.",
        "deleted": "🗑️ כל התמונות, הדירוגים והנתונים שלך נמחקו.",
        "help": "✨ <b>Glow</b>\n/rate — לדרג\n/me — הציון שלי\n/link — הקישור האישי שלי\n/card — כרטיס לשיתוף\n/lang — שפה\n/delete — למחוק הכול",
        "blocked": "⛔ אין גישה לבוט.",
    },
    "en": {
        "welcome": "✨ <b>Glow — what's your real score?</b>\n\nUpload a selfie, strangers rate it 1–10, and you find out your score and your percentile.\n\n"
                   "📜 <b>Rules:</b> 18+ only. Only a photo of you. No nudity. Only you see your score. Delete everything anytime with /delete.",
        "agree": "✅ I'm 18+ and I agree",
        "year": "What year were you born? (e.g. 1998)",
        "year_bad": "Type a 4-digit year, e.g. 1998.",
        "minor": "⛔ Glow is for adults (18+) only. You can't use this bot.",
        "gender": "You are…",
        "g_m": "👨 Man", "g_f": "👩 Woman", "g_o": "🌈 Other",
        "pref": "Who do you want to rate?",
        "p_m": "Men", "p_f": "Women", "p_a": "Everyone",
        "photo": "📸 Send one selfie: clear face, no heavy filters, no nudity.\nOr skip and start rating: /rate",
        "live": "🎥 Quick check: send a <b>round video</b> of 2–3 seconds (hold the mic button → camera). It only proves it's really you; nobody but the admin sees it.",
        "live_need": "Send a round video (not a photo or file) to verify it's you.",
        "pending": "⏳ Your photo is being checked and will go live soon.\nMeanwhile: rate {n} people to unlock your score 👇",
        "approved": "✅ Your photo is approved and live! You'll get a message when it has a score.",
        "rejected": "❌ Your photo wasn't approved (we need a clear selfie of you, no nudity). Send another one.",
        "full": "You already have {n} photos. Delete one to upload a new one: /delete",
        "rate_cap": "🔥 {i}/{n} — what's your rating?",
        "rate_free": "🔥 What's your rating?",
        "sample": "🧪 Sample photo · ",
        "none": "😴 No new photos to rate right now. Try again soon — and share your link to bring more: /link",
        "slow": "Slow down 🙂",
        "cap": "You hit today's rating limit. See you tomorrow!",
        "unlocked": "🔓 You unlocked your score! Type /me",
        "me_none": "You don't have a photo in the game yet. Send a selfie to start.",
        "me_lock": "🔒 Rate {k} more people to see your score: /rate",
        "me_wait": "📊 Photo {i}: {n}/{m} ratings — score coming soon.",
        "me_score": "📊 Photo {i}: <b>{s}</b> ({n} ratings){pct}",
        "pct": " · top {p}%",
        "me_friends": "\n👥 Your friends' average: {f}",
        "me_status": "\n⏳ Photo {i}: {st}",
        "st_pending": "being checked", "st_hidden": "hidden for review",
        "me_tail": "\n\n📣 Share your card: /card",
        "score_ready": "🎉 You have a score! {s} · type /me for details",
        "score_moved": "✨ {k} new people rated you: your score is now {s}",
        "score_locked": "🎉 Your photo has a score — rate {k} more people to see it: /rate",
        "link": "🔗 Your personal link — whoever joins through it rates you first:\n{url}",
        "card": "✨ <b>My Glow score: {s}</b>{pct}\nWhat would you get? 👇\n{url}",
        "card_none": "No score yet. First a photo and {n} ratings.",
        "share": "📤 Share",
        "friend_in": "👋 {name} invited you. Rate them first, then get your own score!",
        "ref_paid": "🎁 A friend you invited started playing! Your photo will be shown to 20 more people.",
        "report": "🚩",
        "report_ask": "Why are you reporting?",
        "r_minor": "Looks under 18", "r_fake": "Not them", "r_nsfw": "Nudity / inappropriate", "r_other": "Other",
        "reported": "Thanks, report received.",
        "deleted": "🗑️ All your photos, ratings and data were deleted.",
        "help": "✨ <b>Glow</b>\n/rate — rate people\n/me — my score\n/link — my personal link\n/card — share card\n/lang — language\n/delete — delete everything",
        "blocked": "⛔ No access.",
    },
}


class Glow:
    def __init__(self, api, db, owner, username="GlowRateMeBot", now=time.time, rng=None):
        self.api, self.owner, self.username, self.now = api, owner, username, now
        self.rng = rng or random.random
        self.db = db
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        for table, col in (("gusers", "seen INTEGER"), ("gusers", "uname TEXT"), ("gphotos", "sample TEXT")):
            try:
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass
        self.fresh = None

    # ---------- helpers ----------
    def q(self, sql, *a):
        cur = self.db.execute(sql, a)
        self.db.commit()
        return cur

    def one(self, sql, *a):
        return self.db.execute(sql, a).fetchone()

    def day(self):
        return datetime.fromtimestamp(self.now(), TZ).strftime("%Y-%m-%d")

    def t(self, u, key, **kw):
        lang = (u["lang"] if u else "en") or "en"
        return T.get(lang, T["en"])[key].format(**kw)

    def send(self, chat, text, kb=None):
        p = {"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        if kb:
            p["reply_markup"] = {"inline_keyboard": kb}
        return self.api.call("sendMessage", **p)

    def link(self, uid):
        return f"https://t.me/{self.username}?start=r_{uid}"

    def user(self, frm):
        u = self.one("SELECT * FROM gusers WHERE id=?", frm["id"])
        if not u:
            lang = "he" if (frm.get("language_code") or "").startswith("he") else "en"
            self.q("INSERT INTO gusers(id, name, lang, state, joined) VALUES(?,?,?,?,?)",
                   frm["id"], (frm.get("first_name") or "")[:40], lang, "terms", int(self.now()))
            self.fresh = frm["id"]
        self.q("UPDATE gusers SET seen=?, uname=? WHERE id=?", int(self.now()), (frm.get("username") or "")[:40] or None, frm["id"])
        return self.one("SELECT * FROM gusers WHERE id=?", frm["id"])

    def rated(self, uid):
        return self.one("SELECT COUNT(*) FROM gratings WHERE rater=?", uid)[0]

    # ---------- scoring ----------
    def weight(self, rater):
        vals = [r[0] for r in self.db.execute(
            "SELECT value FROM gratings WHERE rater=? ORDER BY ts DESC LIMIT 20", (rater,))]
        if len(vals) >= 10:
            m = sum(vals) / len(vals)
            if math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals)) < 0.5:
                return 0.3  # always the same number: counts much less
        return 1.0

    def score(self, photo):
        rows = self.db.execute("SELECT rater, value FROM gratings WHERE photo=? AND friend=0", (photo,)).fetchall()
        if len(rows) < MIN_SCORE:
            return None, len(rows)
        rows = sorted(rows, key=lambda r: r["value"])
        if len(rows) > TRIM_FROM:
            k = len(rows) // 10
            rows = rows[k:len(rows) - k]
        ws = [(self.weight(r["rater"]), r["value"]) for r in rows]
        s = (sum(w * v for w, v in ws) + PRIOR * PRIOR_W) / (sum(w for w, _ in ws) + PRIOR_W)
        return round(s, 1), len(self.db.execute("SELECT 1 FROM gratings WHERE photo=? AND friend=0", (photo,)).fetchall())

    def percentile(self, photo, gender):
        mine, _ = self.score(photo)
        if mine is None:
            return None
        others = [self.score(r["id"])[0] for r in self.db.execute(
            "SELECT p.id FROM gphotos p JOIN gusers u ON u.id=p.owner WHERE p.status='live' AND u.gender=?", (gender,))]
        others = [s for s in others if s is not None]
        if len(others) < 10:
            return None
        higher = sum(1 for s in others if s > mine)
        return max(1, math.ceil(100 * (higher + 1) / len(others)))

    def best(self, uid):
        best = None
        for p in self.db.execute("SELECT id FROM gphotos WHERE owner=? AND status='live'", (uid,)):
            s, _ = self.score(p["id"])
            if s is not None and (best is None or s > best[1]):
                best = (p["id"], s)
        return best

    # ---------- queue ----------
    def next_photo(self, u):
        genders = {"m": ("m",), "f": ("f",), "a": ("m", "f", "o")}.get(u["pref"] or "a", ("m", "f", "o"))
        base = ("SELECT p.id, p.file, p.owner FROM gphotos p JOIN gusers o ON o.id=p.owner "
                "WHERE p.status='live' AND p.owner<>? AND o.blocked=0 AND o.gender IN (%s) "
                "AND NOT EXISTS (SELECT 1 FROM gratings r WHERE r.rater=? AND r.photo=p.id) " % ",".join("?" * len(genders)))
        args = [u["id"], *genders, u["id"]]
        if u["ref"]:  # the friend who invited you comes first
            r = self.one(base + "AND p.owner=? ORDER BY p.id LIMIT 1", *args, u["ref"])
            if r:
                return r
        if u["year"]:
            r = self.one(base + "AND o.year BETWEEN ? AND ? ORDER BY "
                         "(SELECT COUNT(*) FROM gratings g WHERE g.photo=p.id), o.karma DESC, RANDOM() LIMIT 1",
                         *args, u["year"] - AGE_SPAN, u["year"] + AGE_SPAN)
            if r:
                return r
        r = self.one(base + "ORDER BY (SELECT COUNT(*) FROM gratings g WHERE g.photo=p.id), o.karma DESC, RANDOM() LIMIT 1", *args)
        if r:
            return r
        # no real photo left: labelled sample photos matching the preference (never part of anyone's score)
        return self.one("SELECT p.id, p.file, p.owner FROM gphotos p WHERE p.status='live' AND p.sample IN (%s) "
                        "AND NOT EXISTS (SELECT 1 FROM gratings r WHERE r.rater=? AND r.photo=p.id) ORDER BY RANDOM() LIMIT 1"
                        % ",".join("?" * len(genders)), *genders, u["id"])

    def rate_kb(self, u, photo):
        row1 = [{"text": str(i), "callback_data": f"r:{photo}:{i}"} for i in range(1, 6)]
        row2 = [{"text": str(i), "callback_data": f"r:{photo}:{i}"} for i in range(6, 11)]
        return {"inline_keyboard": [row1, row2, [{"text": self.t(u, "report"), "callback_data": f"rep:{photo}"}]]}

    def caption(self, u, p=None):
        n = self.rated(u["id"])
        c = self.t(u, "rate_cap", i=n + 1, n=GIVE) if n < GIVE else self.t(u, "rate_free")
        return (self.t(u, "sample") + c) if p is not None and p["owner"] == 0 else c

    def show_next(self, u, edit=None):
        p = self.next_photo(u)
        if not p:
            if edit:
                self.api.call("editMessageCaption", chat_id=u["id"], message_id=edit, caption=self.t(u, "none"))
            else:
                self.send(u["id"], self.t(u, "none"))
            return
        if edit:
            r = self.api.call("editMessageMedia", chat_id=u["id"], message_id=edit,
                              media={"type": "photo", "media": p["file"], "caption": self.caption(u, p)},
                              reply_markup=self.rate_kb(u, p["id"]))
            if r:
                return
        m = self.api.call("sendPhoto", chat_id=u["id"], photo=p["file"], caption=self.caption(u, p),
                          reply_markup=self.rate_kb(u, p["id"]), protect_content=True)
        if m:
            self.q("UPDATE gusers SET msg=? WHERE id=?", m.get("message_id"), u["id"])

    # ---------- notifications ----------
    def notify(self, uid, text):
        hour = datetime.fromtimestamp(self.now(), TZ).hour
        if not 9 <= hour < 23:
            return False
        d = self.day()
        n = self.one("SELECT n FROM gnotes WHERE user=? AND day=?", uid, d)
        if n and n["n"] >= NOTIFY_DAY:
            return False
        self.q("INSERT INTO gnotes(user, day, n) VALUES(?,?,1) ON CONFLICT(user, day) DO UPDATE SET n=n+1", uid, d)
        self.send(uid, text)
        return True

    def after_rating(self, photo):
        p = self.one("SELECT * FROM gphotos WHERE id=?", photo)
        if not p or p["owner"] == 0:
            return
        s, n = self.score(photo)
        if s is None or n - p["notified"] < (MIN_SCORE if p["notified"] == 0 else 10):
            return
        o = self.one("SELECT * FROM gusers WHERE id=?", p["owner"])
        left = GIVE - self.rated(o["id"])
        if left > 0:
            text = self.t(o, "score_locked", k=left)
        elif p["notified"] == 0:
            text = self.t(o, "score_ready", s=s)
        else:
            text = self.t(o, "score_moved", k=n - p["notified"], s=s)
        if self.notify(o["id"], text):
            self.q("UPDATE gphotos SET notified=? WHERE id=?", n, photo)

    # ---------- updates ----------
    def handle(self, upd):
        if "callback_query" in upd:
            return self.on_callback(upd["callback_query"])
        m = upd.get("message")
        if not m or m["chat"]["type"] != "private":
            return
        u = self.user(m["from"])
        if u["blocked"]:
            return self.send(u["id"], self.t(u, "blocked"))
        text = (m.get("text") or "").strip()
        if text.startswith("/"):
            return self.on_command(u, m, text)
        if u["state"] == "year" and text:
            return self.on_year(u, text)
        cap = (m.get("caption") or "").strip().lower().split()
        if "photo" in m and u["id"] == self.owner and len(cap) == 2 and cap[0] in ("sample", "דוגמה") and cap[1] in ("m", "f"):
            pid = self.add_sample(cap[1], max(m["photo"], key=lambda x: x.get("width", 0) * x.get("height", 0))["file_id"])
            return self.send(self.owner, f"✅ תמונת דוגמה #{pid} נוספה")
        if "photo" in m:
            return self.on_photo(u, m)
        if "video_note" in m:
            return self.on_live(u, m)
        if u["state"] == "live":
            return self.send(u["id"], self.t(u, "live_need"))
        if u["state"] == "terms":
            return self.ask_terms(u)

    def ask_terms(self, u):
        self.send(u["id"], self.t(u, "welcome"), [[{"text": self.t(u, "agree"), "callback_data": "agree"}]])

    def on_command(self, u, m, text):
        cmd, _, arg = text[1:].partition(" ")
        cmd = cmd.split("@")[0].lower()
        if cmd == "start":
            if arg.startswith("r_") and arg[2:].isdigit() and not u["ref"] and int(arg[2:]) != u["id"] \
                    and self.one("SELECT 1 FROM gusers WHERE id=?", int(arg[2:])):
                self.q("UPDATE gusers SET ref=? WHERE id=?", int(arg[2:]), u["id"])
                r = self.one("SELECT name FROM gusers WHERE id=?", int(arg[2:]))
                self.send(u["id"], self.t(u, "friend_in", name=r["name"] or "🙂"))
            if self.fresh == u["id"]:
                self.fresh = None
                self.feed(f"🆕 נכנס משתמש חדש: {self.who(self.one('SELECT * FROM gusers WHERE id=?', u['id']))}")
            if u["state"] == "terms":
                return self.ask_terms(u)
            return self.show_next(self.user(m["from"])) if u["state"] == "ready" else self.resume(u)
        if u["id"] == self.owner and cmd in ("stats", "users", "u", "feed", "sample", "samples"):
            return self.admin(cmd, arg.strip())
        if u["state"] != "ready" and cmd not in ("delete", "lang", "help"):
            return self.resume(u)
        if cmd == "rate":
            return self.show_next(u)
        if cmd == "me":
            return self.me(u)
        if cmd == "link":
            return self.send(u["id"], self.t(u, "link", url=self.link(u["id"])))
        if cmd == "card":
            return self.card(u)
        if cmd == "lang":
            lang = "en" if u["lang"] == "he" else "he"
            self.q("UPDATE gusers SET lang=? WHERE id=?", lang, u["id"])
            return self.send(u["id"], T[lang]["help"])
        if cmd == "delete":
            return self.delete(u)
        return self.send(u["id"], self.t(u, "help"))

    def resume(self, u):
        st = u["state"]
        if st == "terms":
            return self.ask_terms(u)
        if st == "year":
            return self.send(u["id"], self.t(u, "year"))
        if st == "gender":
            return self.ask_gender(u)
        if st == "pref":
            return self.ask_pref(u)
        if st == "live":
            return self.send(u["id"], self.t(u, "live"))
        return self.send(u["id"], self.t(u, "help"))

    def ask_gender(self, u):
        self.send(u["id"], self.t(u, "gender"), [[{"text": self.t(u, k), "callback_data": f"g:{k[2]}"} for k in ("g_m", "g_f", "g_o")]])

    def ask_pref(self, u):
        self.send(u["id"], self.t(u, "pref"), [[{"text": self.t(u, k), "callback_data": f"p:{k[2]}"} for k in ("p_m", "p_f", "p_a")]])

    def on_year(self, u, text):
        if not (text.isdigit() and len(text) == 4 and 1920 <= int(text) <= datetime.fromtimestamp(self.now(), TZ).year):
            return self.send(u["id"], self.t(u, "year_bad"))
        if datetime.fromtimestamp(self.now(), TZ).year - int(text) < 18:
            self.q("UPDATE gusers SET blocked=1, year=? WHERE id=?", int(text), u["id"])
            return self.send(u["id"], self.t(u, "minor"))
        self.q("UPDATE gusers SET year=?, state='gender' WHERE id=?", int(text), u["id"])
        self.ask_gender(u)

    def on_photo(self, u, m):
        if u["state"] not in ("ready", "photo"):
            return self.resume(u)
        n = self.one("SELECT COUNT(*) FROM gphotos WHERE owner=? AND status IN ('live','pending','new','hidden')", u["id"])[0]
        if n >= MAX_PHOTOS:
            return self.send(u["id"], self.t(u, "full", n=MAX_PHOTOS))
        file = max(m["photo"], key=lambda p: p.get("width", 0) * p.get("height", 0))["file_id"]
        self.q("DELETE FROM gphotos WHERE owner=? AND status='new'", u["id"])
        self.q("INSERT INTO gphotos(owner, file, status, created) VALUES(?,?,'new',?)", u["id"], file, int(self.now()))
        if u["live"]:  # already verified once: straight to review
            return self.submit(u)
        self.q("UPDATE gusers SET state='live' WHERE id=?", u["id"])
        self.send(u["id"], self.t(u, "live"))

    def on_live(self, u, m):
        if u["state"] != "live":
            return
        self.q("UPDATE gusers SET live=?, state='ready' WHERE id=?", m["video_note"]["file_id"], u["id"])
        self.submit(self.one("SELECT * FROM gusers WHERE id=?", u["id"]))

    def submit(self, u):
        p = self.one("SELECT * FROM gphotos WHERE owner=? AND status='new' ORDER BY id DESC", u["id"])
        if not p:
            return
        self.q("UPDATE gphotos SET status='pending' WHERE id=?", p["id"])
        age = datetime.fromtimestamp(self.now(), TZ).year - (u["year"] or 0)
        self.api.call("sendPhoto", chat_id=self.owner, photo=p["file"],
                      caption=f"🆕 Glow #{p['id']} · {u['name']} · {age} · {u['gender']}",
                      reply_markup={"inline_keyboard": [[{"text": "✅ אשר", "callback_data": f"ok:{p['id']}"},
                                                         {"text": "❌ דחה", "callback_data": f"no:{p['id']}"}]]})
        if u["live"]:
            self.api.call("sendVideoNote", chat_id=self.owner, video_note=u["live"])
        self.send(u["id"], self.t(u, "pending", n=GIVE))
        self.show_next(u)

    def me(self, u):
        photos = self.db.execute("SELECT * FROM gphotos WHERE owner=? AND status<>'new' ORDER BY id", (u["id"],)).fetchall()
        if not photos:
            return self.send(u["id"], self.t(u, "me_none"))
        left = GIVE - self.rated(u["id"])
        if left > 0:
            return self.send(u["id"], self.t(u, "me_lock", k=left))
        lines = []
        for i, p in enumerate(photos, 1):
            if p["status"] != "live":
                lines.append(self.t(u, "me_status", i=i, st=self.t(u, "st_hidden" if p["status"] == "hidden" else "st_pending")).strip())
                continue
            s, n = self.score(p["id"])
            if s is None:
                lines.append(self.t(u, "me_wait", i=i, n=n, m=MIN_SCORE))
                continue
            pct = self.percentile(p["id"], u["gender"])
            line = self.t(u, "me_score", i=i, s=s, n=n, pct=self.t(u, "pct", p=pct) if pct else "")
            f = self.one("SELECT AVG(value), COUNT(*) FROM gratings WHERE photo=? AND friend=1", p["id"])
            if f[1] >= 3:
                line += self.t(u, "me_friends", f=round(f[0], 1))
            lines.append(line)
        self.send(u["id"], "\n".join(lines) + self.t(u, "me_tail"))

    def card(self, u):
        b = self.best(u["id"])
        if not b or self.rated(u["id"]) < GIVE:
            return self.send(u["id"], self.t(u, "card_none", n=GIVE))
        pct = self.percentile(b[0], u["gender"])
        url = self.link(u["id"])
        text = self.t(u, "card", s=b[1], pct=self.t(u, "pct", p=pct) if pct else "", url=url)
        share = "https://t.me/share/url?url=" + urllib.request.quote(url) + "&text=" + urllib.request.quote(f"✨ Glow {b[1]}")
        self.send(u["id"], text, [[{"text": self.t(u, "share"), "url": share}]])

    def delete(self, u):
        ids = [r[0] for r in self.db.execute("SELECT id FROM gphotos WHERE owner=?", (u["id"],))]
        for pid in ids:
            self.q("DELETE FROM gratings WHERE photo=?", pid)
            self.q("DELETE FROM greports WHERE photo=?", pid)
        self.q("DELETE FROM gphotos WHERE owner=?", u["id"])
        self.q("DELETE FROM gratings WHERE rater=?", u["id"])
        self.q("DELETE FROM gnotes WHERE user=?", u["id"])
        blocked = u["blocked"]
        self.q("DELETE FROM gusers WHERE id=?", u["id"])
        if blocked:  # someone under 18 stays blocked, without their data
            self.q("INSERT INTO gusers(id, lang, state, blocked, joined) VALUES(?,?,'terms',1,?)", u["id"], u["lang"], int(self.now()))
        self.send(u["id"], T.get(u["lang"] or "en", T["en"])["deleted"])

    # ---------- admin (owner only) ----------
    def who(self, u):
        tag = f"@{u['uname']}" if u["uname"] else ""
        return f"{u['name'] or '?'} {tag} <code>{u['id']}</code> · {u['lang']}".replace("  ", " ")

    def ago(self, ts):
        if not ts:
            return "-"
        d = int(self.now()) - int(ts)
        return f"{d // 60} דק׳" if d < 3600 else f"{d // 3600} שע׳" if d < 86400 else f"{d // 86400} ימים"

    def feed(self, text):
        if (self.one("SELECT v FROM gmeta WHERE k='feed'") or ["on"])[0] == "on":
            self.send(self.owner, text)

    def admin(self, cmd, arg):
        if cmd == "feed":
            on = (self.one("SELECT v FROM gmeta WHERE k='feed'") or ["on"])[0] != "on"
            self.q("INSERT OR REPLACE INTO gmeta(k, v) VALUES('feed', ?)", "on" if on else "off")
            return self.send(self.owner, "🔔 התראות חיות: " + ("פועלות" if on else "כבויות"))
        if cmd in ("sample", "samples"):
            return self.sample_cmd(arg)
        if cmd == "users":
            return self.users(int(arg) if arg.isdigit() else 15)
        if cmd == "u":
            return self.user_card(int(arg) if arg.lstrip("-").isdigit() else 0)
        return self.stats()

    def add_sample(self, gender, file):
        self.q("INSERT INTO gphotos(owner, file, status, created, sample) VALUES(0,?,'live',?,?)", file, int(self.now()), gender)
        return self.one("SELECT last_insert_rowid()")[0]

    def sample_cmd(self, arg):
        parts = arg.split()
        if len(parts) >= 2 and parts[0] in ("m", "f") and parts[1].startswith("http"):
            m = self.api.call("sendPhoto", chat_id=self.owner, photo=parts[1], caption="🧪")
            if not m:
                return self.send(self.owner, "❌ לא הצלחתי לטעון את התמונה מהקישור.")
            file = max(m["photo"], key=lambda x: x.get("width", 0) * x.get("height", 0))["file_id"] if m.get("photo") else parts[1]
            pid = self.add_sample(parts[0], file)
            return self.send(self.owner, f"✅ תמונת דוגמה #{pid} נוספה ({'גבר' if parts[0] == 'm' else 'אישה'})")
        if len(parts) == 2 and parts[0] == "del" and parts[1].isdigit():
            self.q("UPDATE gphotos SET status='rejected' WHERE id=? AND owner=0", int(parts[1]))
            return self.send(self.owner, f"🗑 תמונת דוגמה #{parts[1]} הוסרה")
        rows = self.db.execute("SELECT sample, COUNT(*) FROM gphotos WHERE owner=0 AND status='live' GROUP BY sample").fetchall()
        have = " · ".join(f"{'גברים' if g == 'm' else 'נשים'} {n}" for g, n in rows) or "אין"
        self.send(self.owner, f"🧪 תמונות דוגמה פעילות: {have}\n"
                              "הוספה: שלח תמונה עם הכיתוב sample m או sample f, או /sample m &lt;קישור&gt;\n"
                              "הסרה: /sample del &lt;מספר&gt;\n"
                              "הן מוצגות רק כשאין תמונות אמיתיות, מסומנות כדוגמה, ולא נכנסות לציון של אף אחד.")

    def stats(self):
        c = lambda sql, *a: self.one(sql, *a)[0]
        now = int(self.now())
        total = c("SELECT COUNT(*) FROM gusers WHERE name IS NOT NULL")
        new24 = c("SELECT COUNT(*) FROM gusers WHERE name IS NOT NULL AND joined>?", now - 86400)
        new7 = c("SELECT COUNT(*) FROM gusers WHERE name IS NOT NULL AND joined>?", now - 7 * 86400)
        act24 = c("SELECT COUNT(*) FROM gusers WHERE seen>?", now - 86400)
        minors = c("SELECT COUNT(*) FROM gusers WHERE blocked=1")
        refs = c("SELECT COUNT(*) FROM gusers WHERE ref IS NOT NULL")
        st = dict(self.db.execute("SELECT state, COUNT(*) FROM gusers WHERE blocked=0 AND name IS NOT NULL GROUP BY state").fetchall())
        up = c("SELECT COUNT(DISTINCT owner) FROM gphotos WHERE status<>'new' AND owner<>0")
        raters = c("SELECT COUNT(DISTINCT rater) FROM gratings")
        unlocked = c("SELECT COUNT(*) FROM (SELECT rater FROM gratings GROUP BY rater HAVING COUNT(*)>=?)", GIVE)
        ph = dict(self.db.execute("SELECT status, COUNT(*) FROM gphotos WHERE owner<>0 GROUP BY status").fetchall())
        smp = c("SELECT COUNT(*) FROM gphotos WHERE owner=0 AND status='live'")
        r24 = c("SELECT COUNT(*) FROM gratings WHERE ts>?", now - 86400)
        rall = c("SELECT COUNT(*) FROM gratings")
        avg = self.one("SELECT AVG(value) FROM gratings")[0]
        reps = c("SELECT COUNT(*) FROM greports")
        lines = [
            "📊 <b>Glow — סטטיסטיקה (רק לך)</b>",
            "",
            f"👥 משתמשים: <b>{total}</b> · חדשים 24ש׳: {new24} · 7 ימים: {new7}",
            f"🟢 פעילים ב-24ש׳: {act24} · הגיעו מקישור של חבר: {refs} · נחסמו (מתחת ל-18): {minors}",
            "",
            "🪜 <b>משפך:</b>",
            f"נכנסו {total} → סיימו הרשמה {st.get('ready', 0) + st.get('live', 0)} → העלו תמונה {up} → דירגו {raters} → פתחו ציון ({GIVE}+) {unlocked}",
            "תקועים: " + (" · ".join(f"{STATE_HE.get(k, k)} {v}" for k, v in st.items() if k != "ready") or "אף אחד"),
            "",
            f"📸 תמונות: בדירוג {ph.get('live', 0)} · ממתינות לאישור שלך {ph.get('pending', 0)} · מוסתרות {ph.get('hidden', 0)} · נדחו {ph.get('rejected', 0)}",
            f"⭐ דירוגים: 24ש׳ {r24} · סה״כ {rall} · ממוצע {avg:.1f}" if avg else f"⭐ דירוגים: 24ש׳ {r24} · סה״כ {rall}",
            f"🚩 דיווחים: {reps} · 🧪 תמונות דוגמה: {smp} (/samples)",
            "",
            "/users — אחרונים · /u &lt;id&gt; — משתמש · /feed — התראות חיות",
        ]
        self.send(self.owner, "\n".join(lines))

    def users(self, n):
        n = max(1, min(n, 40))
        rows = self.db.execute("SELECT * FROM gusers WHERE name IS NOT NULL ORDER BY joined DESC LIMIT ?", (n,)).fetchall()
        if not rows:
            return self.send(self.owner, "אין עדיין משתמשים.")
        out = [f"👥 <b>{len(rows)} המשתמשים האחרונים</b>"]
        for u in rows:
            ph = self.one("SELECT COUNT(*) FROM gphotos WHERE owner=? AND status<>'new'", u["id"])[0]
            gave = self.rated(u["id"])
            got = self.one("SELECT COUNT(*) FROM gratings r JOIN gphotos p ON p.id=r.photo WHERE p.owner=?", u["id"])[0]
            state = "⛔ קטין" if u["blocked"] else STATE_HE.get(u["state"], u["state"])
            out.append(f"\n• {self.who(u)}\n  נכנס לפני {self.ago(u['joined'])} · נראה לפני {self.ago(u['seen'])} · {state}"
                       f"\n  📸 {ph} · נתן {gave} · קיבל {got}" + (" · 🔗 מחבר" if u["ref"] else ""))
        self.send(self.owner, "\n".join(out))

    def user_card(self, uid):
        u = self.one("SELECT * FROM gusers WHERE id=?", uid)
        if not u:
            return self.send(self.owner, "לא נמצא. כתוב /u ואת המספר מ-/users")
        age = (datetime.fromtimestamp(self.now(), TZ).year - u["year"]) if u["year"] else "-"
        g = {"m": "גבר", "f": "אישה", "o": "אחר"}.get(u["gender"], "-")
        p = {"m": "גברים", "f": "נשים", "a": "כולם"}.get(u["pref"], "-")
        refd = self.one("SELECT COUNT(*) FROM gusers WHERE ref=?", uid)[0]
        out = [f"👤 <b>{self.who(u)}</b>",
               f"מצב: {'⛔ קטין' if u['blocked'] else STATE_HE.get(u['state'], u['state'])} · גיל {age} · {g} · מדרג {p}",
               f"נכנס לפני {self.ago(u['joined'])} · נראה לפני {self.ago(u['seen'])}",
               f"נתן {self.rated(uid)} דירוגים · קארמה {u['karma']} · הביא {refd} חברים" + (f" · הגיע דרך <code>{u['ref']}</code>" if u["ref"] else "")]
        for ph in self.db.execute("SELECT * FROM gphotos WHERE owner=? ORDER BY id", (uid,)).fetchall():
            n = self.one("SELECT COUNT(*) FROM gratings WHERE photo=?", ph["id"])[0]
            sc = self.score(ph["id"])[0]
            out.append(f"📸 #{ph['id']} {ph['status']} · {n} דירוגים" + (f" · ציון {sc}" if sc else ""))
        self.send(self.owner, "\n".join(out))

    # ---------- callbacks ----------
    def on_callback(self, cb):
        u = self.user(cb["from"])
        data = cb.get("data", "")
        msg = (cb.get("message") or {}).get("message_id")
        answer = lambda text=None: self.api.call("answerCallbackQuery", callback_query_id=cb["id"], **({"text": text} if text else {}))
        kind, _, rest = data.partition(":")
        if u["blocked"]:
            return answer(self.t(u, "blocked"))
        if kind in ("ok", "no") and u["id"] == self.owner and rest.isdigit():
            return self.review(int(rest), kind == "ok", answer)
        if kind == "agree" and u["state"] == "terms":
            answer()
            self.q("UPDATE gusers SET state='year' WHERE id=?", u["id"])
            return self.send(u["id"], self.t(u, "year"))
        if kind == "g" and rest in ("m", "f", "o") and u["state"] == "gender":
            answer()
            self.q("UPDATE gusers SET gender=?, state='pref' WHERE id=?", rest, u["id"])
            return self.ask_pref(u)
        if kind == "p" and rest in ("m", "f", "a") and u["state"] == "pref":
            answer()
            self.q("UPDATE gusers SET pref=?, state='ready' WHERE id=?", rest, u["id"])
            u = self.one("SELECT * FROM gusers WHERE id=?", u["id"])
            self.send(u["id"], self.t(u, "photo"))
            if u["ref"]:
                self.show_next(u)
            return
        if kind == "r" and u["state"] == "ready":
            return self.on_rate(u, rest, msg, answer)
        if kind == "rep":
            answer()
            pid = rest
            return self.send(u["id"], self.t(u, "report_ask"), [[{"text": self.t(u, k), "callback_data": f"rr:{pid}:{k[2:]}"}]
                                                                  for k in ("r_minor", "r_fake", "r_nsfw", "r_other")])
        if kind == "rr":
            pid, _, reason = rest.partition(":")
            if pid.isdigit():
                self.report(u, int(pid), reason)
            answer(self.t(u, "reported"))
            if msg:
                self.api.call("deleteMessage", chat_id=u["id"], message_id=msg)
            return self.show_next(u)
        answer()

    def on_rate(self, u, rest, msg, answer):
        try:
            pid, v = (int(x) for x in rest.split(":"))
        except ValueError:
            return answer()
        if not 1 <= v <= 10:
            return answer()
        now = self.now()
        if now - (u["last_rate"] or 0) < MIN_GAP:
            return answer(self.t(u, "slow"))
        if self.one("SELECT COUNT(*) FROM gratings WHERE rater=? AND day=?", u["id"], self.day())[0] >= MAX_RATES_DAY:
            return answer(self.t(u, "cap"))
        p = self.one("SELECT * FROM gphotos WHERE id=? AND status='live'", pid)
        if not p or p["owner"] == u["id"]:
            answer()
            return self.show_next(u, edit=msg)
        friend = 1 if p["owner"] and u["ref"] == p["owner"] else 0
        cur = self.q("INSERT OR IGNORE INTO gratings(rater, photo, value, friend, ts, day) VALUES(?,?,?,?,?,?)",
                     u["id"], pid, v, friend, int(now), self.day())
        answer()
        if cur.rowcount:
            self.q("UPDATE gusers SET karma=karma+1, last_rate=? WHERE id=?", now, u["id"])
            n = self.rated(u["id"])
            if n == GIVE:
                if self.one("SELECT 1 FROM gphotos WHERE owner=?", u["id"]):
                    self.send(u["id"], self.t(u, "unlocked"))
                if u["ref"] and not u["ref_paid"]:
                    self.q("UPDATE gusers SET ref_paid=1 WHERE id=?", u["id"])
                    self.q("UPDATE gusers SET karma=karma+20 WHERE id=?", u["ref"])
                    r = self.one("SELECT * FROM gusers WHERE id=?", u["ref"])
                    if r:
                        self.notify(r["id"], self.t(r, "ref_paid"))
            self.after_rating(pid)
        self.show_next(self.one("SELECT * FROM gusers WHERE id=?", u["id"]), edit=msg)

    def report(self, u, pid, reason):
        if reason not in ("minor", "fake", "nsfw", "other"):
            reason = "other"
        self.q("INSERT OR IGNORE INTO greports(reporter, photo, reason, ts) VALUES(?,?,?,?)", u["id"], pid, reason, int(self.now()))
        n = self.one("SELECT COUNT(*) FROM greports WHERE photo=?", pid)[0]
        p = self.one("SELECT * FROM gphotos WHERE id=?", pid)
        if p and p["status"] == "live" and (n >= REPORT_HIDE or reason == "minor"):
            self.q("UPDATE gphotos SET status='hidden' WHERE id=?", pid)
            self.api.call("sendPhoto", chat_id=self.owner, photo=p["file"],
                          caption=f"🚩 Glow #{pid} הוסתרה · {n} דיווחים · אחרון: {reason}",
                          reply_markup={"inline_keyboard": [[{"text": "✅ להחזיר", "callback_data": f"ok:{pid}"},
                                                             {"text": "❌ להסיר", "callback_data": f"no:{pid}"}]]})

    def review(self, pid, ok, answer):
        p = self.one("SELECT * FROM gphotos WHERE id=?", pid)
        if not p:
            return answer("נמחקה")
        o = self.one("SELECT * FROM gusers WHERE id=?", p["owner"])
        self.q("UPDATE gphotos SET status=? WHERE id=?", "live" if ok else "rejected", pid)
        answer("✅ אושרה" if ok else "❌ נדחתה")
        if o:
            self.send(o["id"], self.t(o, "approved" if ok else "rejected"))


# ---------- network ----------
class Api:
    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}/"

    def call(self, method, **params):
        req = urllib.request.Request(self.base + method, data=json.dumps(params).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=70) as r:
                return json.loads(r.read()).get("result")
        except Exception as e:
            print("glow api error", method, e)
            return None


def run(token, db_path, owner):
    api = Api(token)
    me = None
    while not me:
        me = api.call("getMe")
        if not me:
            time.sleep(30)
    api.call("setMyCommands", commands=[{"command": c, "description": d} for c, d in (
        ("rate", "Rate people / לדרג"), ("me", "My score / הציון שלי"), ("link", "My link / הקישור שלי"),
        ("card", "Share card / כרטיס"), ("lang", "Language / שפה"), ("delete", "Delete my data / מחיקה"))])
    try:
        api.call("setMyCommands", scope={"type": "chat", "chat_id": owner}, commands=[{"command": c, "description": d} for c, d in (
            ("stats", "📊 סטטיסטיקה"), ("users", "👥 משתמשים אחרונים"), ("feed", "🔔 התראות חיות"), ("samples", "🧪 תמונות דוגמה"),
            ("rate", "לדרג"), ("me", "הציון שלי"), ("link", "הקישור שלי"))])
    except Exception as e:
        print("glow owner commands:", e)
    g = Glow(api, sqlite3.connect(db_path, timeout=30), owner, me.get("username", "GlowRateMeBot"))
    offset = 0
    while True:
        ups = api.call("getUpdates", offset=offset, timeout=50, allowed_updates=["message", "callback_query"])
        if ups is None:
            time.sleep(3)
            continue
        for upd in ups:
            offset = upd["update_id"] + 1
            try:
                g.handle(upd)
            except Exception as e:
                print("glow error", e)


def start_thread(token, db_path, owner):
    th = threading.Thread(target=run, args=(token, db_path, owner), daemon=True)
    th.start()
    return th

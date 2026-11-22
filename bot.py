#!/usr/bin/env python3
"""Derby - fan war bot for Telegram. Standard library only.

Run:  BOT_TOKEN=... OWNER_ID=... python3 bot.py
"""
import html
import json
import os
import re
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
DATA = json.loads((HERE / os.environ.get("TOPIC_FILE", "clubs.json")).read_text(encoding="utf-8"))
CLUBS, RIVALRIES = DATA["clubs"], DATA["rivalries"]
TZ = ZoneInfo("Asia/Jerusalem")
BRAND_CLUB = os.environ.get("BRAND_CLUB", "")  # e.g. "mta" for a Maccabi-only bot
EXACT, OUTCOME = 3, 1

T = {
    "he": {
        "pick_region": "באיזו ליגה הקבוצה שלך?",
        "il": "🇮🇱 ישראל", "world": "🌍 העולם",
        "pick_club": "בחר את הקבוצה שלך:",
        "joined": "נרשמת כאוהד {club}. אתה אוהד מספר {n} שלה במפקד.",
        "census": "📊 <b>מפקד האוהדים</b>",
        "invite": "הקישור שלך לגיוס אוהדים:\n{link}\nהבאת עד עכשיו: {n}",
        "change": "החלף קבוצה", "table": "📊 המפקד", "add_group": "➕ הוסף לקבוצה שלך",
        "group_hello": "Derby כאן. מנהל, בחר את הקבוצה שהקבוצה הזאת אוהדת:",
        "admin_only": "רק מנהל קבוצה יכול לבחור.",
        "group_set": "הקבוצה נרשמה כאוהדי {club}. כתבו /derby כדי לאתגר קבוצת אוהדים יריבה.",
        "no_group": "קודם צריך שמנהל יבחר קבוצה. כתבו /start",
        "pick_rival": "את מי מאתגרים?",
        "challenge": "⚔️ <b>{name}</b>\nהאוהדים של {a} ({title}) מזמינים את אוהדי {b} לדרבי של ניחושים.\nמקבלים או בורחים?",
        "accept": "מקבלים את האתגר", "forward_hint": "העבירו את ההודעה הזאת לקבוצת אוהדים של {b}.",
        "challenge_on": "⚔️ הדרבי יצא לדרך: {g1} ({a}) נגד {g2} ({b}). מי שמביא יותר מנחשים מנצח.",
        "bad_challenge": "האתגר הזה כבר לא זמין.",
        "match": "⚽ <b>{home} - {away}</b>\n🕒 {when}\nניחשו עד עכשיו בקבוצה: {n}",
        "predict": "🎯 לנחש תוצאה",
        "ask_home": "{home} - {away}\nכמה שערים ל{home}?",
        "ask_away": "כמה שערים ל{away}?",
        "saved": "נשמר: {home} {hg} - {ag} {away}. אפשר לשנות עד שריקת הפתיחה.",
        "locked": "המשחק כבר התחיל, הניחושים נעולים.",
        "result": "🏁 <b>{home} {hg} - {ag} {away}</b>\nהקבוצה הזאת צברה {pts} נקודות מ-{n} מנחשים.",
        "top": "המנחש המוביל: {name} ({pts})",
        "duel_win": "🏆 ניצחתם את {other}: {mine} מול {theirs}",
        "duel_lose": "😤 הפסדתם ל-{other}: {mine} מול {theirs}",
        "duel_tie": "🤝 תיקו מול {other}: {mine} מול {theirs}",
        "top_title": "🏅 <b>טבלת המגייסים</b>", "top_empty": "עוד אין מגייסים. הקישור האישי שלך מחכה ב-/start",
        "pen_btn": "⚽ הפנדל היומי", "pen_shoot": "הפנדל היומי נגד {rival}.\nלאן אתה בועט?",
        "pen_dive": "ולאן השוער שלכם קופץ מול הבעיטות שלהם?",
        "pen_saved": "נרשם. התוצאה מתפרסמת ב-21:00.\nרצף: {streak} ימים · הנקודות שלך: {pts}",
        "pen_result": "⚽ <b>הפנדל היומי</b>\n{a} <b>{ga}</b> : <b>{gb}</b> {b}\nבעטו: {na} מול {nb}",
        "pen_norival": "אין לקבוצה שלך יריבה במשחק הזה.",
        "log_title": "📒 <b>יומן פעולות</b>", "log_more": "ועוד {n} פעולות. /log לרשימה המלאה",
        "log_empty": "עוד אין פעולות ביומן.", "notify_on": "עדכונים בזמן אמת: פועל.", "notify_off": "עדכונים בזמן אמת: כבוי. /log מציג את היומן.",
        "ev_new": "👤 משתמש חדש: {name}", "ev_club": "🎽 {name} נרשם כאוהד {club}{ref}", "ev_ref": " (גויס ע\"י {ref})",
        "ev_pen": "⚽ {name} בעט בפנדל היומי ({club})", "ev_pred": "🎯 {name} ניחש {home} {hg}-{ag} {away}",
        "ev_group": "👥 קבוצה חדשה: {title} ({club})", "ev_chal": "⚔️ {title} פתחה אתגר דרבי", "ev_acc": "🔥 {title} קיבלה אתגר דרבי",
        "rep_title": "📈 <b>דוח {bot} · {period}</b>", "rep_day": "24 השעות האחרונות", "rep_week": "7 הימים האחרונים",
        "rep_body": "👀 נגעו בבוט: {touch} אנשים ({hits} פעולות)\n🖱 לחיצות על כפתורים: {clicks}\n🆕 נרשמו: {new}\n⚽ שיחקו (פנדל או ניחוש): {played}\n👥 קבוצות חדשות: {groups}\n\n📊 סה\"כ: {users} רשומים · {allgroups} קבוצות",
        "remind": "⏰ עוד שעה הקרב היומי נסגר, ו{club} צריכה אותך.\nהרצף שלך: {streak} ימים. אל תשבור אותו.",
        "remind_off": "לא תקבל יותר תזכורות. /remind on מחזיר אותן.", "remind_on": "התזכורות היומיות חזרו.",
        "owner_only": "פקודה למנהל הבוט בלבד.",
        "usage_addmatch": "שימוש: /addmatch בית חוץ YYYY-MM-DD HH:MM",
        "usage_result": "שימוש: /result מספר_משחק שערי_בית שערי_חוץ",
        "match_added": "משחק {id} נוסף ונשלח ל-{n} קבוצות.",
        "result_done": "תוצאה נרשמה ונשלחה ל-{n} קבוצות.",
        "stats": "משתמשים: {u}\nקבוצות: {g}\nדרבים פעילים: {c}\nניחושים: {p}",
    },
    "en": {
        "pick_region": "Which league is your club in?",
        "il": "🇮🇱 Israel", "world": "🌍 World",
        "pick_club": "Pick your club:",
        "joined": "You are registered as a {club} fan. You are fan number {n} in the census.",
        "census": "📊 <b>Fan census</b>",
        "invite": "Your link to recruit fans:\n{link}\nRecruited so far: {n}",
        "change": "Change club", "table": "📊 Census", "add_group": "➕ Add to your group",
        "group_hello": "Derby is here. Admin, pick the club this group supports:",
        "admin_only": "Only a group admin can pick.",
        "group_set": "This group is registered as {club} fans. Send /derby to challenge a rival fan group.",
        "no_group": "An admin has to pick a club first. Send /start",
        "pick_rival": "Who do you challenge?",
        "challenge": "⚔️ <b>{name}</b>\n{a} fans ({title}) challenge {b} fans to a prediction derby.\nAccept or hide?",
        "accept": "Accept the challenge", "forward_hint": "Forward this message to a {b} fan group.",
        "challenge_on": "⚔️ The derby is on: {g1} ({a}) v {g2} ({b}). The side with more predictors wins.",
        "bad_challenge": "This challenge is no longer available.",
        "match": "⚽ <b>{home} - {away}</b>\n🕒 {when}\nPredictions in this group so far: {n}",
        "predict": "🎯 Predict the score",
        "ask_home": "{home} - {away}\nHow many goals for {home}?",
        "ask_away": "How many goals for {away}?",
        "saved": "Saved: {home} {hg} - {ag} {away}. You can change it until kickoff.",
        "locked": "The match has started, predictions are locked.",
        "result": "🏁 <b>{home} {hg} - {ag} {away}</b>\nThis group scored {pts} points from {n} predictors.",
        "top": "Top predictor: {name} ({pts})",
        "duel_win": "🏆 You beat {other}: {mine} to {theirs}",
        "duel_lose": "😤 You lost to {other}: {mine} to {theirs}",
        "duel_tie": "🤝 Draw with {other}: {mine} to {theirs}",
        "top_title": "🏅 <b>Top recruiters</b>", "top_empty": "No recruiters yet. Your personal link is waiting in /start",
        "pen_btn": "⚽ Daily penalty", "pen_shoot": "Daily penalty against {rival}.\nWhere do you shoot?",
        "pen_dive": "And where does your keeper dive against their shots?",
        "pen_saved": "Saved. The result is published at 21:00.\nStreak: {streak} days · Your points: {pts}",
        "pen_result": "⚽ <b>Daily penalty</b>\n{a} <b>{ga}</b> : <b>{gb}</b> {b}\nShooters: {na} v {nb}",
        "pen_norival": "Your club has no rival in this game.",
        "log_title": "📒 <b>Activity log</b>", "log_more": "and {n} more. /log for the full list",
        "log_empty": "No activity yet.", "notify_on": "Live updates: on.", "notify_off": "Live updates: off. /log shows the log.",
        "ev_new": "👤 New user: {name}", "ev_club": "🎽 {name} joined as a {club} fan{ref}", "ev_ref": " (recruited by {ref})",
        "ev_pen": "⚽ {name} took the daily penalty ({club})", "ev_pred": "🎯 {name} predicted {home} {hg}-{ag} {away}",
        "ev_group": "👥 New group: {title} ({club})", "ev_chal": "⚔️ {title} opened a derby challenge", "ev_acc": "🔥 {title} accepted a derby challenge",
        "rep_title": "📈 <b>{bot} report · {period}</b>", "rep_day": "last 24 hours", "rep_week": "last 7 days",
        "rep_body": "👀 Touched the bot: {touch} people ({hits} actions)\n🖱 Button clicks: {clicks}\n🆕 Registered: {new}\n⚽ Played (penalty or prediction): {played}\n👥 New groups: {groups}\n\n📊 Total: {users} registered · {allgroups} groups",
        "remind": "⏰ One hour until today's battle closes, and {club} needs you.\nYour streak: {streak} days. Don't break it.",
        "remind_off": "No more reminders. /remind on brings them back.", "remind_on": "Daily reminders are back.",
        "owner_only": "Owner command only.",
        "usage_addmatch": "Usage: /addmatch home away YYYY-MM-DD HH:MM",
        "usage_result": "Usage: /result match_id home_goals away_goals",
        "match_added": "Match {id} added and sent to {n} groups.",
        "result_done": "Result saved and sent to {n} groups.",
        "stats": "Users: {u}\nGroups: {g}\nActive derbies: {c}\nPredictions: {p}",
    },
}

for _lang, _over in DATA.get("strings", {}).items():  # a topic file can rename anything the bot says
    T.setdefault(_lang, {}).update(_over)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, lang TEXT, club TEXT, ref_by INTEGER, joined INTEGER, quiet INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS groups(id INTEGER PRIMARY KEY, title TEXT, club TEXT, lang TEXT, joined INTEGER);
CREATE TABLE IF NOT EXISTS challenges(id INTEGER PRIMARY KEY AUTOINCREMENT, rivalry TEXT, from_group INTEGER, to_group INTEGER, status TEXT, created INTEGER);
CREATE TABLE IF NOT EXISTS matches(id INTEGER PRIMARY KEY AUTOINCREMENT, home TEXT, away TEXT, kickoff INTEGER, hg INTEGER, ag INTEGER);
CREATE TABLE IF NOT EXISTS posts(match_id INTEGER, group_id INTEGER, message_id INTEGER, PRIMARY KEY(match_id, group_id));
CREATE TABLE IF NOT EXISTS pen(day TEXT, user_id INTEGER, club TEXT, shoot INTEGER, dive INTEGER, goal INTEGER, PRIMARY KEY(day, user_id));
CREATE TABLE IF NOT EXISTS hits(ts INTEGER, user_id INTEGER, kind TEXT);
CREATE TABLE IF NOT EXISTS events(ts INTEGER, kind TEXT, user_id INTEGER, text TEXT);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS predictions(match_id INTEGER, user_id INTEGER, group_id INTEGER, hg INTEGER, ag INTEGER, points INTEGER, PRIMARY KEY(match_id, user_id));
"""


class Api:
    """Thin Telegram Bot API client."""

    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}/"

    def call(self, method, **params):
        req = urllib.request.Request(
            self.base + method,
            data=json.dumps(params).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=70) as r:
                return json.loads(r.read()).get("result")
        except Exception as e:  # a failed send must never stop the bot
            print("api error", method, e)
            return None


def esc(s):
    return html.escape(str(s or ""))


def points(hg, ag, rh, ra):
    if (hg, ag) == (rh, ra):
        return EXACT
    sign = lambda x, y: (x > y) - (x < y)
    return OUTCOME if sign(hg, ag) == sign(rh, ra) else 0


class Bot:
    def __init__(self, api, db_path="derby.db", owner_id=0, now=time.time):
        self.api, self.owner, self.now = api, int(owner_id or 0), now
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        try:  # databases created before reminders existed
            self.db.execute("ALTER TABLE users ADD COLUMN quiet INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        if not self.owner:  # no OWNER_ID given: the first person to /start in private becomes the owner
            row = self.one("SELECT v FROM meta WHERE k='owner'")
            self.owner = int(row["v"]) if row else 0
        self.pending, self.last_flush = [], self.now()
        me = api.call("getMe") or {}
        self.username = me.get("username", "bot")

    # ---------- helpers ----------
    def q(self, sql, *a):
        cur = self.db.execute(sql, a)
        self.db.commit()
        return cur

    def one(self, sql, *a):
        return self.db.execute(sql, a).fetchone()

    def t(self, lang, key, **kw):
        return T[lang if lang in T else "en"][key].format(**kw)

    def club(self, cid, lang):
        c = CLUBS[cid]
        return f"{c['emoji']} {c[lang if lang in ('he', 'en') else 'en']}"

    def send(self, chat, text, kb=None):
        p = dict(chat_id=chat, text=text, parse_mode="HTML", disable_web_page_preview=True)
        if kb:
            p["reply_markup"] = {"inline_keyboard": kb}
        return self.api.call("sendMessage", **p)

    def link(self, payload, group=False):
        return f"https://t.me/{self.username}?{'startgroup' if group else 'start'}={payload}"

    # ---------- activity log ----------
    def owner_lang(self):
        o = self.one("SELECT lang FROM users WHERE id=?", self.owner) if self.owner else None
        return o["lang"] if o else "he"

    def log(self, kind, uid, key, **kw):
        text = self.t(self.owner_lang(), key, **kw)
        self.q("INSERT INTO events VALUES(?,?,?,?)", int(self.now()), kind, uid, text)
        if self.owner and uid != self.owner:
            self.pending.append(text)

    def notify_enabled(self):
        r = self.one("SELECT v FROM meta WHERE k='notify'")
        return not r or r["v"] != "off"

    def flush_log(self, force=False):
        """Send queued events to the owner as one message, at most once a minute."""
        if not self.pending or not self.owner:
            return
        if not force and self.now() - self.last_flush < 60 and len(self.pending) < 30:
            return
        items, self.pending, self.last_flush = self.pending, [], self.now()
        if not self.notify_enabled():
            return
        lang = self.owner_lang()
        lines = [self.t(lang, "log_title")] + items[:30]
        if len(items) > 30:
            lines.append(self.t(lang, "log_more", n=len(items) - 30))
        self.send(self.owner, "\n".join(lines))

    def user(self, frm):
        u = self.one("SELECT * FROM users WHERE id=?", frm["id"])
        if not u:
            lang = "he" if (frm.get("language_code") or "").startswith("he") else "en"
            self.q("INSERT INTO users(id,name,lang,joined) VALUES(?,?,?,?)",
                   frm["id"], frm.get("first_name", ""), lang, int(self.now()))
            u = self.one("SELECT * FROM users WHERE id=?", frm["id"])
            self.log("new", frm["id"], "ev_new", name=esc(frm.get("first_name", "")))
        return u

    def set_user_club(self, uid, cid):
        self.q("UPDATE users SET club=? WHERE id=?", cid, uid)
        u = self.one("SELECT name, ref_by FROM users WHERE id=?", uid)
        r = self.one("SELECT name FROM users WHERE id=?", u["ref_by"]) if u and u["ref_by"] else None
        ol = self.owner_lang()
        self.log("club", uid, "ev_club", name=esc(u["name"] if u else uid), club=self.club(cid, ol),
                 ref=self.t(ol, "ev_ref", ref=esc(r["name"])) if r else "")
        return self.one("SELECT COUNT(*) c FROM users WHERE club=?", cid)["c"]

    def rivalries_of(self, cid):
        return [(rid, r) for rid, r in RIVALRIES.items() if cid in (r["a"], r["b"])]

    def census_text(self, cid, lang):
        lines = [self.t(lang, "census")]
        for _, r in self.rivalries_of(cid):
            ca = self.one("SELECT COUNT(*) c FROM users WHERE club=?", r["a"])["c"]
            cb = self.one("SELECT COUNT(*) c FROM users WHERE club=?", r["b"])["c"]
            lines.append(f"{self.club(r['a'], lang)} <b>{ca}</b>  :  <b>{cb}</b> {self.club(r['b'], lang)}")
        return "\n".join(lines)

    def region_kb(self, lang):
        return [[{"text": self.t(lang, "il"), "callback_data": "rg:il"},
                 {"text": self.t(lang, "world"), "callback_data": "rg:world"}]]

    def clubs_kb(self, region, lang):
        btns = [{"text": self.club(cid, lang), "callback_data": f"cl:{cid}"}
                for cid, c in CLUBS.items() if c["region"] == region]
        return [btns[i:i + 2] for i in range(0, len(btns), 2)]

    def home_kb(self, lang):
        return [[{"text": self.t(lang, "pen_btn"), "callback_data": "pn"}],
                [{"text": self.t(lang, "table"), "callback_data": "tb"},
                 {"text": self.t(lang, "change"), "callback_data": "chg"}],
                [{"text": self.t(lang, "add_group"), "url": self.link("new", group=True)}]]

    def show_home(self, u):
        lang = u["lang"]
        refs = self.one("SELECT COUNT(*) c FROM users WHERE ref_by=?", u["id"])["c"]
        text = self.census_text(u["club"], lang) + "\n\n" + self.t(
            lang, "invite", link=self.link(f"j{u['club']}_{u['id']}"), n=refs)
        self.send(u["id"], text, self.home_kb(lang))

    # ---------- daily penalty ----------
    def pen_day(self, ts=None):
        """Game day rolls over at 21:00 Israel time: later shots count for tomorrow."""
        return datetime.fromtimestamp((ts or self.now()) + 3 * 3600, TZ).strftime("%Y-%m-%d")

    def user_points(self, uid):
        a = self.one("SELECT COALESCE(SUM(points),0) c FROM predictions WHERE user_id=?", uid)["c"]
        b = self.one("SELECT COALESCE(SUM(goal),0) c FROM pen WHERE user_id=?", uid)["c"]
        return a + b

    def streak(self, uid):
        days = {r["day"] for r in self.db.execute("SELECT day FROM pen WHERE user_id=?", (uid,))}
        n, ts = 0, self.now()
        while self.pen_day(ts) in days:
            n, ts = n + 1, ts - 86400
        return n

    def dir_kb(self, prefix):
        return [[{"text": "⬅️", "callback_data": f"{prefix}:0"}, {"text": "⬆️", "callback_data": f"{prefix}:1"},
                 {"text": "➡️", "callback_data": f"{prefix}:2"}]]

    def resolve_penalties(self):
        """Settle every finished game day once and post the score to the groups of both clubs."""
        today = self.pen_day()
        for row in self.db.execute("SELECT DISTINCT day FROM pen WHERE goal IS NULL AND day<? ORDER BY day", (today,)).fetchall():
            day = row["day"]
            keeper = {}
            for r in self.db.execute("SELECT club, dive, COUNT(*) n FROM pen WHERE day=? GROUP BY club, dive ORDER BY n DESC, dive", (day,)):
                keeper.setdefault(r["club"], r["dive"])
            for rid, rv in RIVALRIES.items():
                a, b = rv["a"], rv["b"]
                na = self.one("SELECT COUNT(*) c FROM pen WHERE day=? AND club=?", day, a)["c"]
                nb = self.one("SELECT COUNT(*) c FROM pen WHERE day=? AND club=?", day, b)["c"]
                primary = lambda c: self.rivalries_of(c)[0][0] == rid
                if not ((na and nb) or (na and primary(a)) or (nb and primary(b))):
                    continue  # one-sided scores are posted only for a club's main rivalry
                ga = self.one("SELECT COUNT(*) c FROM pen WHERE day=? AND club=? AND shoot!=?", day, a, keeper.get(b, -1))["c"]
                gb = self.one("SELECT COUNT(*) c FROM pen WHERE day=? AND club=? AND shoot!=?", day, b, keeper.get(a, -1))["c"]
                for g in self.db.execute("SELECT * FROM groups WHERE club IN (?,?)", (a, b)).fetchall():
                    gl = g["lang"]
                    self.send(g["id"], self.t(gl, "pen_result", a=self.club(a, gl), b=self.club(b, gl), ga=ga, gb=gb, na=na, nb=nb),
                              [[{"text": self.t(gl, "pen_btn"), "url": self.link("pen")}]])
            # a shot scores unless the rival keeper (first rivalry of the club) guessed its direction
            for r in self.db.execute("SELECT user_id, club, shoot FROM pen WHERE day=?", (day,)).fetchall():
                rivs = self.rivalries_of(r["club"])
                rival = None
                if rivs:
                    rv = rivs[0][1]
                    rival = rv["b"] if r["club"] == rv["a"] else rv["a"]
                goal = 1 if r["shoot"] != keeper.get(rival, -1) else 0
                self.q("UPDATE pen SET goal=? WHERE day=? AND user_id=?", goal, day, r["user_id"])

    # ---------- matches ----------
    def match_text(self, m, gid, lang):
        n = self.one("SELECT COUNT(*) c FROM predictions WHERE match_id=? AND group_id=?", m["id"], gid)["c"]
        when = datetime.fromtimestamp(m["kickoff"], TZ).strftime("%d/%m %H:%M")
        return self.t(lang, "match", home=self.club(m["home"], lang), away=self.club(m["away"], lang), when=when, n=n)

    def post_match(self, m, g):
        kb = [[{"text": self.t(g["lang"], "predict"), "url": self.link(f"p{m['id']}_{g['id']}")}]]
        res = self.send(g["id"], self.match_text(m, g["id"], g["lang"]), kb)
        if res:
            self.q("INSERT OR REPLACE INTO posts VALUES(?,?,?)", m["id"], g["id"], res["message_id"])

    def post_open_matches(self, g):
        for m in self.db.execute("SELECT * FROM matches WHERE hg IS NULL AND kickoff>? AND (home=? OR away=?)",
                                 (int(self.now()), g["club"], g["club"])).fetchall():
            self.post_match(m, g)

    def register_group(self, chat, cid):
        lang = "he" if CLUBS[cid]["region"] == "il" else "en"
        self.q("INSERT OR REPLACE INTO groups(id,title,club,lang,joined) VALUES(?,?,?,?,?)",
               chat["id"], chat.get("title", ""), cid, lang, int(self.now()))
        g = self.one("SELECT * FROM groups WHERE id=?", chat["id"])
        self.log("group", 0, "ev_group", title=esc(g["title"]), club=self.club(cid, self.owner_lang()))
        self.send(g["id"], self.t(lang, "group_set", club=self.club(cid, lang)))
        self.post_open_matches(g)
        return g

    # ---------- updates ----------
    def handle(self, upd):
        try:
            frm = (upd.get("message") or upd.get("callback_query") or {}).get("from") or {}
            kind = "click" if "callback_query" in upd else "msg"
            if frm.get("id") and frm["id"] != self.owner:
                self.q("INSERT INTO hits VALUES(?,?,?)", int(self.now()), frm["id"], kind)
        except Exception as e:
            print("hit error", e)
        if "message" in upd:
            self.on_message(upd["message"])
        elif "callback_query" in upd:
            self.on_callback(upd["callback_query"])
        elif "my_chat_member" in upd:
            m = upd["my_chat_member"]
            if m["chat"]["type"] in ("group", "supergroup") and m["new_chat_member"]["status"] in ("member", "administrator") \
                    and m["old_chat_member"]["status"] in ("left", "kicked"):
                if not self.one("SELECT 1 FROM groups WHERE id=?", m["chat"]["id"]):
                    lang = "he" if (m["from"].get("language_code") or "").startswith("he") else "en"
                    self.send(m["chat"]["id"], self.t(lang, "group_hello"), self.region_kb(lang))

    def on_message(self, msg):
        text = msg.get("text") or ""
        if not text.startswith("/") or "from" not in msg:
            return
        parts = text.split()
        cmd = parts[0][1:].split("@")[0].lower()
        args = parts[1:]
        chat, frm = msg["chat"], msg["from"]
        private = chat["type"] == "private"
        if cmd == "start":
            return self.start_private(frm, args) if private else self.start_group(chat, frm, args)
        if cmd in ("table", "census"):
            if private:
                u = self.user(frm)
                return self.show_home(u) if u["club"] else self.send(u["id"], self.t(u["lang"], "pick_region"), self.region_kb(u["lang"]))
            g = self.one("SELECT * FROM groups WHERE id=?", chat["id"])
            return self.send(chat["id"], self.census_text(g["club"], g["lang"])) if g else None
        if cmd == "remind" and private:
            u = self.user(frm)
            off = not (args and args[0].lower() in ("on", "1"))
            self.q("UPDATE users SET quiet=? WHERE id=?", 1 if off else 0, u["id"])
            return self.send(u["id"], self.t(u["lang"], "remind_off" if off else "remind_on"))
        if cmd == "derby" and not private:
            return self.derby(chat, frm)
        if cmd == "top":
            g = None if private else self.one("SELECT * FROM groups WHERE id=?", chat["id"])
            lang = g["lang"] if g else self.user(frm)["lang"]
            rows = self.db.execute(
                "SELECT r.name, r.club, COUNT(*) n FROM users u JOIN users r ON r.id=u.ref_by "
                "GROUP BY r.id ORDER BY n DESC, r.id LIMIT 10").fetchall()
            if not rows:
                return self.send(chat["id"], self.t(lang, "top_empty"))
            lines = [self.t(lang, "top_title")] + [
                f"{i}. {esc(r['name'])} {CLUBS[r['club']]['emoji'] if r['club'] in CLUBS else ''} <b>{r['n']}</b>"
                for i, r in enumerate(rows, 1)]
            return self.send(chat["id"], "\n".join(lines))
        if cmd in ("addmatch", "result", "stats", "log", "notify", "report"):
            lang = self.user(frm)["lang"]
            if frm["id"] != self.owner:
                return self.send(chat["id"], self.t(lang, "owner_only"))
            return getattr(self, "cmd_" + cmd)(chat["id"], args, lang)

    def start_private(self, frm, args):
        if not self.owner:
            self.owner = frm["id"]
            self.q("INSERT OR REPLACE INTO meta VALUES('owner',?)", str(frm["id"]))
        u = self.user(frm)
        lang = u["lang"]
        payload = args[0] if args else ""
        if payload.startswith("p"):  # prediction deep link: p<match>_<group>
            try:
                mid, gid = payload[1:].split("_", 1)
                mid, gid = int(mid), int(gid)
            except ValueError:
                return
            g = self.one("SELECT * FROM groups WHERE id=?", gid)
            m = self.one("SELECT * FROM matches WHERE id=?", mid)
            if not g or not m:
                return
            if not u["club"]:
                n = self.set_user_club(u["id"], g["club"])
                self.send(u["id"], self.t(lang, "joined", club=self.club(g["club"], lang), n=n))
            if self.now() >= m["kickoff"]:
                return self.send(u["id"], self.t(lang, "locked"))
            kb = [[{"text": str(i), "callback_data": f"ph:{mid}:{gid}:{i}"} for i in range(0, 4)],
                  [{"text": str(i), "callback_data": f"ph:{mid}:{gid}:{i}"} for i in range(4, 8)]]
            return self.send(u["id"], self.t(lang, "ask_home", home=self.club(m["home"], lang), away=self.club(m["away"], lang)), kb)
        if payload.startswith("j") and not u["club"]:  # recruit link: j<club>_<referrer>
            cid, _, ref = payload[1:].partition("_")
            if cid in CLUBS:
                if ref.isdigit() and int(ref) != u["id"]:
                    self.q("UPDATE users SET ref_by=? WHERE id=?", int(ref), u["id"])
                n = self.set_user_club(u["id"], cid)
                self.send(u["id"], self.t(lang, "joined", club=self.club(cid, lang), n=n))
                return self.show_home(self.user(frm))
        if u["club"]:
            return self.show_home(u)
        if BRAND_CLUB in CLUBS:  # a club-branded bot signs fans up in one tap
            n = self.set_user_club(u["id"], BRAND_CLUB)
            self.send(u["id"], self.t(lang, "joined", club=self.club(BRAND_CLUB, lang), n=n))
            return self.show_home(self.user(frm))
        self.send(u["id"], self.t(lang, "pick_region"), self.region_kb(lang))

    def start_group(self, chat, frm, args):
        payload = args[0] if args else ""
        lang = "he" if (frm.get("language_code") or "").startswith("he") else "en"
        g = self.one("SELECT * FROM groups WHERE id=?", chat["id"])
        if payload.startswith("c") and payload[1:].isdigit():
            ch = self.one("SELECT * FROM challenges WHERE id=? AND status='open'", int(payload[1:]))
            if not ch or ch["from_group"] == chat["id"]:
                return self.send(chat["id"], self.t(lang, "bad_challenge"))
            src = self.one("SELECT * FROM groups WHERE id=?", ch["from_group"])
            r = RIVALRIES[ch["rivalry"]]
            rival = r["b"] if src["club"] == r["a"] else r["a"]
            if g and g["club"] != rival:
                return self.send(chat["id"], self.t(g["lang"], "bad_challenge"))
            if not g:
                g = self.register_group(chat, rival)
            self.q("UPDATE challenges SET to_group=?, status='active' WHERE id=?", g["id"], ch["id"])
            self.log("accept", 0, "ev_acc", title=esc(g["title"]))
            for x in (src, g):
                self.send(x["id"], self.t(x["lang"], "challenge_on", g1=esc(src["title"]), a=self.club(src["club"], x["lang"]),
                                           g2=esc(g["title"]), b=self.club(g["club"], x["lang"])))
            return
        if g:
            return self.send(chat["id"], self.census_text(g["club"], g["lang"]))
        self.send(chat["id"], self.t(lang, "group_hello"), self.region_kb(lang))

    def derby(self, chat, frm):
        g = self.one("SELECT * FROM groups WHERE id=?", chat["id"])
        if not g:
            lang = "he" if (frm.get("language_code") or "").startswith("he") else "en"
            return self.send(chat["id"], self.t(lang, "no_group"))
        kb = []
        for rid, r in self.rivalries_of(g["club"]):
            rival = r["b"] if g["club"] == r["a"] else r["a"]
            kb.append([{"text": self.club(rival, g["lang"]), "callback_data": f"dr:{rid}"}])
        self.send(chat["id"], self.t(g["lang"], "pick_rival"), kb)

    def is_admin(self, chat_id, user_id):
        m = self.api.call("getChatMember", chat_id=chat_id, user_id=user_id) or {}
        return m.get("status") in ("creator", "administrator")

    def on_callback(self, cb):
        data, frm = cb.get("data", ""), cb["from"]
        chat = cb["message"]["chat"]
        private = chat["type"] == "private"
        u = self.user(frm)
        lang = u["lang"]
        answer = lambda text=None: self.api.call("answerCallbackQuery", callback_query_id=cb["id"], **({"text": text} if text else {}))
        kind, _, rest = data.partition(":")
        if kind == "rg" and rest in ("il", "world"):
            answer()
            return self.send(chat["id"], self.t(lang, "pick_club"), self.clubs_kb(rest, lang))
        if kind == "cl" and rest in CLUBS:
            if private:
                answer()
                n = self.set_user_club(u["id"], rest)
                self.send(u["id"], self.t(lang, "joined", club=self.club(rest, lang), n=n))
                return self.show_home(self.user(frm))
            if not self.is_admin(chat["id"], frm["id"]):
                return answer(self.t(lang, "admin_only"))
            answer()
            if not self.one("SELECT 1 FROM groups WHERE id=?", chat["id"]):
                self.register_group(chat, rest)
            return
        if kind == "pn" and private:
            answer()
            rivs = self.rivalries_of(u["club"]) if u["club"] else []
            if not rivs:
                return self.send(u["id"], self.t(lang, "pen_norival"))
            rv = rivs[0][1]
            rival = rv["b"] if u["club"] == rv["a"] else rv["a"]
            return self.send(u["id"], self.t(lang, "pen_shoot", rival=self.club(rival, lang)), self.dir_kb("ps"))
        if kind == "ps" and private and rest in ("0", "1", "2"):
            answer()
            return self.send(u["id"], self.t(lang, "pen_dive"), self.dir_kb(f"pd:{rest}"))
        if kind == "pd" and private and u["club"] and re.fullmatch(r"[012]:[012]", rest):
            answer()
            shoot, dive = (int(x) for x in rest.split(":"))
            self.q("INSERT OR REPLACE INTO pen(day,user_id,club,shoot,dive) VALUES(?,?,?,?,?)",
                   self.pen_day(), u["id"], u["club"], shoot, dive)
            self.log("pen", u["id"], "ev_pen", name=esc(u["name"]), club=self.club(u["club"], self.owner_lang()))
            return self.send(u["id"], self.t(lang, "pen_saved", streak=self.streak(u["id"]), pts=self.user_points(u["id"])))
        if kind == "tb" and u["club"]:
            answer()
            return self.show_home(u)
        if kind == "chg":
            answer()
            return self.send(chat["id"], self.t(lang, "pick_region"), self.region_kb(lang))
        if kind == "dr" and rest in RIVALRIES and not private:
            answer()
            g = self.one("SELECT * FROM groups WHERE id=?", chat["id"])
            r = RIVALRIES[rest]
            if not g or g["club"] not in (r["a"], r["b"]):
                return
            rival = r["b"] if g["club"] == r["a"] else r["a"]
            cid = self.q("INSERT INTO challenges(rivalry,from_group,status,created) VALUES(?,?,'open',?)",
                         rest, g["id"], int(self.now())).lastrowid
            self.log("challenge", frm["id"], "ev_chal", title=esc(g["title"]))
            gl = g["lang"]
            text = self.t(gl, "challenge", name=r[gl], a=self.club(g["club"], gl), title=esc(g["title"]), b=self.club(rival, gl))
            self.send(chat["id"], text, [[{"text": self.t(gl, "accept"), "url": self.link(f"c{cid}", group=True)}]])
            return self.send(chat["id"], self.t(gl, "forward_hint", b=self.club(rival, gl)))
        if kind in ("ph", "pa") and private:
            answer()
            try:
                nums = [int(x) for x in rest.split(":")]
            except ValueError:
                return
            if len(nums) != (3 if kind == "ph" else 4) or not all(0 <= x <= 20 for x in nums[2:]):
                return
            m = self.one("SELECT * FROM matches WHERE id=?", nums[0])
            g = self.one("SELECT * FROM groups WHERE id=?", nums[1])
            if not m or not g:
                return
            if self.now() >= m["kickoff"]:
                return self.send(u["id"], self.t(lang, "locked"))
            home, away = self.club(m["home"], lang), self.club(m["away"], lang)
            if kind == "ph":
                mk = lambda i: {"text": str(i), "callback_data": f"pa:{nums[0]}:{nums[1]}:{nums[2]}:{i}"}
                return self.send(u["id"], self.t(lang, "ask_away", away=away),
                                 [[mk(i) for i in range(0, 4)], [mk(i) for i in range(4, 8)]])
            self.q("INSERT OR REPLACE INTO predictions(match_id,user_id,group_id,hg,ag) VALUES(?,?,?,?,?)",
                   m["id"], u["id"], g["id"], nums[2], nums[3])
            ol = self.owner_lang()
            self.log("predict", u["id"], "ev_pred", name=esc(u["name"]), home=self.club(m["home"], ol),
                     away=self.club(m["away"], ol), hg=nums[2], ag=nums[3])
            self.send(u["id"], self.t(lang, "saved", home=home, hg=nums[2], ag=nums[3], away=away))
            post = self.one("SELECT * FROM posts WHERE match_id=? AND group_id=?", m["id"], g["id"])
            if post:
                self.api.call("editMessageText", chat_id=g["id"], message_id=post["message_id"], parse_mode="HTML",
                              text=self.match_text(m, g["id"], g["lang"]),
                              reply_markup={"inline_keyboard": [[{"text": self.t(g["lang"], "predict"),
                                                                  "url": self.link(f"p{m['id']}_{g['id']}")}]]})
            return
        answer()

    # ---------- owner commands ----------
    def cmd_addmatch(self, chat_id, args, lang):
        try:
            home, away = args[0], args[1]
            assert home in CLUBS and away in CLUBS and home != away
            ko = datetime.strptime(args[2] + " " + args[3], "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        except (IndexError, ValueError, AssertionError):
            return self.send(chat_id, self.t(lang, "usage_addmatch"))
        mid = self.q("INSERT INTO matches(home,away,kickoff) VALUES(?,?,?)", home, away, int(ko.timestamp())).lastrowid
        m = self.one("SELECT * FROM matches WHERE id=?", mid)
        groups = self.db.execute("SELECT * FROM groups WHERE club IN (?,?)", (home, away)).fetchall()
        for g in groups:
            self.post_match(m, g)
            time.sleep(0.05 if len(groups) > 20 else 0)
        self.send(chat_id, self.t(lang, "match_added", id=mid, n=len(groups)))

    def cmd_result(self, chat_id, args, lang):
        try:
            mid, rh, ra = int(args[0]), int(args[1]), int(args[2])
            m = self.one("SELECT * FROM matches WHERE id=?", mid)
            assert m and rh >= 0 and ra >= 0
        except (IndexError, ValueError, AssertionError):
            return self.send(chat_id, self.t(lang, "usage_result"))
        self.q("UPDATE matches SET hg=?, ag=? WHERE id=?", rh, ra, mid)
        for p in self.db.execute("SELECT * FROM predictions WHERE match_id=?", (mid,)).fetchall():
            self.q("UPDATE predictions SET points=? WHERE match_id=? AND user_id=?",
                   points(p["hg"], p["ag"], rh, ra), mid, p["user_id"])
        totals = {r["group_id"]: (r["pts"], r["n"]) for r in self.db.execute(
            "SELECT group_id, SUM(points) pts, COUNT(*) n FROM predictions WHERE match_id=? GROUP BY group_id", (mid,))}
        sent = 0
        for gid, (pts, n) in totals.items():
            g = self.one("SELECT * FROM groups WHERE id=?", gid)
            if not g:
                continue
            gl = g["lang"]
            lines = [self.t(gl, "result", home=self.club(m["home"], gl), away=self.club(m["away"], gl), hg=rh, ag=ra, pts=pts, n=n)]
            top = self.one("SELECT u.name, p.points FROM predictions p JOIN users u ON u.id=p.user_id "
                           "WHERE p.match_id=? AND p.group_id=? ORDER BY p.points DESC, p.rowid LIMIT 1", mid, gid)
            if top and top["points"]:
                lines.append(self.t(gl, "top", name=esc(top["name"]), pts=top["points"]))
            for ch in self.db.execute("SELECT * FROM challenges WHERE status='active' AND (from_group=? OR to_group=?)", (gid, gid)).fetchall():
                other_id = ch["to_group"] if ch["from_group"] == gid else ch["from_group"]
                other = self.one("SELECT * FROM groups WHERE id=?", other_id)
                theirs = totals.get(other_id, (0, 0))[0]
                key = "duel_win" if pts > theirs else "duel_lose" if pts < theirs else "duel_tie"
                lines.append(self.t(gl, key, other=esc(other["title"]), mine=pts, theirs=theirs))
            lines.append("")
            lines.append(self.census_text(g["club"], gl))
            self.send(gid, "\n".join(lines), [[{"text": self.t(gl, "add_group"), "url": self.link("new", group=True)}]])
            sent += 1
        self.send(chat_id, self.t(lang, "result_done", n=sent))

    def cmd_log(self, chat_id, args, lang):
        rows = self.db.execute("SELECT ts, text FROM events ORDER BY rowid DESC LIMIT 25").fetchall()
        if not rows:
            return self.send(chat_id, self.t(lang, "log_empty"))
        lines = [self.t(lang, "log_title")] + [
            datetime.fromtimestamp(r["ts"], TZ).strftime("%d/%m %H:%M") + "  " + r["text"] for r in reversed(rows)]
        self.send(chat_id, "\n".join(lines))

    def cmd_notify(self, chat_id, args, lang):
        off = bool(args) and args[0].lower() in ("off", "כבוי", "0")
        self.q("INSERT OR REPLACE INTO meta VALUES('notify',?)", "off" if off else "on")
        self.send(chat_id, self.t(lang, "notify_off" if off else "notify_on"))

    def report_text(self, lang, seconds):
        since = int(self.now()) - seconds
        c = lambda sql, *a: self.one(sql, *a)["c"]
        o = self.owner or 0
        played = c("SELECT COUNT(DISTINCT user_id) c FROM events WHERE ts>=? AND kind IN ('pen','predict')", since)
        return self.t(lang, "rep_title", bot="@" + self.username,
                      period=self.t(lang, "rep_week" if seconds > 86400 else "rep_day")) + "\n" + self.t(
            lang, "rep_body",
            touch=c("SELECT COUNT(DISTINCT user_id) c FROM hits WHERE ts>=? AND user_id!=?", since, o),
            hits=c("SELECT COUNT(*) c FROM hits WHERE ts>=? AND user_id!=?", since, o),
            clicks=c("SELECT COUNT(*) c FROM hits WHERE ts>=? AND kind='click' AND user_id!=?", since, o),
            new=c("SELECT COUNT(*) c FROM users WHERE joined>=? AND id!=?", since, o),
            played=played,
            groups=c("SELECT COUNT(*) c FROM groups WHERE joined>=?", since),
            users=c("SELECT COUNT(*) c FROM users"), allgroups=c("SELECT COUNT(*) c FROM groups"))

    def cmd_report(self, chat_id, args, lang):
        week = bool(args) and args[0].lower() in ("week", "שבוע", "7")
        self.send(chat_id, self.report_text(lang, 7 * 86400 if week else 86400))

    def daily_reminder(self):
        """At 20:00 Israel time, nudge registered fans who have not played today. Once a day, opt-out with /remind off."""
        now = datetime.fromtimestamp(self.now(), TZ)
        if now.hour != 20:
            return
        day = now.strftime("%Y-%m-%d")
        r = self.one("SELECT v FROM meta WHERE k='remind_day'")
        if r and r["v"] == day:
            return
        self.q("INSERT OR REPLACE INTO meta VALUES('remind_day',?)", day)
        today = self.pen_day()
        rows = self.db.execute("SELECT * FROM users WHERE club IS NOT NULL AND quiet=0 AND id NOT IN "
                               "(SELECT user_id FROM pen WHERE day=?)", (today,)).fetchall()
        for i, u in enumerate(rows):
            if not self.rivalries_of(u["club"]):
                continue
            self.send(u["id"], self.t(u["lang"], "remind", club=self.club(u["club"], u["lang"]), streak=self.streak(u["id"])),
                      [[{"text": self.t(u["lang"], "pen_btn"), "callback_data": "pn"}]])
            if i % 25 == 24:
                time.sleep(1)  # stay under Telegram's broadcast limit

    def daily_report(self):
        """Once a day at 21:05 Israel time, send the owner the day's numbers."""
        if not self.owner:
            return
        now = datetime.fromtimestamp(self.now(), TZ)
        day = now.strftime("%Y-%m-%d")
        if (now.hour, now.minute) < (21, 5):
            return
        r = self.one("SELECT v FROM meta WHERE k='report_day'")
        if r and r["v"] == day:
            return
        self.q("INSERT OR REPLACE INTO meta VALUES('report_day',?)", day)
        self.send(self.owner, self.report_text(self.owner_lang(), 86400))

    def cmd_stats(self, chat_id, args, lang):
        c = lambda sql: self.one(sql)["c"]
        self.send(chat_id, self.t(lang, "stats", u=c("SELECT COUNT(*) c FROM users"), g=c("SELECT COUNT(*) c FROM groups"),
                                  c=c("SELECT COUNT(*) c FROM challenges WHERE status='active'"),
                                  p=c("SELECT COUNT(*) c FROM predictions")))

    # ---------- main loop ----------
    def run(self):
        offset = 0
        print(f"Derby running as @{self.username}")
        while True:
            updates = self.api.call("getUpdates", offset=offset, timeout=50,
                                    allowed_updates=["message", "callback_query", "my_chat_member"])
            try:
                self.resolve_penalties()
            except Exception as e:
                print("penalty error", e)
            try:
                self.daily_reminder()
            except Exception as e:
                print("remind error", e)
            try:
                self.daily_report()
            except Exception as e:
                print("report error", e)
            try:
                self.flush_log()
            except Exception as e:
                print("log error", e)
            if updates is None:
                time.sleep(3)
                continue
            for upd in updates:
                offset = upd["update_id"] + 1
                try:
                    self.handle(upd)
                except Exception as e:  # one bad update must not stop the bot
                    print("handler error", e)


if __name__ == "__main__":
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Set BOT_TOKEN (from BotFather) and OWNER_ID (your Telegram user id).")
    Bot(Api(token), os.environ.get("DB_PATH", str(HERE / "derby.db")), os.environ.get("OWNER_ID", 0)).run()

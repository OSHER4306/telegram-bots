"""Fan War for Discord: the same world fan war as the Telegram bot, played with slash commands.

Points from Discord and Telegram go into the same cpower table, so fans on both apps feed one war.
Pure standard library: a small Discord Gateway (websocket) client plus REST calls over urllib.
"""
import json
import os
import socket
import ssl
import struct
import sqlite3
import threading
import time
import urllib.request
from datetime import datetime, timedelta

API = "https://discord.com/api/v10"
UA = "DiscordBot (https://t.me/DerbyFanWarBot, 1.0)"
HQ = "https://discord.gg/umBMNSrVj"
DUELS_PER_DAY = 5
MANAGE_GUILD = 1 << 5
import re
INVITE_RE = re.compile(r"^(?:https?://)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com/invite)/([A-Za-z0-9-]{2,32})/?$")
from zoneinfo import ZoneInfo
TZ = ZoneInfo("Asia/Jerusalem")

DSCHEMA = """
CREATE TABLE IF NOT EXISTS cpower(club TEXT PRIMARY KEY, power INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS dusers(id TEXT PRIMARY KEY, name TEXT, club TEXT, guild TEXT, joined INTEGER);
CREATE TABLE IF NOT EXISTS dhits(day TEXT, user_id TEXT, club TEXT, guild TEXT, PRIMARY KEY(day, user_id));
CREATE TABLE IF NOT EXISTS dguilds(id TEXT PRIMARY KEY, name TEXT, members INTEGER, joined INTEGER, left_at INTEGER);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS dduels(id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT, a TEXT, b TEXT, winner TEXT, guild TEXT);
CREATE TABLE IF NOT EXISTS dlinks(code TEXT PRIMARY KEY, discord_id TEXT, guild TEXT, tg_id INTEGER, created INTEGER);
CREATE TABLE IF NOT EXISTS dbonus(day TEXT, tg_id INTEGER, guild TEXT, PRIMARY KEY(day, tg_id));
"""

T = {
    "en": {
        "need_team": "⚽ Pick your team first: type **/team** and choose your club.",
        "bad_team": "Couldn't find that club. Type **/team** and pick one from the list.",
        "joined": "{e} You're in! You fight for **{c}** in the world Fan War ({n} fans on your side).\nNow type **/hit** to add points to your club today.",
        "hit": "💥 +10 for **{c}**!\n{c}: **{p}** points (#{rank} in the world)\n{r}: **{rp}** points\n{status}\n🔥 Streak: **{streak}** day(s) in a row\n\n⚔️ Challenge a rival fan: **/duel @friend**\nCome back tomorrow to keep your streak.",
        "ahead": "🔥 You're ahead of your rivals by {d}!",
        "behind": "⚠️ Your rivals lead by {d}. Call your friends!",
        "tie": "⚖️ Dead even with your rivals!",
        "done": "✅ You already hit for **{c}** today. Next hit: tomorrow (21:00 Israel time reset).\nType **/war** to see the world table.",
        "war": "🌍 **World Fan War** — live table\n{rows}{servers}\n\n🎮 {players} fans | 🏟️ {guilds} Discord servers + Telegram\nPick a side: **/team**, then **/hit** every day.",
        "servers": "\n\n🏟️ **Top servers this week**\n{rows}",
        "invite": "Add **Fan War** to any server in one click — the whole server joins the world war:",
        "add": "➕ Add to your server",
        "me": "🎮 Play anywhere",
        "tg": "📱 Play on Telegram too",
        "hq": "⚔️ Join Fan War HQ",
        "duel_self": "You can't duel yourself 😅 Tag a rival fan: **/duel @friend**",
        "duel_bot": "Bots don't support a club 🤖 Tag a real fan.",
        "duel_limit": "You've used all {n} duels for today. Come back tomorrow!",
        "duel_open": "⚔️ <@{a}> ({ca}) challenges <@{b}> to a **Fan War duel**!\n<@{b}>, accept and defend your club — winner's club gets **+5**.",
        "duel_accept": "⚔️ Accept",
        "duel_notyou": "This duel isn't yours — start your own with **/duel @friend**.",
        "duel_needteam": "Pick your club first with **/team**, then hit Accept again.",
        "duel_done": "This duel is already over.",
        "duel_result": "⚔️ **{wc}** wins! <@{w}> beat <@{l}> ({lc}) — **+5** for {wc}.\nRematch? **/duel @{ln}** · Table: **/war**",
        "help": "⚽ **Fan War — how to play**\n**/team** — pick your club\n**/hit** — +10 points for your club, once a day\n**/war** — the live world table\n**/duel @friend** — challenge a rival fan\n**/invite** — add Fan War to another server\n**/promote** — (admins) enter your server in the Server War\n\n🏆 **Server War:** every hit and duel scores for your server. The #1 server each week is advertised in EVERY server running Fan War.\nFans on Discord and Telegram fight in the same war. Free, no ads, needs no permissions.",
        "myserver": "\n🏟️ Your server: **#{rank}** in the Server War this week ({s} pts). #1 gets advertised in every Fan War server!",
        "spot": "\n\n📣 **Server of the week:** {n} — {s} pts → {url}",
        "spot_btn": "🏆 Server of the week",
        "promote_ok": "✅ **{n}** is in the Server War! Every /hit (+10) and duel win (+5) by your members scores for you.\nIf you finish #1 this week, your invite is shown in every server running Fan War. Rally your members: **/team** then **/hit** every day!",
        "promote_bad": "That doesn't look like a server invite. Use a permanent link like **https://discord.gg/yourcode**.",
        "promote_perm": "Only server admins (Manage Server) can enter the server in the Server War.",
        "promote_dm": "Use **/promote** inside your server.",
        "tg_tip": "\n📱 **/link** your Telegram — your daily Telegram penalty counts **DOUBLE (+20)** for this server!",
        "link": "📱 **Link Telegram → double points for your server**\nTap the button, press **Start** in Telegram, and take your daily penalty there.\nEvery day you play on Telegram adds **+20** to this server in the Server War (a /hit here is +10).",
        "link_btn": "📱 Link Telegram (x2)",
    },
    "he": {
        "need_team": "⚽ קודם בחר קבוצה: כתוב **/team** ובחר את הקבוצה שלך.",
        "bad_team": "לא מצאתי את הקבוצה. כתוב **/team** ובחר מהרשימה.",
        "joined": "{e} נכנסת! אתה נלחם בשביל **{c}** במלחמת האוהדים העולמית ({n} אוהדים בצד שלך).\nעכשיו כתוב **/hit** כדי להוסיף נקודות לקבוצה היום.",
        "hit": "💥 +10 ל**{c}**!\n{c}: **{p}** נקודות (מקום {rank} בעולם)\n{r}: **{rp}** נקודות\n{status}\n🔥 רצף: **{streak}** ימים ברצף\n\n⚔️ הזמן אוהד יריב: **/duel @חבר**\nתחזור מחר כדי לשמור על הרצף.",
        "ahead": "🔥 אתם מובילים על היריבה ב-{d}!",
        "behind": "⚠️ היריבה מובילה ב-{d}. תקרא לחברים!",
        "tie": "⚖️ שוויון מוחלט מול היריבה!",
        "done": "✅ כבר הכית היום בשביל **{c}**. המכה הבאה: מחר (מתאפס ב-21:00).\nכתוב **/war** לטבלה העולמית.",
        "servers": "\n\n🏟️ **השרתים המובילים השבוע**\n{rows}",
        "war": "🌍 **מלחמת האוהדים העולמית** — טבלה חיה\n{rows}{servers}\n\n🎮 {players} אוהדים | 🏟️ {guilds} שרתי דיסקורד + טלגרם\nבחר צד: **/team**, ואז **/hit** כל יום.",
        "invite": "הוסף את **מלחמת האוהדים** לכל שרת בלחיצה אחת — כל השרת נכנס למלחמה העולמית:",
        "add": "➕ הוסף לשרת שלך",
        "me": "🎮 לשחק בכל מקום",
        "tg": "📱 לשחק גם בטלגרם",
        "hq": "⚔️ לשרת של מלחמת האוהדים",
        "duel_self": "אי אפשר להתמודד מול עצמך 😅 תייג אוהד יריב: **/duel @חבר**",
        "duel_bot": "לבוטים אין קבוצה 🤖 תייג אוהד אמיתי.",
        "duel_limit": "ניצלת את כל {n} הדו-קרבות של היום. תחזור מחר!",
        "duel_open": "⚔️ <@{a}> ({ca}) מזמין את <@{b}> ל**דו-קרב אוהדים**!\n<@{b}>, קבל והגן על הקבוצה שלך — הקבוצה המנצחת מקבלת **+5**.",
        "duel_accept": "⚔️ קבל",
        "duel_notyou": "הדו-קרב הזה לא שלך — פתח משלך עם **/duel @חבר**.",
        "duel_needteam": "קודם בחר קבוצה עם **/team**, ואז לחץ שוב על קבל.",
        "duel_done": "הדו-קרב הזה כבר נגמר.",
        "duel_result": "⚔️ **{wc}** ניצחה! <@{w}> גבר על <@{l}> ({lc}) — **+5** ל{wc}.\nריוונג'? **/duel @{ln}** · טבלה: **/war**",
        "help": "⚽ **מלחמת האוהדים — איך משחקים**\n**/team** — בחר קבוצה\n**/hit** — +10 נקודות לקבוצה שלך, פעם ביום\n**/war** — הטבלה העולמית החיה\n**/duel @חבר** — דו-קרב מול אוהד יריב\n**/invite** — הוסף את המשחק לשרת אחר\n**/promote** — (מנהלים) רשום את השרת למלחמת השרתים\n\n🏆 **מלחמת השרתים:** כל מכה ודו-קרב נספרים לשרת שלכם. השרת במקום 1 בכל שבוע מפורסם בכל השרתים שמשחקים.\nאוהדים בדיסקורד ובטלגרם נלחמים באותה מלחמה. חינם, בלי פרסומות.",
        "myserver": "\n🏟️ השרת שלכם: **מקום {rank}** במלחמת השרתים השבוע ({s} נק'). המקום הראשון מפורסם בכל השרתים!",
        "spot": "\n\n📣 **שרת השבוע:** {n} — {s} נק' → {url}",
        "spot_btn": "🏆 שרת השבוע",
        "promote_ok": "✅ **{n}** נכנס למלחמת השרתים! כל /hit (+10) וכל ניצחון בדו-קרב (+5) של החברים שלכם נספר לשרת.\nמי שמסיים ראשון השבוע — הקישור שלו מוצג בכל השרתים שמשחקים. תגייסו את החברים: **/team** ואז **/hit** כל יום!",
        "promote_bad": "זה לא נראה כמו קישור הזמנה. שימו קישור קבוע כמו **https://discord.gg/הקוד-שלכם**.",
        "promote_perm": "רק מנהלי שרת (Manage Server) יכולים לרשום את השרת למלחמת השרתים.",
        "promote_dm": "השתמשו ב-**/promote** בתוך השרת שלכם.",
        "tg_tip": "\n📱 **/link** לטלגרם — הפנדל היומי שלך בטלגרם נספר **כפול (+20)** לשרת הזה!",
        "link": "📱 **חבר את הטלגרם → נקודות כפולות לשרת**\nלחץ על הכפתור, לחץ **Start** בטלגרם ובעט שם את הפנדל היומי.\nכל יום שאתה משחק בטלגרם מוסיף **+20** לשרת הזה במלחמת השרתים (/hit כאן הוא +10).",
        "link_btn": "📱 חיבור לטלגרם (x2)",
    },
}

COMMANDS = [
    {"name": "team", "description": "Pick your club and join the world Fan War",
     "description_localizations": {"he": "בחר קבוצה והצטרף למלחמת האוהדים העולמית"},
     "options": [{"type": 3, "name": "club", "description": "Your club", "required": True, "autocomplete": True}]},
    {"name": "hit", "description": "Add today's +10 points to your club",
     "description_localizations": {"he": "הוסף את ה-+10 היומי לקבוצה שלך"}},
    {"name": "war", "description": "World Fan War live table",
     "description_localizations": {"he": "הטבלה החיה של מלחמת האוהדים"}},
    {"name": "duel", "description": "Challenge a rival fan — winner's club gets +5",
     "description_localizations": {"he": "הזמן אוהד יריב לדו-קרב — הקבוצה המנצחת מקבלת +5"},
     "options": [{"type": 6, "name": "rival", "description": "The fan you challenge", "required": True}]},
    {"name": "promote", "description": "Admins: enter your server in the Server War — #1 gets advertised everywhere",
     "description_localizations": {"he": "מנהלים: רשמו את השרת למלחמת השרתים — המקום הראשון מפורסם בכל השרתים"},
     "options": [{"type": 3, "name": "invite", "description": "A permanent invite link to your server", "required": True}]},
    {"name": "link", "description": "Link Telegram — your daily Telegram play counts double for this server",
     "description_localizations": {"he": "חבר את הטלגרם — המשחק היומי שם נספר כפול לשרת הזה"}},
    {"name": "help", "description": "How to play Fan War",
     "description_localizations": {"he": "איך משחקים"}},
    {"name": "invite", "description": "Add Fan War to another server",
     "description_localizations": {"he": "הוסף את המשחק לשרת אחר"}},
]


class DiscordGame:
    """Game logic. handle() takes a Discord interaction dict and returns the interaction response dict."""

    def __init__(self, db, data, app_id="", tg_link="https://t.me/DerbyFanWarBot", now=time.time, rng=None):
        import random
        self.db, self.now, self.rng = db, now, rng or random.random
        self.db.row_factory = sqlite3.Row
        self.db.executescript(DSCHEMA)
        for col in ("invite TEXT", "nsfw INTEGER DEFAULT 0"):
            try:
                self.db.execute(f"ALTER TABLE dguilds ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass  # column already there
        self.clubs, self.rivalries = data["clubs"], data["rivalries"]
        self.app_id, self.tg_link = app_id, tg_link

    # ---------- helpers ----------
    def q(self, sql, *a):
        cur = self.db.execute(sql, a)
        self.db.commit()
        return cur

    def one(self, sql, *a):
        return self.db.execute(sql, a).fetchone()

    def day(self):
        return datetime.fromtimestamp(self.now() + 3 * 3600, TZ).strftime("%Y-%m-%d")

    def name(self, cid, lang):
        c = self.clubs[cid]
        return f"{c['emoji']} {c.get(lang) or c['en']}"

    def rival(self, cid):
        for r in (self.rivalries.values() if isinstance(self.rivalries, dict) else self.rivalries):
            if r["a"] == cid:
                return r["b"]
            if r["b"] == cid:
                return r["a"]
        return None

    def power(self, cid):
        r = self.one("SELECT power FROM cpower WHERE club=?", cid)
        return r["power"] if r else 0

    def invite_url(self):
        return (f"https://discord.com/oauth2/authorize?client_id={self.app_id}"
                "&scope=bot+applications.commands&permissions=0")

    def user_install_url(self):
        return f"https://discord.com/oauth2/authorize?client_id={self.app_id}&integration_type=1&scope=applications.commands"

    def week(self):
        return datetime.fromtimestamp(self.now() - 7 * 86400 + 3 * 3600, TZ).strftime("%Y-%m-%d")

    def board(self):
        """Server War: this week's score per server (hits x10 + duel wins x5), best first."""
        w = self.week()
        rows = self.db.execute(
            "SELECT g.id, g.name, g.invite, g.nsfw, "
            "(SELECT COUNT(*) FROM dhits h WHERE h.guild=g.id AND h.day>=?)*10 + "
            "(SELECT COUNT(*) FROM dduels d WHERE d.guild=g.id AND d.day>=? AND d.winner IS NOT NULL)*5 + "
            "(SELECT COUNT(*) FROM dbonus b WHERE b.guild=g.id AND b.day>=?)*20 AS s "
            "FROM dguilds g WHERE g.left_at IS NULL ORDER BY s DESC, g.joined", (w, w, w)).fetchall()
        return [r for r in rows if r["s"] > 0]

    def spotlight(self):
        """The best server this week that entered with /promote, is not adult-only and is not banned."""
        ban = set((self.one("SELECT v FROM meta WHERE k='dban'") or {"v": ""})["v"].split(","))
        for r in self.board():
            if r["invite"] and r["nsfw"] not in (1, 3) and r["id"] not in ban:
                return r
        return None

    def buttons(self, lang, spot=None):
        row = [{"type": 2, "style": 5, "label": T[lang]["hq"], "url": HQ},
               {"type": 2, "style": 5, "label": T[lang]["tg"], "url": self.tg_link + "?start=dc"}]
        if self.app_id:
            row.insert(0, {"type": 2, "style": 5, "label": T[lang]["add"], "url": self.invite_url()})
            row.insert(1, {"type": 2, "style": 5, "label": T[lang]["me"], "url": self.user_install_url()})
        if spot:
            row.append({"type": 2, "style": 5, "label": T[lang]["spot_btn"], "url": spot["invite"]})
        return [{"type": 1, "components": row}]

    def reply(self, text, lang, buttons=True, spot=None):
        d = {"content": text, "allowed_mentions": {"parse": []}}
        if buttons:
            d["components"] = self.buttons(lang, spot)
        return {"type": 4, "data": d}

    # ---------- interactions ----------
    def handle(self, it):
        lang = "he" if str(it.get("locale", "")).startswith("he") else "en"
        member = it.get("member") or {}
        user = member.get("user") or it.get("user") or {}
        uid, uname = str(user.get("id", "")), user.get("global_name") or user.get("username") or "?"
        guild = str(it.get("guild_id") or "")
        data = it.get("data") or {}
        cmd = data.get("name")
        opts = {o["name"]: o.get("value") for o in data.get("options", [])}
        if it.get("type") == 3:  # button press
            return self.duel_button(it, lang, uid, user)
        if it.get("type") == 4:  # autocomplete for /team
            typed = str(opts.get("club") or "").lower()
            hits = [(cid, c) for cid, c in self.clubs.items()
                    if typed in c["en"].lower() or typed in c.get("he", "") or typed == cid]
            hits.sort(key=lambda x: (x[1]["region"] == "il", x[1]["en"]))
            return {"type": 8, "data": {"choices": [{"name": f"{c['en']} / {c.get('he', '')}"[:100], "value": cid}
                                                     for cid, c in hits[:25]]}}
        if cmd == "team":
            cid = str(opts.get("club") or "")
            if cid not in self.clubs:  # typed a name instead of picking
                cid = next((k for k, c in self.clubs.items() if cid.lower() in (c["en"].lower(), c.get("he"))), "")
            if not cid:
                return self.reply(T[lang]["bad_team"], lang, False)
            self.q("INSERT INTO dusers(id, name, club, guild, joined) VALUES(?,?,?,?,?) "
                   "ON CONFLICT(id) DO UPDATE SET club=excluded.club, name=excluded.name",
                   uid, uname, cid, guild, int(self.now()))
            n = self.one("SELECT COUNT(*) FROM dusers WHERE club=?", cid)[0]
            return self.reply(T[lang]["joined"].format(e=self.clubs[cid]["emoji"], c=self.name(cid, lang), n=n), lang, False)
        u = self.one("SELECT * FROM dusers WHERE id=?", uid)
        if cmd == "hit":
            if not u or u["club"] not in self.clubs:
                return self.reply(T[lang]["need_team"], lang, False)
            cid, day = u["club"], self.day()
            if self.one("SELECT 1 FROM dhits WHERE day=? AND user_id=?", day, uid):
                return self.reply(T[lang]["done"].format(c=self.name(cid, lang)), lang)
            self.q("INSERT INTO dhits VALUES(?,?,?,?)", day, uid, cid, guild)
            self.q("INSERT INTO cpower(club, power) VALUES(?, 10) ON CONFLICT(club) DO UPDATE SET power=power+10", cid)
            p, r = self.power(cid), self.rival(cid)
            rp = self.power(r) if r else 0
            rank = self.one("SELECT COUNT(*) FROM cpower WHERE power>?", p)[0] + 1
            streak, d = 0, datetime.strptime(day, "%Y-%m-%d")
            while self.one("SELECT 1 FROM dhits WHERE day=? AND user_id=?", d.strftime("%Y-%m-%d"), uid) and streak < 365:
                streak, d = streak + 1, d - timedelta(days=1)
            mine = ""
            if guild:
                b = self.board()
                pos = next((i for i, r in enumerate(b, 1) if r["id"] == guild), 0)
                if pos:
                    mine = T[lang]["myserver"].format(rank=pos, s=b[pos - 1]["s"])
            status = (T[lang]["ahead"].format(d=p - rp) if p > rp else
                      T[lang]["behind"].format(d=rp - p) if p < rp else T[lang]["tie"])
            return self.reply(T[lang]["hit"].format(c=self.name(cid, lang), p=p, rank=rank,
                                                    r=self.name(r, lang) if r else "-", rp=rp, status=status,
                                                    streak=streak) + mine + (T[lang]["tg_tip"] if guild else ""),
                              lang, spot=self.spotlight())
        if cmd == "war":
            rows = self.db.execute("SELECT club, power FROM cpower WHERE club IN (%s) ORDER BY power DESC LIMIT 10"
                                   % ",".join("?" * len(self.clubs)), tuple(self.clubs)).fetchall()
            medals = ["🥇", "🥈", "🥉"]
            body = "\n".join(f"{medals[i] if i < 3 else f'{i + 1}.'} {self.name(r['club'], lang)} — **{r['power']}**"
                             for i, r in enumerate(rows)) or "—"
            top = self.board()[:5]
            servers = T[lang]["servers"].format(rows="\n".join(
                f"{i}. {r['name'][:40]} — {r['s']}" for i, r in enumerate(top, 1))) if top else ""
            spot = self.spotlight()
            if spot:
                servers += T[lang]["spot"].format(n=spot["name"][:40], s=spot["s"], url=spot["invite"])
            return self.reply(T[lang]["war"].format(
                rows=body, servers=servers, players=self.one("SELECT COUNT(*) FROM dusers")[0],
                guilds=self.one("SELECT COUNT(*) FROM dguilds WHERE left_at IS NULL")[0]), lang, spot=spot)
        if cmd == "invite":
            return self.reply(T[lang]["invite"], lang)
        if cmd == "link":
            return self.link(lang, uid, guild)
        if cmd == "promote":
            return self.promote(lang, member, guild, str(opts.get("invite") or ""))
        if cmd == "duel":
            return self.duel_start(it, lang, uid, u, opts, guild)
        if cmd == "help":
            return self.reply(T[lang]["help"], lang)
        return self.reply(T[lang]["need_team"], lang, False)

    def promote(self, lang, member, guild, link):
        if not guild:
            return self.plain(T[lang]["promote_dm"])
        if not int(member.get("permissions") or 0) & MANAGE_GUILD:
            return self.plain(T[lang]["promote_perm"])
        m = INVITE_RE.match(link.strip())
        if not m:
            return self.plain(T[lang]["promote_bad"])
        url = "https://discord.gg/" + m.group(1)
        self.q("INSERT INTO dguilds(id, name, members, joined) VALUES(?, '?', 0, ?) ON CONFLICT(id) DO NOTHING",
               guild, int(self.now()))
        self.q("UPDATE dguilds SET invite=?, left_at=NULL WHERE id=?", url, guild)
        n = self.one("SELECT name FROM dguilds WHERE id=?", guild)["name"]
        return self.reply(T[lang]["promote_ok"].format(n=n), lang)

    def link(self, lang, uid, guild):
        import secrets
        code = secrets.token_hex(5)
        self.q("INSERT INTO dlinks(code, discord_id, guild, created) VALUES(?,?,?,?)", code, uid, guild, int(self.now()))
        return {"type": 4, "data": {"content": T[lang]["link"], "flags": 64, "components": [{"type": 1, "components": [
            {"type": 2, "style": 5, "label": T[lang]["link_btn"], "url": f"{self.tg_link}?start=d{code}"}]}]}}

    def plain(self, text):
        return {"type": 4, "data": {"content": text, "flags": 64}}

    def duel_start(self, it, lang, uid, u, opts, guild):
        if not u or u["club"] not in self.clubs:
            return self.plain(T[lang]["need_team"])
        rival = str(opts.get("rival") or "")
        users = ((it.get("data") or {}).get("resolved") or {}).get("users") or {}
        if rival == uid:
            return self.plain(T[lang]["duel_self"])
        if (users.get(rival) or {}).get("bot"):
            return self.plain(T[lang]["duel_bot"])
        if self.one("SELECT COUNT(*) FROM dduels WHERE day=? AND a=?", self.day(), uid)[0] >= DUELS_PER_DAY:
            return self.plain(T[lang]["duel_limit"].format(n=DUELS_PER_DAY))
        did = self.q("INSERT INTO dduels(day, a, b, guild) VALUES(?,?,?,?)", self.day(), uid, rival, guild).lastrowid
        return {"type": 4, "data": {
            "content": T[lang]["duel_open"].format(a=uid, b=rival, ca=self.name(u["club"], lang)),
            "allowed_mentions": {"users": [rival]},
            "components": [{"type": 1, "components": [
                {"type": 2, "style": 1, "label": T[lang]["duel_accept"], "custom_id": f"duel:{did}"}]}]}}

    def duel_button(self, it, lang, uid, user):
        cid = ((it.get("data") or {}).get("custom_id") or "")
        if not cid.startswith("duel:"):
            return self.plain(T[lang]["duel_done"])
        d = self.one("SELECT * FROM dduels WHERE id=?", int(cid[5:] or 0))
        if not d or d["winner"]:
            return self.plain(T[lang]["duel_done"])
        if uid != d["b"]:
            return self.plain(T[lang]["duel_notyou"])
        ua = self.one("SELECT * FROM dusers WHERE id=?", d["a"])
        ub = self.one("SELECT * FROM dusers WHERE id=?", d["b"])
        if not ub or ub["club"] not in self.clubs:
            return self.plain(T[lang]["duel_needteam"])
        pa, pb = self.power(ua["club"]), self.power(ub["club"])
        # underdog edge: the weaker club's fan wins a little more often, so every duel stays exciting
        edge = 0.5 + max(-0.15, min(0.15, (pb - pa) / max(1, (pa + pb) * 4)))
        a_wins = self.rng() < edge
        w, l = (ua, ub) if a_wins else (ub, ua)
        self.q("UPDATE dduels SET winner=? WHERE id=?", w["id"], d["id"])
        self.q("INSERT INTO cpower(club, power) VALUES(?, 5) ON CONFLICT(club) DO UPDATE SET power=power+5", w["club"])
        text = T[lang]["duel_result"].format(wc=self.name(w["club"], lang), lc=self.name(l["club"], lang),
                                             w=w["id"], l=l["id"], ln=l["name"] or "rival")
        return {"type": 7, "data": {"content": text, "allowed_mentions": {"parse": []}, "components": self.buttons(lang)}}

    def guild_join(self, g):
        self.q("INSERT INTO dguilds(id, name, members, joined) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
               "name=excluded.name, members=CASE WHEN excluded.members>0 THEN excluded.members ELSE members END, "
               "left_at=NULL", str(g.get("id")), g.get("name", "?"), int(g.get("member_count") or 0), int(self.now()))
        if "nsfw_level" in g:
            self.q("UPDATE dguilds SET nsfw=? WHERE id=?", int(g.get("nsfw_level") or 0), str(g.get("id")))

    def guild_leave(self, g):
        if not g.get("unavailable"):
            self.q("UPDATE dguilds SET left_at=? WHERE id=?", int(self.now()), str(g.get("id")))


# ---------- network: REST + Gateway ----------
def rest(method, path, token, body=None):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bot {token}", "User-Agent": UA,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        print("discord rest", method, path, e.code, e.read()[:300])
        return None
    except Exception as e:  # network trouble: caller retries
        print("discord rest", method, path, e)
        return None


def respond(it, resp):
    url = f"{API}/interactions/{it['id']}/{it['token']}/callback"
    req = urllib.request.Request(url, method="POST", data=json.dumps(resp).encode(),
                                 headers={"User-Agent": UA, "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        print("discord respond failed", e)


class WS:
    """Minimal websocket client (text frames, client masking, ping/pong)."""

    def __init__(self, host, path):
        raw = socket.create_connection((host, 443), timeout=90)
        self.s = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        self.s.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nUser-Agent: {UA}\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.s.recv(1)
            if not chunk:
                raise ConnectionError("handshake closed")
            head += chunk
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise ConnectionError(head[:100])
        self.lock = threading.Lock()

    def _read(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.s.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("socket closed")
            buf += chunk
        return buf

    def send(self, obj, opcode=1):
        data = json.dumps(obj).encode() if opcode == 1 else obj
        mask = os.urandom(4)
        n = len(data)
        head = bytes([0x80 | opcode])
        head += bytes([0x80 | n]) if n < 126 else (bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536
                                                    else bytes([0x80 | 127]) + struct.pack(">Q", n))
        with self.lock:
            self.s.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self):
        msg = b""
        while True:
            b1, b2 = self._read(2)
            op, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if op == 8:
                raise ConnectionError(f"closed {payload[:2].hex()} {payload[2:80]!r}")
            if op == 9:
                self.send(payload, 10)
                continue
            if op == 10:
                continue
            msg += payload
            if b1 & 0x80:
                return json.loads(msg)

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass


def run_discord(token, db_path, data, on_ready=None, tg_link="https://t.me/DerbyFanWarBot"):
    """Run forever: connect, identify, answer interactions, reconnect on any failure."""
    me = None
    while me is None:
        me = rest("GET", "/oauth2/applications/@me", token)
        if me is None:
            time.sleep(60)
    app_id = me["id"]
    game = DiscordGame(sqlite3.connect(db_path, timeout=30), data, app_id, tg_link)
    if rest("PUT", f"/applications/{app_id}/commands", token, commands()) is None:
        rest("PUT", f"/applications/{app_id}/commands", token, COMMANDS)  # user install not enabled yet
    if on_ready:
        on_ready(game.invite_url(), me.get("name", "bot"))
    while True:
        ws = None
        try:
            ws = WS("gateway.discord.gg", "/?v=10&encoding=json")
            hello = ws.recv()
            interval = hello["d"]["heartbeat_interval"] / 1000
            state = {"seq": None, "alive": True}

            def beat():
                while state["alive"]:
                    time.sleep(interval)
                    if state["alive"]:
                        try:
                            ws.send({"op": 1, "d": state["seq"]})
                        except Exception:
                            state["alive"] = False
            threading.Thread(target=beat, daemon=True).start()
            ws.send({"op": 2, "d": {"token": token, "intents": 1,
                                    "properties": {"os": "linux", "browser": "fanwar", "device": "fanwar"}}})
            while state["alive"]:
                ev = ws.recv()
                if ev.get("s") is not None:
                    state["seq"] = ev["s"]
                op, t, d = ev.get("op"), ev.get("t"), ev.get("d")
                if op == 1:
                    ws.send({"op": 1, "d": state["seq"]})
                elif op in (7, 9):
                    break
                elif t in ("GUILD_CREATE", "GUILD_UPDATE"):
                    game.guild_join(d)
                elif t == "GUILD_DELETE":
                    game.guild_leave(d)
                elif t == "INTERACTION_CREATE":
                    try:
                        respond(d, game.handle(d))
                    except Exception as e:
                        print("discord interaction error", e)
            state["alive"] = False
        except Exception as e:
            print("discord gateway:", e)
        finally:
            if ws:
                ws.close()
        time.sleep(5)


def commands():
    """Every command except /promote also works when a player installs Fan War on their own account
    (integration type 1), so anyone can play in any server or DM without an admin adding the bot."""
    out = []
    for c in COMMANDS:
        c = dict(c)
        if c["name"] == "promote":
            c["integration_types"], c["contexts"] = [0], [0]
        else:
            c["integration_types"], c["contexts"] = [0, 1], [0, 1, 2]
        out.append(c)
    return out


def start_thread(token, db_path, data, on_ready=None):
    th = threading.Thread(target=run_discord, args=(token, db_path, data, on_ready), daemon=True)
    th.start()
    return th

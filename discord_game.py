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
from datetime import datetime

API = "https://discord.com/api/v10"
UA = "DiscordBot (https://t.me/DerbyFanWarBot, 1.0)"
from zoneinfo import ZoneInfo
TZ = ZoneInfo("Asia/Jerusalem")

DSCHEMA = """
CREATE TABLE IF NOT EXISTS cpower(club TEXT PRIMARY KEY, power INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS dusers(id TEXT PRIMARY KEY, name TEXT, club TEXT, guild TEXT, joined INTEGER);
CREATE TABLE IF NOT EXISTS dhits(day TEXT, user_id TEXT, club TEXT, guild TEXT, PRIMARY KEY(day, user_id));
CREATE TABLE IF NOT EXISTS dguilds(id TEXT PRIMARY KEY, name TEXT, members INTEGER, joined INTEGER, left_at INTEGER);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""

T = {
    "en": {
        "need_team": "⚽ Pick your team first: type **/team** and choose your club.",
        "bad_team": "Couldn't find that club. Type **/team** and pick one from the list.",
        "joined": "{e} You're in! You fight for **{c}** in the world Fan War ({n} fans on your side).\nNow type **/hit** to add points to your club today.",
        "hit": "💥 +10 for **{c}**!\n{c}: **{p}** points (#{rank} in the world)\n{r}: **{rp}** points\n{status}\n\nCome back tomorrow for another hit. Bring friends: every fan = more points.",
        "ahead": "🔥 You're ahead of your rivals by {d}!",
        "behind": "⚠️ Your rivals lead by {d}. Call your friends!",
        "tie": "⚖️ Dead even with your rivals!",
        "done": "✅ You already hit for **{c}** today. Next hit: tomorrow (21:00 Israel time reset).\nType **/war** to see the world table.",
        "war": "🌍 **World Fan War** — live table\n{rows}\n\n🎮 {players} fans | 🏟️ {guilds} Discord servers + Telegram\nPick a side: **/team**, then **/hit** every day.",
        "invite": "Add **Fan War** to any server in one click — the whole server joins the world war:",
        "add": "➕ Add to your server",
        "tg": "📱 Play on Telegram too",
        "help": "⚽ **Fan War — how to play**\n**/team** — pick your club\n**/hit** — +10 points for your club, once a day\n**/war** — the live world table\n**/invite** — add Fan War to another server\n\nFans on Discord and Telegram fight in the same war. Free, no ads, needs no permissions.",
    },
    "he": {
        "need_team": "⚽ קודם בחר קבוצה: כתוב **/team** ובחר את הקבוצה שלך.",
        "bad_team": "לא מצאתי את הקבוצה. כתוב **/team** ובחר מהרשימה.",
        "joined": "{e} נכנסת! אתה נלחם בשביל **{c}** במלחמת האוהדים העולמית ({n} אוהדים בצד שלך).\nעכשיו כתוב **/hit** כדי להוסיף נקודות לקבוצה היום.",
        "hit": "💥 +10 ל**{c}**!\n{c}: **{p}** נקודות (מקום {rank} בעולם)\n{r}: **{rp}** נקודות\n{status}\n\nתחזור מחר למכה נוספת. תביא חברים: כל אוהד = עוד נקודות.",
        "ahead": "🔥 אתם מובילים על היריבה ב-{d}!",
        "behind": "⚠️ היריבה מובילה ב-{d}. תקרא לחברים!",
        "tie": "⚖️ שוויון מוחלט מול היריבה!",
        "done": "✅ כבר הכית היום בשביל **{c}**. המכה הבאה: מחר (מתאפס ב-21:00).\nכתוב **/war** לטבלה העולמית.",
        "war": "🌍 **מלחמת האוהדים העולמית** — טבלה חיה\n{rows}\n\n🎮 {players} אוהדים | 🏟️ {guilds} שרתי דיסקורד + טלגרם\nבחר צד: **/team**, ואז **/hit** כל יום.",
        "invite": "הוסף את **מלחמת האוהדים** לכל שרת בלחיצה אחת — כל השרת נכנס למלחמה העולמית:",
        "add": "➕ הוסף לשרת שלך",
        "tg": "📱 לשחק גם בטלגרם",
        "help": "⚽ **מלחמת האוהדים — איך משחקים**\n**/team** — בחר קבוצה\n**/hit** — +10 נקודות לקבוצה שלך, פעם ביום\n**/war** — הטבלה העולמית החיה\n**/invite** — הוסף את המשחק לשרת אחר\n\nאוהדים בדיסקורד ובטלגרם נלחמים באותה מלחמה. חינם, בלי פרסומות.",
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
    {"name": "help", "description": "How to play Fan War",
     "description_localizations": {"he": "איך משחקים"}},
    {"name": "invite", "description": "Add Fan War to another server",
     "description_localizations": {"he": "הוסף את המשחק לשרת אחר"}},
]


class DiscordGame:
    """Game logic. handle() takes a Discord interaction dict and returns the interaction response dict."""

    def __init__(self, db, data, app_id="", tg_link="https://t.me/DerbyFanWarBot", now=time.time):
        self.db, self.now = db, now
        self.db.row_factory = sqlite3.Row
        self.db.executescript(DSCHEMA)
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

    def buttons(self, lang):
        row = [{"type": 2, "style": 5, "label": T[lang]["tg"], "url": self.tg_link + "?start=dc"}]
        if self.app_id:
            row.insert(0, {"type": 2, "style": 5, "label": T[lang]["add"], "url": self.invite_url()})
        return [{"type": 1, "components": row}]

    def reply(self, text, lang, buttons=True):
        d = {"content": text, "allowed_mentions": {"parse": []}}
        if buttons:
            d["components"] = self.buttons(lang)
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
            status = (T[lang]["ahead"].format(d=p - rp) if p > rp else
                      T[lang]["behind"].format(d=rp - p) if p < rp else T[lang]["tie"])
            return self.reply(T[lang]["hit"].format(c=self.name(cid, lang), p=p, rank=rank,
                                                    r=self.name(r, lang) if r else "-", rp=rp, status=status), lang)
        if cmd == "war":
            rows = self.db.execute("SELECT club, power FROM cpower WHERE club IN (%s) ORDER BY power DESC LIMIT 10"
                                   % ",".join("?" * len(self.clubs)), tuple(self.clubs)).fetchall()
            medals = ["🥇", "🥈", "🥉"]
            body = "\n".join(f"{medals[i] if i < 3 else f'{i + 1}.'} {self.name(r['club'], lang)} — **{r['power']}**"
                             for i, r in enumerate(rows)) or "—"
            return self.reply(T[lang]["war"].format(
                rows=body, players=self.one("SELECT COUNT(*) FROM dusers")[0],
                guilds=self.one("SELECT COUNT(*) FROM dguilds WHERE left_at IS NULL")[0]), lang)
        if cmd == "invite":
            return self.reply(T[lang]["invite"], lang)
        if cmd == "help":
            return self.reply(T[lang]["help"], lang)
        return self.reply(T[lang]["need_team"], lang, False)

    def guild_join(self, g):
        self.q("INSERT INTO dguilds(id, name, members, joined) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
               "name=excluded.name, members=excluded.members, left_at=NULL",
               str(g.get("id")), g.get("name", "?"), int(g.get("member_count") or 0), int(self.now()))

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
    rest("PUT", f"/applications/{app_id}/commands", token, COMMANDS)
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
                elif t == "GUILD_CREATE":
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


def start_thread(token, db_path, data, on_ready=None):
    th = threading.Thread(target=run_discord, args=(token, db_path, data, on_ready), daemon=True)
    th.start()
    return th

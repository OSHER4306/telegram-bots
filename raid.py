"""RAID: a war game between Telegram groups. The group is the player.

Every member gets one daily hit that adds power to their group (clan).
A clan can raid another clan; the defender has RAID_SECONDS to fight back.
Winner takes power from the loser. Global league in real time.
"""
import html
import random

RAID_SECONDS = 3600
HIT_POWER = 10
RAID_HIT = 5
STEAL = 0.2

SCHEMA = """
CREATE TABLE IF NOT EXISTS clans(id INTEGER PRIMARY KEY, title TEXT, lang TEXT, power INTEGER DEFAULT 0,
  wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, joined INTEGER);
CREATE TABLE IF NOT EXISTS rhits(day TEXT, user_id INTEGER, clan INTEGER, PRIMARY KEY(day, user_id));
CREATE TABLE IF NOT EXISTS raids(id INTEGER PRIMARY KEY AUTOINCREMENT, attacker INTEGER, defender INTEGER,
  started INTEGER, ends INTEGER, atk INTEGER DEFAULT 0, def INTEGER DEFAULT 0, status TEXT DEFAULT 'live');
CREATE TABLE IF NOT EXISTS rfight(raid INTEGER, user_id INTEGER, PRIMARY KEY(raid, user_id));
"""

T = {
    "he": {
        "hello": "⚔️ <b>הקבוצה הזאת היא עכשיו שבט במלחמת הקבוצות של טלגרם!</b>\n\n"
                 "כל חבר מקבל מכה אחת ביום שמוסיפה כוח לשבט.\n"
                 "שבט חזק פושט על קבוצות אחרות ולוקח להן כוח. לקבוצה המותקפת יש שעה להתגונן.\n"
                 "יותר חברים פעילים = שבט חזק יותר בליגה העולמית 🌍",
        "hit_btn": "⚔️ מכה יומית",
        "raid_btn": "🏴 פשיטה",
        "league_btn": "🏆 ליגה",
        "add_btn": "➕ צרפו קבוצה יריבה",
        "hit_ok": "{name} הוסיף {p} כוח ל{clan} 💪 כוח השבט: <b>{power}</b>",
        "hit_done": "כבר נתת את המכה של היום. חזור מחר!",
        "fight_ok": "{name} נלחם! {side}: <b>{n}</b>",
        "fight_done": "כבר נלחמת בפשיטה הזאת",
        "no_targets": "אין עדיין שבטים אחרים לפשוט עליהם. צרפו את הבוט לקבוצה יריבה 👇",
        "pick_target": "🏴 על מי פושטים? הנה שבטים בטווח הכוח שלכם:",
        "busy": "כבר יש פשיטה פתוחה עם השבט הזה",
        "raid_start": "🏴 <b>{a}</b> פושטים על <b>{d}</b>!\nלחצו להילחם. הפשיטה נגמרת בעוד 60 דקות ⏳",
        "raid_alert": "🚨🚨 <b>{a}</b> תוקפים אותנו!\nיש לנו 60 דקות להתגונן. כל אחד לוחץ פעם אחת 👇",
        "fight_btn": "⚔️ להילחם",
        "atk": "תוקפים", "def": "מגינים",
        "won": "🏆 <b>ניצחון!</b> {w} הביסו את {l} {wa}:{la} ולקחו {p} כוח.",
        "lost": "💀 <b>הפסד.</b> {w} הביסו אותנו {wa}:{la} ולקחו {p} כוח. נקמה? 🏴",
        "league": "🏆 <b>הליגה העולמית</b>",
        "your_rank": "\nאתם במקום <b>{r}</b> מתוך {n}",
        "group_only": "המשחק עובד בקבוצות. צרפו אותי לקבוצה 👇",
    },
    "en": {
        "hello": "⚔️ <b>This group is now a clan in the Telegram Group Wars!</b>\n\n"
                 "Every member gets one daily hit that adds power to the clan.\n"
                 "Strong clans raid other groups and steal their power. A raided group has one hour to defend.\n"
                 "More active members = a stronger clan in the world league 🌍",
        "hit_btn": "⚔️ Daily hit",
        "raid_btn": "🏴 Raid",
        "league_btn": "🏆 League",
        "add_btn": "➕ Add a rival group",
        "hit_ok": "{name} added {p} power to {clan} 💪 Clan power: <b>{power}</b>",
        "hit_done": "You already hit today. Come back tomorrow!",
        "fight_ok": "{name} joined the fight! {side}: <b>{n}</b>",
        "fight_done": "You already fought in this raid",
        "no_targets": "No other clans to raid yet. Add the bot to a rival group 👇",
        "pick_target": "🏴 Who do we raid? Clans in your power range:",
        "busy": "There is already an open raid with this clan",
        "raid_start": "🏴 <b>{a}</b> are raiding <b>{d}</b>!\nTap to fight. The raid ends in 60 minutes ⏳",
        "raid_alert": "🚨🚨 <b>{a}</b> are attacking us!\nWe have 60 minutes to defend. Everyone tap once 👇",
        "fight_btn": "⚔️ Fight",
        "atk": "Attackers", "def": "Defenders",
        "won": "🏆 <b>Victory!</b> {w} beat {l} {wa}:{la} and took {p} power.",
        "lost": "💀 <b>Defeat.</b> {w} beat us {wa}:{la} and took {p} power. Revenge? 🏴",
        "league": "🏆 <b>World league</b>",
        "your_rank": "\nYou are ranked <b>{r}</b> of {n}",
        "group_only": "The game works in groups. Add me to a group 👇",
    },
}


def guess_lang(title):
    return "he" if any("֐" <= ch <= "׿" for ch in title or "") else "en"


class RaidMixin:
    """Mixed into Bot. Uses self.q, self.one, self.send, self.api, self.now, self.pen_day, self.link."""

    def raid_init(self):
        self.db.executescript(SCHEMA)

    def rt(self, lang, key, **kw):
        s = T.get(lang, T["en"]).get(key) or T["en"][key]
        return s.format(**kw) if kw else s

    def clan(self, chat):
        c = self.one("SELECT * FROM clans WHERE id=?", chat["id"])
        if c:
            return c
        title = chat.get("title") or "?"
        self.q("INSERT INTO clans(id,title,lang,joined) VALUES(?,?,?,?)", chat["id"], title, guess_lang(title), int(self.now()))
        return self.one("SELECT * FROM clans WHERE id=?", chat["id"])

    def clan_kb(self, lang):
        return [[{"text": self.rt(lang, "hit_btn"), "callback_data": "rh"},
                 {"text": self.rt(lang, "raid_btn"), "callback_data": "rr"}],
                [{"text": self.rt(lang, "league_btn"), "callback_data": "rl"},
                 {"text": self.rt(lang, "add_btn"), "url": self.link("raid", group=True)}]]

    def clan_hello(self, chat):
        c = self.clan(chat)
        self.send(chat["id"], self.rt(c["lang"], "hello"), self.clan_kb(c["lang"]))

    def raid_cmd(self, cmd, chat, frm):
        """Group commands. Returns True when handled."""
        if cmd not in ("clan", "raid", "league", "hit"):
            return False
        if chat["type"] == "private":
            lang = "he" if (frm.get("language_code") or "").startswith("he") else "en"
            self.send(chat["id"], self.rt(lang, "group_only"),
                      [[{"text": self.rt(lang, "add_btn"), "url": self.link("raid", group=True)}]])
            return True
        c = self.clan(chat)
        if cmd == "clan":
            self.clan_hello(chat)
        elif cmd == "league":
            self.send(chat["id"], self.league_text(c))
        elif cmd == "raid":
            self.pick_target(c)
        elif cmd == "hit":
            self.send(chat["id"], self.do_hit(c, frm)[1])
        return True

    def do_hit(self, c, frm):
        day = self.pen_day()
        if self.one("SELECT 1 FROM rhits WHERE day=? AND user_id=?", day, frm["id"]):
            return False, self.rt(c["lang"], "hit_done")
        self.q("INSERT INTO rhits VALUES(?,?,?)", day, frm["id"], c["id"])
        self.q("UPDATE clans SET power=power+? WHERE id=?", HIT_POWER, c["id"])
        p = self.one("SELECT power FROM clans WHERE id=?", c["id"])["power"]
        return True, self.rt(c["lang"], "hit_ok", name=html.escape(frm.get("first_name", "?")), p=HIT_POWER,
                             clan=html.escape(c["title"]), power=p)

    def league_rows(self):
        return self.db.execute("SELECT * FROM clans ORDER BY power DESC, id LIMIT 10").fetchall()

    def league_text(self, c):
        lines = [self.rt(c["lang"], "league")]
        for i, r in enumerate(self.league_rows(), 1):
            mark = " 👈" if r["id"] == c["id"] else ""
            lines.append(f"{i}. {html.escape(r['title'])} — <b>{r['power']}</b> ({r['wins']}W){mark}")
        n = self.one("SELECT COUNT(*) n FROM clans")["n"]
        rank = self.one("SELECT COUNT(*) n FROM clans WHERE power > ?", c["power"])["n"] + 1
        return "\n".join(lines) + self.rt(c["lang"], "your_rank", r=rank, n=n)

    def pick_target(self, c):
        rows = self.db.execute("SELECT * FROM clans WHERE id<>? ORDER BY ABS(power-?) LIMIT 5",
                               (c["id"], c["power"])).fetchall()
        if not rows:
            return self.send(c["id"], self.rt(c["lang"], "no_targets"),
                             [[{"text": self.rt(c["lang"], "add_btn"), "url": self.link("raid", group=True)}]])
        kb = [[{"text": f"{r['title'][:30]} ({r['power']})", "callback_data": f"ra:{r['id']}"}] for r in rows]
        self.send(c["id"], self.rt(c["lang"], "pick_target"), kb)

    def start_raid(self, c, target_id):
        d = self.one("SELECT * FROM clans WHERE id=?", target_id)
        if not d or d["id"] == c["id"]:
            return None
        if self.one("SELECT 1 FROM raids WHERE status='live' AND ((attacker=? AND defender=?) OR (attacker=? AND defender=?))",
                    c["id"], d["id"], d["id"], c["id"]):
            return "busy"
        now = int(self.now())
        cur = self.q("INSERT INTO raids(attacker,defender,started,ends) VALUES(?,?,?,?)", c["id"], d["id"], now, now + RAID_SECONDS)
        rid = cur.lastrowid
        self.send(c["id"], self.rt(c["lang"], "raid_start", a=html.escape(c["title"]), d=html.escape(d["title"])),
                  [[{"text": self.rt(c["lang"], "fight_btn"), "callback_data": f"rf:{rid}"}]])
        self.send(d["id"], self.rt(d["lang"], "raid_alert", a=html.escape(c["title"])),
                  [[{"text": self.rt(d["lang"], "fight_btn"), "callback_data": f"rf:{rid}"}]])
        return rid

    def fight(self, rid, chat_id, frm):
        r = self.one("SELECT * FROM raids WHERE id=? AND status='live'", rid)
        if not r or chat_id not in (r["attacker"], r["defender"]):
            return None
        c = self.one("SELECT * FROM clans WHERE id=?", chat_id)
        if self.one("SELECT 1 FROM rfight WHERE raid=? AND user_id=?", rid, frm["id"]):
            return self.rt(c["lang"], "fight_done")
        self.q("INSERT INTO rfight VALUES(?,?)", rid, frm["id"])
        col, side = ("atk", "atk") if chat_id == r["attacker"] else ("def", "def")
        self.q(f"UPDATE raids SET {col}={col}+? WHERE id=?", RAID_HIT, rid)
        n = self.one(f"SELECT {col} v FROM raids WHERE id=?", rid)["v"]
        self.send(chat_id, self.rt(c["lang"], "fight_ok", name=html.escape(frm.get("first_name", "?")),
                                   side=self.rt(c["lang"], side), n=n))
        return "ok"

    def resolve_raids(self):
        now = int(self.now())
        for r in self.db.execute("SELECT * FROM raids WHERE status='live' AND ends<=?", (now,)).fetchall():
            a = self.one("SELECT * FROM clans WHERE id=?", r["attacker"])
            d = self.one("SELECT * FROM clans WHERE id=?", r["defender"])
            atk_wins = r["atk"] > r["def"]
            w, l = (a, d) if atk_wins else (d, a)
            wa, la = (r["atk"], r["def"]) if atk_wins else (r["def"], r["atk"])
            prize = max(int(l["power"] * STEAL), 1 if l["power"] > 0 else 0)
            self.q("UPDATE clans SET power=power+?, wins=wins+1 WHERE id=?", prize, w["id"])
            self.q("UPDATE clans SET power=MAX(power-?,0), losses=losses+1 WHERE id=?", prize, l["id"])
            self.q("UPDATE raids SET status='done' WHERE id=?", r["id"])
            names = dict(w=html.escape(w["title"]), l=html.escape(l["title"]), wa=wa, la=la, p=prize)
            self.send(w["id"], self.rt(w["lang"], "won", **names), self.clan_kb(w["lang"]))
            self.send(l["id"], self.rt(l["lang"], "lost", **names), self.clan_kb(l["lang"]))

    def raid_callback(self, kind, rest, chat, frm, answer):
        """Returns True when handled."""
        if kind not in ("rh", "rr", "rl", "ra", "rf") or chat["type"] == "private":
            return False
        c = self.clan(chat)
        if kind == "rh":
            ok, text = self.do_hit(c, frm)
            answer(None if ok else text)
            if ok:
                self.send(chat["id"], text)
        elif kind == "rl":
            answer()
            self.send(chat["id"], self.league_text(c))
        elif kind == "rr":
            answer()
            self.pick_target(c)
        elif kind == "ra" and rest.lstrip("-").isdigit():
            res = self.start_raid(c, int(rest))
            answer(self.rt(c["lang"], "busy") if res == "busy" else None)
        elif kind == "rf" and rest.isdigit():
            res = self.fight(int(rest), chat["id"], frm)
            answer(res if res and res != "ok" else None)
        return True

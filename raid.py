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
SHOP = {"shield": (5, 3600), "boost": (10, 50)}  # stars price, effect (seconds of shield / power)
RECAP_HOUR = 20  # Israel time, daily recap in active groups

SCHEMA = """
CREATE TABLE IF NOT EXISTS clans(id INTEGER PRIMARY KEY, title TEXT, lang TEXT, power INTEGER DEFAULT 0,
  wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, joined INTEGER);
CREATE TABLE IF NOT EXISTS rhits(day TEXT, user_id INTEGER, clan INTEGER, PRIMARY KEY(day, user_id));
CREATE TABLE IF NOT EXISTS raids(id INTEGER PRIMARY KEY AUTOINCREMENT, attacker INTEGER, defender INTEGER,
  started INTEGER, ends INTEGER, atk INTEGER DEFAULT 0, def INTEGER DEFAULT 0, status TEXT DEFAULT 'live');
CREATE TABLE IF NOT EXISTS rfight(raid INTEGER, user_id INTEGER, PRIMARY KEY(raid, user_id));
CREATE TABLE IF NOT EXISTS cpower(club TEXT PRIMARY KEY, power INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS uhits(day TEXT, user_id INTEGER, club TEXT, PRIMARY KEY(day, user_id));
CREATE TABLE IF NOT EXISTS purchases(ts INTEGER, user_id INTEGER, clan INTEGER, item TEXT, stars INTEGER, charge TEXT);
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
        "w_hit_btn": "⚔️ מכה לקבוצה שלי (+10)",
        "w_league_btn": "🌍 ליגת האוהדים העולמית",
        "w_hit": "⚔️ <b>+10 כוח ל{club}!</b>\n\n{club}: <b>{p}</b>\n{rival}: <b>{rp}</b>\n\n{status}\nמחר יש מכה חדשה. כל חבר שמצטרף דרכך = עוד 3 נקודות לך.",
        "w_ahead": "🔥 אתם מובילים ב-{d}!",
        "w_behind": "😤 אתם מפגרים ב-{d}. תביא עוד אוהד!",
        "w_tie": "⚖️ שוויון מוחלט!",
        "w_done": "כבר נתת מכה היום. חזור מחר, ובינתיים תביא חבר 👇",
        "w_dare_btn": "📣 שלח לאוהד של {rival}",
        "w_dare_text": "אני ב{club} והם כבר מובילים על {rival} במלחמת האוהדים. אוהד של {rival}? בוא נראה אותך:",
        "w_league": "🌍 <b>ליגת האוהדים העולמית</b>",
        "w_need_club": "קודם בוחרים קבוצה 👇",
        "w_amb": "\n\n🏆 <b>שגרירי השבוע</b> (מי שהביא הכי הרבה אוהדים):\n{rows}",
        "w_amb_you": "\nאתה הבאת השבוע: <b>{n}</b>",
        "revenge_btn": "🔥 נקמה",
        "shop_btn": "🛒 חנות",
        "shop": "🛒 <b>חנות השבט</b>\n🛡 מגן לשעה: אי אפשר לפשוט עליכם (5 ⭐)\n⚡ חיזוק: +50 כוח לשבט מיד (10 ⭐)",
        "shield_btn": "🛡 מגן (5 ⭐)", "boost_btn": "⚡ חיזוק (10 ⭐)",
        "inv_shield": "מגן לשעה", "inv_shield_d": "שעה שבה אף שבט לא יכול לפשוט על {clan}",
        "inv_boost": "חיזוק כוח", "inv_boost_d": "+50 כוח ל{clan} מיד",
        "paid_shield": "🛡 {name} הפעיל מגן! אף אחד לא יכול לפשוט על {clan} בשעה הקרובה.",
        "paid_boost": "⚡ {name} חיזק את {clan}! +50 כוח. כוח השבט: <b>{power}</b>",
        "shielded": "לשבט הזה יש מגן פעיל. נסו שבט אחר",
        "recap": "🌙 <b>סיכום היום של {clan}</b>\n💪 כוח: <b>{power}</b> | מקום <b>{rank}</b> מתוך {n}\n👥 נתנו מכה היום: {today}\n{threat}\nמחר בבוקר המכות מתחדשות. מי שמביא קבוצה יריבה, מביא לנו יעד לפשיטה 👇",
        "threat": "⚠️ {t} רק {d} כוח מאחוריכם",
        "lead": "👑 אתם בראש הליגה!",
        "cstats": "📊 <b>הסטטיסטיקה של {clan}</b>\n\n💪 כוח: <b>{power}</b>\n🏆 מקום בליגה: <b>{rank}</b> מתוך {n}\n"
                  "⚔️ ניצחונות: {w} | הפסדים: {l}\n👥 חברים ששיחקו: <b>{players}</b> (היום: {today})\n"
                  "👁 השם שלכם הופיע בקבוצות אחרות: <b>{seen}</b> פעמים\n\nהשבט המוביל: {top}",
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
        "w_hit_btn": "⚔️ Hit for my club (+10)",
        "w_league_btn": "🌍 World fan league",
        "w_hit": "⚔️ <b>+10 power for {club}!</b>\n\n{club}: <b>{p}</b>\n{rival}: <b>{rp}</b>\n\n{status}\nNew hit tomorrow. Every friend who joins through you = 3 more points for you.",
        "w_ahead": "🔥 You lead by {d}!",
        "w_behind": "😤 You're {d} behind. Bring another fan!",
        "w_tie": "⚖️ Dead even!",
        "w_done": "You already hit today. Come back tomorrow, and bring a friend meanwhile 👇",
        "w_dare_btn": "📣 Dare a {rival} fan",
        "w_dare_text": "I'm with {club} and we're beating {rival} in the fan war. {rival} fan? Let's see you:",
        "w_league": "🌍 <b>World fan league</b>",
        "w_need_club": "Pick your club first 👇",
        "w_amb": "\n\n🏆 <b>Ambassadors of the week</b> (most fans recruited):\n{rows}",
        "w_amb_you": "\nYou recruited this week: <b>{n}</b>",
        "revenge_btn": "🔥 Revenge",
        "shop_btn": "🛒 Shop",
        "shop": "🛒 <b>Clan shop</b>\n🛡 One-hour shield: nobody can raid you (5 ⭐)\n⚡ Boost: +50 clan power now (10 ⭐)",
        "shield_btn": "🛡 Shield (5 ⭐)", "boost_btn": "⚡ Boost (10 ⭐)",
        "inv_shield": "One-hour shield", "inv_shield_d": "One hour in which no clan can raid {clan}",
        "inv_boost": "Power boost", "inv_boost_d": "+50 power for {clan} right now",
        "paid_shield": "🛡 {name} activated a shield! Nobody can raid {clan} for the next hour.",
        "paid_boost": "⚡ {name} boosted {clan}! +50 power. Clan power: <b>{power}</b>",
        "shielded": "This clan has an active shield. Try another one",
        "recap": "🌙 <b>{clan} daily recap</b>\n💪 Power: <b>{power}</b> | Rank <b>{rank}</b> of {n}\n👥 Hit today: {today}\n{threat}\nHits reset tomorrow morning. Bring a rival group and we get a new raid target 👇",
        "threat": "⚠️ {t} is only {d} power behind you",
        "lead": "👑 You lead the league!",
        "cstats": "📊 <b>{clan} stats</b>\n\n💪 Power: <b>{power}</b>\n🏆 League rank: <b>{rank}</b> of {n}\n"
                  "⚔️ Wins: {w} | Losses: {l}\n👥 Members who played: <b>{players}</b> (today: {today})\n"
                  "👁 Your name was shown in other groups: <b>{seen}</b> times\n\nTop clan: {top}",
    },
}


def guess_lang(title):
    return "he" if any("֐" <= ch <= "׿" for ch in title or "") else "en"


class RaidMixin:
    """Mixed into Bot. Uses self.q, self.one, self.send, self.api, self.now, self.pen_day, self.link."""

    def raid_init(self):
        self.db.executescript(SCHEMA)
        for col in ("shield_until INTEGER DEFAULT 0", "recap_day TEXT"):
            try:
                self.db.execute("ALTER TABLE clans ADD COLUMN " + col)
            except Exception:
                pass
        try:  # exposure counter: how many times a clan's name was shown in other groups
            self.db.execute("ALTER TABLE clans ADD COLUMN seen INTEGER DEFAULT 0")
        except Exception:
            pass

    def seen(self, ids):
        for i in ids:
            self.q("UPDATE clans SET seen=seen+1 WHERE id=?", i)

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
                 {"text": self.rt(lang, "shop_btn"), "callback_data": "rs"}],
                [{"text": self.rt(lang, "add_btn"), "url": self.link("raid", group=True)}]]

    def clan_hello(self, chat):
        c = self.clan(chat)
        self.send(chat["id"], self.rt(c["lang"], "hello"), self.clan_kb(c["lang"]))

    def raid_cmd(self, cmd, chat, frm):
        """Group commands. Returns True when handled."""
        if cmd == "admin" and chat["type"] == "private" and frm["id"] == self.owner:
            self.send(chat["id"], self.admin_text(), [[{"text": "🔄 רענן", "callback_data": "ad"}]])
            return True
        if cmd == "stats" and chat["type"] != "private":
            c = self.clan(chat)
            self.send(chat["id"], self.clan_stats(c))
            return True
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
        rows = self.league_rows()
        self.seen(r["id"] for r in rows if r["id"] != c["id"])
        for i, r in enumerate(rows, 1):
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
        self.seen(r["id"] for r in rows)
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
        if (d["shield_until"] or 0) > now:
            return "shielded"
        cur = self.q("INSERT INTO raids(attacker,defender,started,ends) VALUES(?,?,?,?)", c["id"], d["id"], now, now + RAID_SECONDS)
        rid = cur.lastrowid
        self.seen([c["id"]])
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
            self.send(l["id"], self.rt(l["lang"], "lost", **names),
                      [[{"text": self.rt(l["lang"], "revenge_btn"), "callback_data": f"ra:{w['id']}"}]] + self.clan_kb(l["lang"]))
        self.daily_recap()

    def raid_callback(self, kind, rest, chat, frm, answer):
        """Returns True when handled."""
        if kind in ("wh", "wl") and chat["type"] == "private":
            answer()
            return self.world_callback(kind, frm) or True
        if kind == "ad" and chat["type"] == "private" and frm["id"] == self.owner:
            answer("✅")
            self.send(chat["id"], self.admin_text(), [[{"text": "🔄 רענן", "callback_data": "ad"}]])
            return True
        if kind not in ("rh", "rr", "rl", "ra", "rf", "rs", "rb") or chat["type"] == "private":
            return False
        c = self.clan(chat)
        if kind == "rs":
            answer()
            self.send(chat["id"], self.rt(c["lang"], "shop"),
                      [[{"text": self.rt(c["lang"], "shield_btn"), "callback_data": "rb:shield"},
                        {"text": self.rt(c["lang"], "boost_btn"), "callback_data": "rb:boost"}]])
        elif kind == "rb" and rest in SHOP:
            answer()
            self.send_invoice(c, rest)
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
            answer(self.rt(c["lang"], res) if res in ("busy", "shielded") else None)
        elif kind == "rf" and rest.isdigit():
            res = self.fight(int(rest), chat["id"], frm)
            answer(res if res and res != "ok" else None)
        return True

    # ---------- stats ----------
    def clan_stats(self, c):
        c = self.one("SELECT * FROM clans WHERE id=?", c["id"])
        day = self.pen_day()
        players = self.one("SELECT COUNT(DISTINCT user_id) n FROM rhits WHERE clan=?", c["id"])["n"]
        today = self.one("SELECT COUNT(*) n FROM rhits WHERE clan=? AND day=?", c["id"], day)["n"]
        n = self.one("SELECT COUNT(*) n FROM clans")["n"]
        rank = self.one("SELECT COUNT(*) n FROM clans WHERE power > ?", c["power"])["n"] + 1
        top = self.one("SELECT title, power FROM clans ORDER BY power DESC, id LIMIT 1")
        return self.rt(c["lang"], "cstats", clan=html.escape(c["title"]), power=c["power"], rank=rank, n=n,
                       w=c["wins"], l=c["losses"], players=players, today=today, seen=c["seen"] or 0,
                       top=f"{html.escape(top['title'])} ({top['power']})" if top else "-")

    def dcount(self, sql, *a):
        try:
            return self.one(sql, *a)[0]
        except Exception:  # Discord tables appear once the Discord bot first runs
            return 0

    def admin_text(self):
        c = lambda sql, *a: self.one(sql, *a)[0]
        now = int(self.now())
        day_ago = now - 86400
        owner = self.owner or 0
        live = c("SELECT COUNT(*) FROM raids WHERE status='live'")
        lines = [
            "📊 <b>לוח ניהול</b>",
            "",
            "<b>👥 משתמשים</b>",
            f"סה״כ: <b>{c('SELECT COUNT(*) FROM users WHERE id<>?', owner)}</b> | חדשים ב-24 שעות: <b>{c('SELECT COUNT(*) FROM users WHERE joined>=? AND id<>?', day_ago, owner)}</b>",
            f"הגיעו דרך הזמנה: <b>{c('SELECT COUNT(*) FROM users WHERE ref_by IS NOT NULL')}</b>",
            "",
            "<b>👆 פעולות</b>",
            f"לחיצות והודעות ב-24 שעות: <b>{c('SELECT COUNT(*) FROM hits WHERE ts>=?', day_ago)}</b> | סה״כ: <b>{c('SELECT COUNT(*) FROM hits')}</b>",
            f"משתמשים פעילים ב-24 שעות: <b>{c('SELECT COUNT(DISTINCT user_id) FROM hits WHERE ts>=?', day_ago)}</b>",
            f"מכות יומיות היום: <b>{c('SELECT COUNT(*) FROM rhits WHERE day=?', self.pen_day())}</b>",
            f"מכות במלחמת האוהדים היום: <b>{c('SELECT COUNT(*) FROM uhits WHERE day=?', self.pen_day())}</b> | סה״כ: <b>{c('SELECT COUNT(*) FROM uhits')}</b>",
            "",
            "<b>⚔️ קבוצות</b>",
            f"שבטים במשחק: <b>{c('SELECT COUNT(*) FROM clans')}</b> | חדשים ב-24 שעות: <b>{c('SELECT COUNT(*) FROM clans WHERE joined>=?', day_ago)}</b>",
            f"פשיטות: <b>{c('SELECT COUNT(*) FROM raids')}</b> (פתוחות עכשיו: {live})",
            f"חשיפות של שמות קבוצות בקבוצות אחרות: <b>{c('SELECT COALESCE(SUM(seen),0) FROM clans')}</b>",
            "",
            "<b>🎮 דיסקורד</b>",
            f"שרתים: <b>{self.dcount('SELECT COUNT(*) FROM dguilds WHERE left_at IS NULL')}</b> | שחקנים: <b>{self.dcount('SELECT COUNT(*) FROM dusers')}</b> | מכות היום: <b>{self.dcount('SELECT COUNT(*) FROM dhits WHERE day=?', self.pen_day())}</b>",
            "",
            "<b>⭐ חנות</b>",
            f"רכישות: <b>{c('SELECT COUNT(*) FROM purchases')}</b> | כוכבים: <b>{c('SELECT COALESCE(SUM(stars),0) FROM purchases')}</b>",
        ]
        top = self.db.execute("SELECT title, power, wins, seen FROM clans ORDER BY power DESC LIMIT 5").fetchall()
        if top:
            lines += ["", "<b>🏆 השבטים המובילים</b>"] + [
                f"{i}. {html.escape(r['title'])} — {r['power']} כוח, {r['wins']} ניצחונות, {r['seen'] or 0} חשיפות"
                for i, r in enumerate(top, 1)]
        refs = self.db.execute("SELECT r.name, COUNT(*) n FROM users u JOIN users r ON r.id=u.ref_by "
                               "GROUP BY r.id ORDER BY n DESC LIMIT 5").fetchall()
        if refs:
            lines += ["", "<b>🤝 המגייסים המובילים</b>"] + [
                f"{i}. {html.escape(r['name'] or '?')} — {r['n']}" for i, r in enumerate(refs, 1)]
        hitters = self.db.execute("SELECT user_id, COUNT(*) n FROM rhits GROUP BY user_id ORDER BY n DESC LIMIT 5").fetchall()
        if hitters:
            names = {r["id"]: r["name"] for r in self.db.execute("SELECT id, name FROM users")}
            lines += ["", "<b>💪 השחקנים הפעילים</b>"] + [
                f"{i}. {html.escape(names.get(r['user_id']) or str(r['user_id']))} — {r['n']} מכות" for i, r in enumerate(hitters, 1)]
        return "\n".join(lines)

    # ---------- Telegram Stars shop ----------
    def send_invoice(self, c, item):
        price = SHOP[item][0]
        self.api.call("sendInvoice", chat_id=c["id"], title=self.rt(c["lang"], "inv_" + item),
                      description=self.rt(c["lang"], "inv_" + item + "_d", clan=c["title"][:60]),
                      payload=f"{item}:{c['id']}", provider_token="", currency="XTR",
                      prices=[{"label": self.rt(c["lang"], "inv_" + item), "amount": price}])

    def on_precheckout(self, pq):
        item, _, cid = (pq.get("invoice_payload") or "").partition(":")
        ok = item in SHOP and cid.lstrip("-").isdigit() and bool(self.one("SELECT 1 FROM clans WHERE id=?", int(cid)))
        self.api.call("answerPreCheckoutQuery", pre_checkout_query_id=pq["id"], ok=ok,
                      **({} if ok else {"error_message": "Unavailable"}))

    def on_paid(self, msg):
        sp = msg["successful_payment"]
        item, _, cid = sp.get("invoice_payload", "").partition(":")
        c = self.one("SELECT * FROM clans WHERE id=?", int(cid)) if cid.lstrip("-").isdigit() else None
        if not c or item not in SHOP:
            return
        self.q("INSERT INTO purchases(ts,user_id,clan,item,stars,charge) VALUES(?,?,?,?,?,?)", int(self.now()),
               msg["from"]["id"], c["id"], item, sp.get("total_amount", 0), sp.get("telegram_payment_charge_id", ""))
        name = html.escape(msg["from"].get("first_name", "?"))
        if item == "shield":
            self.q("UPDATE clans SET shield_until=? WHERE id=?", int(self.now()) + SHOP["shield"][1], c["id"])
            self.send(c["id"], self.rt(c["lang"], "paid_shield", name=name, clan=html.escape(c["title"])))
        else:
            self.q("UPDATE clans SET power=power+? WHERE id=?", SHOP["boost"][1], c["id"])
            p = self.one("SELECT power FROM clans WHERE id=?", c["id"])["power"]
            self.send(c["id"], self.rt(c["lang"], "paid_boost", name=name, clan=html.escape(c["title"]), power=p))

    # ---------- daily recap in active groups ----------
    def daily_recap(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.fromtimestamp(self.now(), ZoneInfo("Asia/Jerusalem"))
        if now.hour < RECAP_HOUR:
            return
        day = self.pen_day()
        clans = self.db.execute("SELECT * FROM clans ORDER BY power DESC, id").fetchall()
        n = len(clans)
        for i, c in enumerate(clans):
            if c["recap_day"] == day:
                continue
            today = self.one("SELECT COUNT(*) n FROM rhits WHERE clan=? AND day=?", c["id"], day)["n"]
            self.q("UPDATE clans SET recap_day=? WHERE id=?", day, c["id"])
            if not today:
                continue  # only groups that played today get a recap
            if i == 0:
                threat = self.rt(c["lang"], "lead")
            else:
                t = clans[i + 1] if i + 1 < n else None
                threat = self.rt(c["lang"], "threat", t=html.escape(t["title"]), d=c["power"] - t["power"]) if t else ""
            self.send(c["id"], self.rt(c["lang"], "recap", clan=html.escape(c["title"]), power=c["power"], rank=i + 1,
                                       n=n, today=today, threat=threat), self.clan_kb(c["lang"]))

    # ---------- world fan war: solo play, no group or admin needed ----------
    def world_kb_row(self, lang):
        return [{"text": self.rt(lang, "w_hit_btn"), "callback_data": "wh"}]

    def cpow(self, club):
        r = self.one("SELECT power FROM cpower WHERE club=?", club)
        return r["power"] if r else 0

    def rival_of(self, club):
        rs = self.rivalries_of(club)
        if not rs:
            return None
        r = rs[0][1]
        return r["b"] if r["a"] == club else r["a"]

    def world_callback(self, kind, frm):
        u = self.user(frm)
        lang = u["lang"]
        if kind == "wl":
            rows = self.db.execute("SELECT club, power FROM cpower ORDER BY power DESC LIMIT 15").fetchall()
            lines = [self.rt(lang, "w_league")] + [f"{i}. {self.club(r['club'], lang)} — <b>{r['power']}</b>"
                                                  for i, r in enumerate(rows, 1)]
            return self.send(u["id"], "\n".join(lines) + self.ambassadors(u, lang), [self.world_kb_row(lang)])
        if not u["club"]:
            return self.send(u["id"], self.rt(lang, "w_need_club"), self.region_kb(lang))
        club, rival = u["club"], self.rival_of(u["club"])
        day = self.pen_day()
        dare = []
        if rival:
            import urllib.parse
            link = self.link(f"j{rival}_{u['id']}")
            text = self.rt(lang, "w_dare_text", club=self.club(club, lang), rival=self.club(rival, lang))
            dare = [[{"text": self.rt(lang, "w_dare_btn", rival=self.club(rival, lang)),
                      "url": "https://t.me/share/url?" + urllib.parse.urlencode({"url": link, "text": text})}]]
        league = [[{"text": self.rt(lang, "w_league_btn"), "callback_data": "wl"}]]
        if self.one("SELECT 1 FROM uhits WHERE day=? AND user_id=?", day, u["id"]):
            return self.send(u["id"], self.rt(lang, "w_done"), dare + league)
        self.q("INSERT INTO uhits VALUES(?,?,?)", day, u["id"], club)
        self.q("INSERT INTO cpower(club, power) VALUES(?, ?) ON CONFLICT(club) DO UPDATE SET power=power+?", club, 10, 10)
        p, rp = self.cpow(club), self.cpow(rival) if rival else 0
        status = (self.rt(lang, "w_ahead", d=p - rp) if p > rp else
                  self.rt(lang, "w_behind", d=rp - p) if p < rp else self.rt(lang, "w_tie"))
        self.send(u["id"], self.rt(lang, "w_hit", club=self.club(club, lang), p=p,
                                   rival=self.club(rival, lang) if rival else "-", rp=rp, status=status)
                  + self.ambassadors(u, lang), dare + league)

    def ambassadors(self, u, lang):
        week = int(self.now()) - 7 * 86400
        rows = self.db.execute("SELECT r.name, r.club, COUNT(*) n FROM users x JOIN users r ON r.id=x.ref_by "
                               "WHERE x.joined>=? GROUP BY r.id ORDER BY n DESC, r.id LIMIT 3", (week,)).fetchall()
        mine = self.one("SELECT COUNT(*) n FROM users WHERE ref_by=? AND joined>=?", u["id"], week)["n"]
        medals = ["🥇", "🥈", "🥉"]
        body = "\n".join(f"{medals[i]} {html.escape(r['name'] or '?')} — {r['n']}" for i, r in enumerate(rows))
        out = self.rt(lang, "w_amb", rows=body) if rows else ""
        return out + self.rt(lang, "w_amb_you", n=mine)

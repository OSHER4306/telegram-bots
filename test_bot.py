"""End-to-end simulation against a fake Telegram API. Run: python3 test_bot.py"""
import itertools
import bot as B


class FakeApi:
    def __init__(self):
        self.calls, self.ids, self.admins = [], itertools.count(100), set()

    def call(self, method, **p):
        self.calls.append((method, p))
        if method == "getMe":
            return {"username": "DerbyTestBot"}
        if method == "getChatMember":
            return {"status": "administrator" if p["user_id"] in self.admins else "member"}
        if method == "sendMessage":
            return {"message_id": next(self.ids)}
        return True

    def sent(self, chat):
        return [p for m, p in self.calls if m == "sendMessage" and p["chat_id"] == chat]

    def last(self, chat):
        return self.sent(chat)[-1]


clock = [1_800_000_000]
api = FakeApi()
bot = B.Bot(api, ":memory:", owner_id=1, now=lambda: clock[0])
uid = itertools.count(1)

G1 = {"id": -1001, "type": "supergroup", "title": "Yellow Army"}
G2 = {"id": -1002, "type": "supergroup", "title": "Red Devils TLV"}
def user(i, lang="he"): return {"id": i, "first_name": f"U{i}", "language_code": lang}
def priv(i): return {"id": i, "type": "private"}
def msg(chat, frm, text): bot.handle({"update_id": next(uid), "message": {"chat": chat, "from": frm, "text": text}})
def cb(chat, frm, data): bot.handle({"update_id": next(uid), "callback_query": {"id": "x", "from": frm, "data": data, "message": {"chat": chat}}})
def count(sql, *a): return bot.one(sql, *a)[0]

# 1. private signup: region -> club
msg(priv(1), user(1), "/start")
assert "rg:il" in str(api.last(1)["reply_markup"])
cb(priv(1), user(1), "rg:il")
cb(priv(1), user(1), "cl:mta")
assert count("SELECT COUNT(*) FROM users WHERE club='mta'") == 1
assert "jmta_1" in api.last(1)["text"]

# 2. recruit link registers a friend and credits the referrer
msg(priv(2), user(2), "/start jmta_1")
assert bot.one("SELECT club, ref_by FROM users WHERE id=2")["ref_by"] == 1
# self-referral and second use are ignored
msg(priv(2), user(2), "/start jhta_2")
assert bot.one("SELECT club FROM users WHERE id=2")["club"] == "mta"

# 3. bot added to group; non-admin cannot pick, admin can
bot.handle({"update_id": next(uid), "my_chat_member": {"chat": G1, "from": user(1),
            "old_chat_member": {"status": "left"}, "new_chat_member": {"status": "member"}}})
cb(G1, user(2), "cl:mta")
assert count("SELECT COUNT(*) FROM groups") == 0
api.admins.add(1)
cb(G1, user(1), "cl:mta")
assert bot.one("SELECT club, lang FROM groups WHERE id=-1001")["club"] == "mta"

# 4. challenge: card with startgroup link, rival group accepts by adding the bot
msg(G1, user(2), "/derby")
assert "dr:tlv" in str(api.last(-1001)["reply_markup"])
cb(G1, user(2), "dr:tlv")
card = api.sent(-1001)[-2]
assert "startgroup=c1" in str(card["reply_markup"]) and "Yellow Army" in card["text"]
msg(G1, user(1), "/start@DerbyTestBot c1")          # own group cannot accept
assert bot.one("SELECT status FROM challenges WHERE id=1")["status"] == "open"
msg(G2, user(3), "/start@DerbyTestBot c1")
assert bot.one("SELECT club FROM groups WHERE id=-1002")["club"] == "hta"
assert bot.one("SELECT status, to_group FROM challenges WHERE id=1")["to_group"] == -1002
assert "Red Devils TLV" in api.last(-1001)["text"]

# 5. owner adds a match; non-owner cannot
msg(priv(2), user(2), "/addmatch mta hta 2027-01-20 20:30")
assert count("SELECT COUNT(*) FROM matches") == 0
msg(priv(1), user(1), "/addmatch mta hta 2027-01-20 20:30")
m = bot.one("SELECT * FROM matches WHERE id=1")
assert m["kickoff"] > clock[0]
assert count("SELECT COUNT(*) FROM posts WHERE match_id=1") == 2
assert "start=p1_-1001" in str(api.last(-1001)["reply_markup"])

# 6. predictions through deep link; newcomer is auto-registered to the group's club
msg(priv(1), user(1), "/start p1_-1001"); cb(priv(1), user(1), "ph:1:-1001:2"); cb(priv(1), user(1), "pa:1:-1001:2:1")
msg(priv(2), user(2), "/start p1_-1001"); cb(priv(2), user(2), "ph:1:-1001:0"); cb(priv(2), user(2), "pa:1:-1001:0:3")
msg(priv(4), user(4), "/start p1_-1002"); cb(priv(4), user(4), "ph:1:-1002:1"); cb(priv(4), user(4), "pa:1:-1002:1:0")
assert bot.one("SELECT club FROM users WHERE id=4")["club"] == "hta"
assert count("SELECT COUNT(*) FROM predictions") == 3
assert any(mth == "editMessageText" and "2" in p["text"] for mth, p in api.calls)
# changing a prediction replaces it
cb(priv(2), user(2), "pa:1:-1001:1:1")
assert count("SELECT COUNT(*) FROM predictions") == 3
# malformed callback data is ignored
cb(priv(2), user(2), "pa:1:-1001:99:1"); cb(priv(2), user(2), "pa:abc")
assert bot.one("SELECT hg, ag FROM predictions WHERE user_id=2")["hg"] == 1

# 7. lock at kickoff
clock[0] = m["kickoff"] + 1
cb(priv(4), user(4), "pa:1:-1002:5:5")
assert bot.one("SELECT hg FROM predictions WHERE user_id=4")["hg"] == 1
msg(priv(5), user(5), "/start p1_-1002")
assert count("SELECT COUNT(*) FROM predictions") == 3

# 8. result: exact=3, outcome=1, miss=0; duel verdict in both groups
msg(priv(1), user(1), "/result 1 2 1")
pts = {r["user_id"]: r["points"] for r in bot.db.execute("SELECT * FROM predictions")}
assert pts == {1: 3, 2: 0, 4: 1}, pts
r1, r2 = api.last(-1001)["text"], api.last(-1002)["text"]
assert "ניצחתם" in r1 and "3 מול 1" in r1, r1
assert "הפסדתם" in r2 and "1 מול 3" in r2, r2
assert "U1" in r1 and "startgroup=new" in str(api.last(-1001)["reply_markup"])

# 9. scoring unit checks
assert B.points(0, 0, 1, 1) == 1 and B.points(1, 1, 1, 1) == 3 and B.points(2, 0, 0, 1) == 0

# 10. English flow for a world club, group language follows region
msg(priv(9), user(9, "en"), "/start jrma_1")
assert "Real Madrid" in api.sent(9)[0]["text"]
msg(priv(1), user(1), "/stats")
assert "5" in api.last(1)["text"]

# 11. public recruiter table: user 1 recruited users 2 and 9
msg(priv(4), user(4), "/top")
top = api.last(4)["text"]
assert "1. U1" in top and "<b>2</b>" in top, top
msg(G1, user(2), "/top")
assert "U1" in api.last(-1001)["text"]

# 12. with no OWNER_ID, the first private /start claims ownership and it survives a restart
import os, tempfile
path = os.path.join(tempfile.mkdtemp(), "t.db")
api2 = FakeApi()
b2 = B.Bot(api2, path, owner_id=0)
b2.handle({"update_id": 1, "message": {"chat": priv(77), "from": user(77), "text": "/start"}})
b2.handle({"update_id": 2, "message": {"chat": priv(88), "from": user(88), "text": "/start"}})
assert b2.owner == 77
assert B.Bot(FakeApi(), path, owner_id=0).owner == 77

# 13. daily penalty: mta fans 1,2 v hta fan 4; keepers are the majority dive of each side
api3 = FakeApi(); clk = [1_800_000_000]
b3 = B.Bot(api3, ":memory:", owner_id=1, now=lambda: clk[0])
def cb3(i, data): b3.handle({"update_id": 1, "callback_query": {"id": "x", "from": user(i), "data": data, "message": {"chat": priv(i)}}})
for i, club in ((1, "mta"), (2, "mta"), (4, "hta")):
    b3.handle({"update_id": 1, "message": {"chat": priv(i), "from": user(i), "text": "/start j%s_0" % club}})
b3.q("INSERT INTO groups VALUES(-5,'G','mta','he',0)")
cb3(1, "pn"); assert "ps:0" in str(api3.last(1)["reply_markup"])
cb3(1, "ps:0"); cb3(1, "pd:0:2")      # shoots left, keeper dives right
cb3(2, "ps:1"); cb3(2, "pd:1:2")      # shoots centre, keeper dives right
cb3(4, "ps:2"); cb3(4, "pd:2:0")      # hta shoots right (saved), hta keeper dives left
cb3(4, "pd:9:9")                       # malformed, ignored
assert b3.one("SELECT COUNT(*) c FROM pen")["c"] == 3
b3.resolve_penalties()                 # same day: nothing settles yet
assert b3.one("SELECT COUNT(*) c FROM pen WHERE goal IS NOT NULL")["c"] == 0
clk[0] += 86400
b3.resolve_penalties()
goals = {r["user_id"]: r["goal"] for r in b3.db.execute("SELECT * FROM pen")}
assert goals == {1: 0, 2: 1, 4: 0}, goals   # user1 hit the keeper's side, user2 scored, user4 saved
res = api3.last(-5)["text"]
assert "<b>1</b> : <b>0</b>" in res and "2 מול 1" in res, res
n_msgs = len(api3.sent(-5)); b3.resolve_penalties(); assert len(api3.sent(-5)) == n_msgs   # settles once
assert b3.user_points(2) == 1
cb3(2, "ps:1"); cb3(2, "pd:1:1")
assert "2" in api3.last(2)["text"]     # two-day streak

# 15. activity log: owner gets batched live updates of other users' actions, not his own
clk5 = [1_800_000_000]; api5 = FakeApi()
b5 = B.Bot(api5, ":memory:", owner_id=0, now=lambda: clk5[0])
def m5(i, text): b5.handle({"update_id": 1, "message": {"chat": priv(i), "from": user(i), "text": text}})
def c5(i, data): b5.handle({"update_id": 1, "callback_query": {"id": "x", "from": user(i), "data": data, "message": {"chat": priv(i)}}})
m5(1, "/start"); c5(1, "rg:il"); c5(1, "cl:mta")      # owner
m5(2, "/start j" + "mta_1")                           # recruited by owner
c5(2, "ps:0"); c5(2, "pd:0:1")
assert len(b5.pending) == 3, b5.pending               # new user, club with recruiter, penalty
assert "גויס" in b5.pending[1]
b5.flush_log(); assert not any("יומן" in p["text"] for p in api5.sent(1))   # under a minute: wait
clk5[0] += 61; b5.flush_log()
note = api5.last(1)["text"]
assert "יומן" in note and "U2" in note and "פנדל" in note, note
assert not b5.pending
m5(1, "/log"); assert "U1" in api5.last(1)["text"] and "U2" in api5.last(1)["text"]
m5(1, "/notify off"); m5(3, "/start"); clk5[0] += 61; n = len(api5.sent(1)); b5.flush_log()
assert len(api5.sent(1)) == n                          # muted: nothing sent, still logged
assert b5.one("SELECT COUNT(*) c FROM events")["c"] == 6
m5(2, "/log"); assert "בעלים" not in api5.last(2)["text"] and "יומן" not in api5.last(2)["text"]

# 16. reports: touches, clicks, plays; daily report once at 21:05
from datetime import datetime as _dt
base = int(_dt(2027, 1, 10, 20, 0, tzinfo=B.TZ).timestamp())
clk6 = [base]; api6 = FakeApi()
b6 = B.Bot(api6, ":memory:", owner_id=0, now=lambda: clk6[0])
def m6(i, text): b6.handle({"update_id": 1, "message": {"chat": priv(i), "from": user(i), "text": text}})
def c6(i, data): b6.handle({"update_id": 1, "callback_query": {"id": "x", "from": user(i), "data": data, "message": {"chat": priv(i)}}})
m6(1, "/start")                                  # owner, not counted
m6(2, "/start jmta_1"); c6(2, "ps:0"); c6(2, "pd:0:1")
m6(3, "/start")                                  # touched, did not register a club
m6(1, "/report")
rep = api6.last(1)["text"]
assert "נגעו בבוט: 2 אנשים (4 פעולות)" in rep and "לחיצות על כפתורים: 2" in rep, rep
assert "שיחקו (פנדל או ניחוש): 1" in rep and "נרשמו: 2" in rep, rep
n = len(api6.sent(1)); b6.daily_report(); assert len(api6.sent(1)) == n      # 20:00, too early
clk6[0] = base + 70 * 60; b6.daily_report(); assert "דוח" in api6.last(1)["text"]
n = len(api6.sent(1)); b6.daily_report(); assert len(api6.sent(1)) == n      # once a day
m6(2, "/report"); assert "דוח" not in api6.last(2)["text"]

# 17. club-branded bot: plain /start signs the fan to the brand club in one step
B.BRAND_CLUB = "bjr"
api7 = FakeApi(); b7 = B.Bot(api7, ":memory:", owner_id=1)
b7.handle({"update_id": 1, "message": {"chat": priv(5), "from": user(5), "text": "/start"}})
assert b7.one("SELECT club FROM users WHERE id=5")["club"] == "bjr"
assert "בית" in api7.sent(5)[0]["text"]
B.BRAND_CLUB = ""

# 18. 20:00 reminder: only registered fans who have not played and did not opt out, once a day
base8 = int(_dt(2027, 1, 10, 20, 1, tzinfo=B.TZ).timestamp())
clk8 = [base8]; api8 = FakeApi(); b8 = B.Bot(api8, ":memory:", owner_id=1, now=lambda: clk8[0])
def m8(i, text): b8.handle({"update_id": 1, "message": {"chat": priv(i), "from": user(i), "text": text}})
def c8(i, data): b8.handle({"update_id": 1, "callback_query": {"id": "x", "from": user(i), "data": data, "message": {"chat": priv(i)}}})
for i in (2, 3, 4): m8(i, "/start jmta_0")
c8(2, "ps:0"); c8(2, "pd:0:1")            # played already
m8(4, "/remind off")                       # opted out
before = {i: len(api8.sent(i)) for i in (2, 3, 4)}
b8.daily_reminder()
assert len(api8.sent(3)) == before[3] + 1 and "⏰" in api8.last(3)["text"]
assert len(api8.sent(2)) == before[2] and len(api8.sent(4)) == before[4]
b8.daily_reminder(); assert len(api8.sent(3)) == before[3] + 1   # once a day

# 19. referral reward: recruiter is notified and gets 3 points, recruit gets 1
msg(priv(900), user(900), "/start")
cb(priv(900), user(900), "rg:il")
cb(priv(900), user(900), "cl:hta")
p0 = bot.user_points(900)
msg(priv(901), user(901), "/start jhta_900")
assert "+3" in api.last(900)["text"], api.last(900)["text"]
assert bot.user_points(900) == p0 + 3 and bot.user_points(901) == 1

# 20. inline share: card with census text and a personal recruit link
bot.handle({"update_id": next(uid), "inline_query": {"id": "iq1", "from": user(900), "query": ""}})
m, p = api.calls[-1]
assert m == "answerInlineQuery" and "jhta_900" in str(p["results"][0]["reply_markup"])
assert p["results"][0]["input_message_content"]["parse_mode"] == "HTML"

# 21. RAID: bot joins a group -> clan created with game buttons
GA = {"id": -2001, "type": "supergroup", "title": "אוהדי באר שבע"}
GB = {"id": -2002, "type": "supergroup", "title": "Barca Fans"}
for g in (GA, GB):
    bot.handle({"update_id": next(uid), "my_chat_member": {"chat": g, "from": user(1),
                "old_chat_member": {"status": "left"}, "new_chat_member": {"status": "member"}}})
assert bot.one("SELECT lang FROM clans WHERE id=-2001")["lang"] == "he"
assert bot.one("SELECT lang FROM clans WHERE id=-2002")["lang"] == "en"
assert any("callback_data': 'rh'" in str(p.get("reply_markup")) for p in api.sent(-2001))

# 22. daily hit: once per user per day
cb(GA, user(50), "rh"); cb(GA, user(51), "rh"); cb(GA, user(50), "rh")
assert bot.one("SELECT power FROM clans WHERE id=-2001")["power"] == 20
cb(GB, user(60), "rh")
assert bot.one("SELECT power FROM clans WHERE id=-2002")["power"] == 10

# 23. raid: A attacks B, both groups alerted, fight once each, winner takes power
cb(GA, user(50), "rr")
assert "ra:-2002" in str(api.last(-2001)["reply_markup"])
cb(GA, user(50), "ra:-2002")
rid = bot.one("SELECT id FROM raids")["id"]
assert "🚨" in api.last(-2002)["text"]
cb(GA, user(50), f"rf:{rid}"); cb(GA, user(51), f"rf:{rid}"); cb(GA, user(51), f"rf:{rid}")
cb(GB, user(60), f"rf:{rid}")
r = bot.one("SELECT atk, def FROM raids WHERE id=?", rid)
assert (r["atk"], r["def"]) == (10, 5)
clock[0] += 3601
bot.resolve_raids()
assert bot.one("SELECT power, wins FROM clans WHERE id=-2001")["wins"] == 1
assert bot.one("SELECT power FROM clans WHERE id=-2001")["power"] == 22
assert bot.one("SELECT power FROM clans WHERE id=-2002")["power"] == 8
assert "🏆" in api.sent(-2001)[-1]["text"] and "Defeat" in api.sent(-2002)[-1]["text"]

# 24. league + private command points to groups
msg(GA, user(50), "/league")
assert "22" in api.last(-2001)["text"]
msg(priv(50), user(50), "/raid")
assert "startgroup=raid" in str(api.last(50)["reply_markup"])
msg(GB, user(60), "/start@DerbyTestBot raid")
assert "Telegram Group Wars" in api.last(-2002)["text"]

# 25. owner dashboard (private, owner only) with refresh, and group stats with exposure
msg(priv(1), user(1), "/admin")
assert "לוח ניהול" in api.last(1)["text"] and "callback_data': 'ad'" in str(api.last(1)["reply_markup"])
assert "Barca Fans" in api.last(1)["text"]
cb(priv(1), user(1), "ad")
assert "לוח ניהול" in api.last(1)["text"]
n_before = len(api.sent(50))
msg(priv(50), user(50), "/admin")
assert all("לוח ניהול" not in p["text"] for p in api.sent(50)[n_before:])
msg(GB, user(60), "/stats")
st = api.last(-2002)["text"]
assert "Barca Fans stats" in st and "shown in other groups" in st
assert bot.one("SELECT seen FROM clans WHERE id=-2002")["seen"] >= 1

# 26. Stars shop: invoice in XTR, pre-checkout approved, payment applies the shield, shield blocks raids
cb(GA, user(50), "rs")
assert "rb:shield" in str(api.last(-2001)["reply_markup"])
cb(GA, user(50), "rb:shield")
m, p = api.calls[-1]
assert m == "sendInvoice" and p["currency"] == "XTR" and p["prices"][0]["amount"] == 5 and p["payload"] == "shield:-2002" or p["payload"] == "shield:-2001"
bot.handle({"update_id": next(uid), "pre_checkout_query": {"id": "pq1", "from": user(50), "invoice_payload": "shield:-2001"}})
m, p = api.calls[-1]
assert m == "answerPreCheckoutQuery" and p["ok"] is True
bot.handle({"update_id": next(uid), "message": {"chat": GA, "from": user(50),
            "successful_payment": {"invoice_payload": "shield:-2001", "total_amount": 5, "telegram_payment_charge_id": "x1"}}})
assert "🛡" in api.last(-2001)["text"]
cb(GB, user(60), "ra:-2001")
m, p = api.calls[-1]
assert m == "answerCallbackQuery" and "shield" in p.get("text", "")
bot.handle({"update_id": next(uid), "message": {"chat": GB, "from": user(60),
            "successful_payment": {"invoice_payload": "boost:-2002", "total_amount": 10, "telegram_payment_charge_id": "x2"}}})
assert bot.one("SELECT power FROM clans WHERE id=-2002")["power"] == 58
msg(priv(1), user(1), "/admin")
assert "כוכבים: <b>15</b>" in api.last(1)["text"]

# 27. revenge button after a loss + daily recap only in groups that played today
clock[0] += 3600
cb(GB, user(60), "ra:-2001")
rid2 = bot.one("SELECT MAX(id) m FROM raids")["m"]
cb(GA, user(50), f"rf:{rid2}")
clock[0] += 3601
bot.resolve_raids()
assert "ra:-2001" in str(api.sent(-2002)[-1]["reply_markup"]) or "ra:-2001" in str(api.sent(-2002)[-2].get("reply_markup"))
day = bot.pen_day()
bot.q("UPDATE clans SET recap_day=NULL")
from datetime import datetime as _dt
from zoneinfo import ZoneInfo as _Z
while _dt.fromtimestamp(clock[0], _Z("Asia/Jerusalem")).hour != 20:
    clock[0] += 900
bot.q("INSERT OR IGNORE INTO rhits VALUES(?,?,?)", bot.pen_day(), 777, -2001)
bot.daily_recap()
recaps = [p for p in api.sent(-2001) if "סיכום היום" in p["text"]]
assert len(recaps) == 1
bot.daily_recap()
assert len([p for p in api.sent(-2001) if "סיכום היום" in p["text"]]) == 1

# 28. world fan war: solo daily hit for your club, rival comparison, dare link to the rival's join page, league
msg(priv(910), user(910), "/start jfcb")
home = api.last(910)
assert "callback_data': 'wh'" in str(home["reply_markup"])
cb(priv(910), user(910), "wh")
r = api.last(910)
assert "+10" in r["text"] and "jrma_910" in str(r["reply_markup"])
cb(priv(910), user(910), "wh")
assert "כבר נתת" in api.last(910)["text"]
msg(priv(911), user(911, "en"), "/start jrma_910")
cb(priv(911), user(911, "en"), "wh")
assert "Real Madrid" in api.last(911)["text"] and "Dead even" in api.last(911)["text"]
assert bot.one("SELECT ref_by FROM users WHERE id=911")["ref_by"] == 910
cb(priv(911), user(911, "en"), "wl")
assert "World fan league" in api.last(911)["text"]
msg(priv(1), user(1), "/admin")
assert "מלחמת האוהדים היום: <b>2</b>" in api.last(1)["text"]

# 29. ambassadors of the week: recruiters ranked, shown after a hit and in the league
cb(priv(911), user(911, "en"), "wl")
assert "Ambassadors of the week" in api.last(911)["text"] and "U910" in api.last(911)["text"]
msg(priv(912), user(912), "/start jfcb_910")
cb(priv(912), user(912), "wh")
assert "שגרירי השבוע" in api.last(912)["text"] and "U910 — 2" in api.last(912)["text"]

# 30. Discord: same world war, slash commands, shared cpower with Telegram
import discord_game as DG
dg = DG.DiscordGame(bot.db, B.DATA, app_id="999", now=lambda: clock[0])
bot.row = None
def it(cmd, uid_, locale="en-US", **opts):
    return dg.handle({"type": 2, "id": "1", "token": "t", "guild_id": "g1", "locale": locale,
                      "member": {"user": {"id": uid_, "username": f"d{uid_}"}},
                      "data": {"name": cmd, "options": [{"name": k, "value": v} for k, v in opts.items()]}})
assert "Pick your team" in it("hit", "5001")["data"]["content"]
ac = dg.handle({"type": 4, "locale": "en-US", "user": {"id": "5001"},
                "data": {"name": "team", "options": [{"name": "club", "value": "madr"}]}})
assert ac["type"] == 8 and ac["data"]["choices"][0]["value"] == "rma"
before = dg.power("rma")
assert "You're in" in it("team", "5001", club="rma")["data"]["content"]
r = it("hit", "5001")
assert "+10" in r["data"]["content"] and dg.power("rma") == before + 10
assert "Streak: **1**" in r["data"]["content"] and "/duel" in r["data"]["content"]
assert "client_id=999" in r["data"]["components"][0]["components"][0]["url"]
assert "already hit" in it("hit", "5001")["data"]["content"] and dg.power("rma") == before + 10
assert "נכנסת" in it("team", "5002", locale="he", club="Barcelona")["data"]["content"]
dg.guild_join({"id": "g1", "name": "Madridistas", "member_count": 500})
w = it("war", "5002", locale="he")["data"]["content"]
assert "מלחמת האוהדים" in w and "2 אוהדים" in w and "1 שרתי" in w
assert "השרתים המובילים" in w and "Madridistas — 10" in w
dg.guild_leave({"id": "g1"})
assert dg.one("SELECT COUNT(*) FROM dguilds WHERE left_at IS NULL")[0] == 0
assert "Add **Fan War**" in it("invite", "5003")["data"]["content"]
assert "/hit" in it("help", "5003")["data"]["content"] and "איך משחקים" in it("help", "5003", locale="he")["data"]["content"]
msg(priv(1), user(1), "/admin")
assert "שחקנים: <b>2</b>" in api.last(1)["text"] and "מכות היום: <b>1</b>" in api.last(1)["text"]
# owner stores a Discord token from private chat; message deleted; others cannot
msg(priv(1), user(1), "/discord " + "x" * 60)
assert bot.one("SELECT v FROM meta WHERE k='discord_token'")["v"] == "x" * 60
assert any(m == "deleteMessage" for m, p in api.calls)
msg(priv(912), user(912), "/discord " + "y" * 60)
assert bot.one("SELECT v FROM meta WHERE k='discord_token'")["v"] == "x" * 60

# 31. Discord duels: tag a rival fan, they accept, winner's club +5, limits
dg.rng = lambda: 0.0  # challenger wins
def duel(a, b, bot=False):
    return dg.handle({"type": 2, "id": "1", "token": "t", "guild_id": "g1", "locale": "en-US",
                      "member": {"user": {"id": a, "username": f"d{a}"}},
                      "data": {"name": "duel", "options": [{"name": "rival", "value": b}],
                               "resolved": {"users": {b: {"id": b, "bot": bot}}}}})
def press(uid_, cid):
    return dg.handle({"type": 3, "id": "1", "token": "t", "guild_id": "g1", "locale": "en-US",
                      "member": {"user": {"id": uid_, "username": f"d{uid_}"}}, "data": {"custom_id": cid}})
assert "yourself" in duel("5001", "5001")["data"]["content"]
assert "Bots" in duel("5001", "999", bot=True)["data"]["content"]
r = duel("5001", "5002")
assert "<@5002>" in r["data"]["content"] and r["data"]["allowed_mentions"] == {"users": ["5002"]}
cid = r["data"]["components"][0]["components"][0]["custom_id"]
assert "isn't yours" in press("5003", cid)["data"]["content"]
before = dg.power("rma")
res = press("5002", cid)
assert res["type"] == 7 and "Real Madrid" in res["data"]["content"] and dg.power("rma") == before + 5
assert "already over" in press("5002", cid)["data"]["content"]
assert "umBMNSrVj" in str(res["data"]["components"])
for _ in range(4): duel("5001", "5002")
assert "all 5 duels" in duel("5001", "5002")["data"]["content"]
assert "Pick your team" in duel("5009", "5001")["data"]["content"]
dg.guild_join({"id": "g1", "name": "Renamed HQ", "member_count": 5})
assert dg.one("SELECT name FROM dguilds WHERE id='g1'")["name"] == "Renamed HQ"
# 32. streak counts consecutive days
clock[0] += 86400
assert "Streak: **2**" in it("hit", "5001")["data"]["content"]

# 33. Server War: /promote (admins only), server rank on /hit, spotlight in /war, owner can hide a server
def pr(uid_, link, perms="0", guild="g1", locale="en-US"):
    return dg.handle({"type": 2, "id": "1", "token": "t", "guild_id": guild, "locale": locale,
                      "member": {"user": {"id": uid_, "username": f"d{uid_}"}, "permissions": perms},
                      "data": {"name": "promote", "options": [{"name": "invite", "value": link}]}})
assert "Only server admins" in pr("5001", "https://discord.gg/abc")["data"]["content"]
assert "doesn't look like" in pr("5001", "https://evil.com/x", perms="32")["data"]["content"]
assert "Server War" in pr("5001", "discord.com/invite/Renamed1", perms="32")["data"]["content"]
assert dg.one("SELECT invite FROM dguilds WHERE id='g1'")["invite"] == "https://discord.gg/Renamed1"
assert "promote" in [c["name"] for c in DG.COMMANDS]
r = it("hit", "5002")
assert "Your server: **#1**" in r["data"]["content"]
assert "https://discord.gg/Renamed1" in str(r["data"]["components"])
w = it("war", "5003")["data"]["content"]
assert "Server of the week:** Renamed HQ" in w and "discord.gg/Renamed1" in w
# a second server that has more activity but no invite is ranked, yet the spotlight stays with a promoted one
dg.guild_join({"id": "g2", "name": "Adults", "member_count": 50, "nsfw_level": 3})
for u_ in ("6001", "6002", "6003", "6004"):
    dg.handle({"type": 2, "id": "1", "token": "t", "guild_id": "g2", "locale": "en-US",
               "member": {"user": {"id": u_, "username": "x"}}, "data": {"name": "team", "options": [{"name": "club", "value": "rma"}]}})
    dg.handle({"type": 2, "id": "1", "token": "t", "guild_id": "g2", "locale": "en-US",
               "member": {"user": {"id": u_, "username": "x"}}, "data": {"name": "hit", "options": []}})
assert dg.board()[0]["id"] == "g2" and dg.spotlight()["id"] == "g1"
pr("6001", "https://discord.gg/adults", perms="8", guild="g2")
assert dg.spotlight()["id"] == "g1"  # adult-only servers are never advertised
msg(priv(1), user(1), "/dservers")
assert "Renamed HQ" in api.last(1)["text"] and "📣" in api.last(1)["text"]
msg(priv(1), user(1), "/dban g1")
assert dg.spotlight() is None and "הוסתר" in api.last(1)["text"]
msg(priv(1), user(1), "/dban g1")
assert dg.spotlight()["id"] == "g1"
msg(priv(912), user(912), "/dban g1")
assert dg.spotlight()["id"] == "g1"
assert "מלחמת השרתים" in it("help", "5003", locale="he")["data"]["content"]
dg.guild_join({"id": "g1", "name": "Renamed HQ"})  # GUILD_UPDATE has no member_count: keep the old number
assert dg.one("SELECT members FROM dguilds WHERE id='g1'")["members"] == 5

# 34. /link: Discord player links Telegram; their daily Telegram penalty adds +20 to the Discord server
it("team", "5005", club="rma")
assert "/link" in it("hit", "5005")["data"]["content"]
lk = it("link", "5001")
url = lk["data"]["components"][0]["components"][0]["url"]
assert lk["data"]["flags"] == 64 and "?start=d" in url and "+20" in lk["data"]["content"]
code = url.split("start=d")[1]
assert len(code) == 10
before = dict((r["id"], r["s"]) for r in dg.board())["g1"]
msg(priv(7001), user(7001, "en"), "/start d" + code)
assert any("Linked" in p.get("text", "") and "Renamed HQ" in p.get("text", "") for m, p in api.calls[-4:])
assert bot.one("SELECT club FROM users WHERE id=7001")["club"] == "rma"  # took the Discord club
cb(priv(7001), user(7001, "en"), "pd:1:2")
assert dict((r["id"], r["s"]) for r in dg.board())["g1"] == before + 20
cb(priv(7001), user(7001, "en"), "pd:2:0")  # same day again: no second bonus
assert dict((r["id"], r["s"]) for r in dg.board())["g1"] == before + 20
msg(priv(7002), user(7002), "/start d" + code)  # someone else can't reuse a used code
assert "לא תקף" in api.last(7002)["text"]
msg(priv(7003), user(7003), "/start dzzzzzzzzzz")
assert "לא תקף" in api.last(7003)["text"]
assert "link" in [c["name"] for c in DG.COMMANDS]

# 35. user install: every command but /promote can be installed on a player's own account
cs = {c["name"]: c for c in DG.commands()}
assert cs["hit"]["integration_types"] == [0, 1] and cs["hit"]["contexts"] == [0, 1, 2]
assert cs["promote"]["integration_types"] == [0]
assert "integration_types" not in DG.COMMANDS[0]  # the base list stays usable before user install is enabled
btns = it("war", "5003")["data"]["components"][0]["components"]
assert "integration_type=1" in btns[1]["url"] and len(btns) <= 5
# playing from a DM (user install, no guild) works
r = dg.handle({"type": 2, "id": "1", "token": "t", "locale": "en-US", "user": {"id": "8001", "username": "dm"},
               "data": {"name": "team", "options": [{"name": "club", "value": "fcb"}]}})
assert "You're in" in r["data"]["content"]
r = dg.handle({"type": 2, "id": "1", "token": "t", "locale": "en-US", "user": {"id": "8001", "username": "dm"},
               "data": {"name": "hit", "options": []}})
assert "+10" in r["data"]["content"] and "/link" not in r["data"]["content"]
print("ALL TESTS PASSED")

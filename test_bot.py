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

print("ALL TESTS PASSED")

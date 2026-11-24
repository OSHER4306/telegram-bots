"""End-to-end simulation of Glow against a fake Telegram API. Run: python3 test_glow.py"""
import itertools
import sqlite3
import glow as G


class FakeApi:
    def __init__(self):
        self.calls, self.ids = [], itertools.count(500)

    def call(self, method, **p):
        self.calls.append((method, p))
        if method in ("sendMessage", "sendPhoto"):
            return {"message_id": next(self.ids)}
        return True

    def to(self, chat):
        return [(m, p) for m, p in self.calls if p.get("chat_id") == chat]

    def texts(self, chat):
        return " | ".join(p.get("text") or p.get("caption") or (p.get("media") or {}).get("caption", "") for m, p in self.to(chat))


OWNER = 1
clock = [1_800_000_000]  # 10:00 in Israel
api = FakeApi()
g = G.Glow(api, sqlite3.connect(":memory:"), OWNER, "GlowTestBot", now=lambda: clock[0])
cbid = itertools.count(1)


def frm(uid, lang="he"):
    return {"id": uid, "first_name": f"u{uid}", "language_code": lang}


def msg(uid, text=None, lang="he", **extra):
    m = {"chat": {"id": uid, "type": "private"}, "from": frm(uid, lang), "message_id": 1, **extra}
    if text is not None:
        m["text"] = text
    g.handle({"message": m})


def cb(uid, data, lang="he", mid=77):
    g.handle({"callback_query": {"id": str(next(cbid)), "from": frm(uid, lang), "data": data,
                                 "message": {"message_id": mid, "chat": {"id": uid}}}})


def onboard(uid, year="1995", gender="m", pref="a", lang="he", start="/start"):
    msg(uid, start, lang)
    cb(uid, "agree", lang)
    msg(uid, year, lang)
    cb(uid, f"g:{gender}", lang)
    cb(uid, f"p:{pref}", lang)


def upload(uid, lang="he"):
    msg(uid, lang=lang, photo=[{"file_id": f"small{uid}", "width": 90, "height": 90},
                               {"file_id": f"photo{uid}", "width": 800, "height": 800}])
    msg(uid, lang=lang, video_note={"file_id": f"live{uid}"})


def rate(uid, pid, v):
    clock[0] += 2
    cb(uid, f"r:{pid}:{v}")


def pid_of(uid):
    return g.one("SELECT id FROM gphotos WHERE owner=? ORDER BY id DESC", uid)["id"]


# 1. onboarding: terms -> year -> gender -> pref; English users get English
onboard(10)
u = g.one("SELECT * FROM gusers WHERE id=10")
assert u["state"] == "ready" and u["year"] == 1995 and u["gender"] == "m" and u["pref"] == "a"
assert "סלפי" in api.texts(10)
onboard(11, lang="en")
assert "Send one selfie" in api.texts(11)

# 2. under 18 is blocked for good, even after /delete
msg(12, "/start")
cb(12, "agree")
msg(12, "2015")
assert g.one("SELECT blocked FROM gusers WHERE id=12")["blocked"] == 1 and "18" in api.texts(12)
msg(12, "/delete")
assert g.one("SELECT blocked FROM gusers WHERE id=12")["blocked"] == 1
msg(12, "/rate")
assert "אין גישה" in api.texts(12)
msg(13, "/start"); cb(13, "agree"); msg(13, "abc")
assert "4 ספרות" in api.texts(13)

# 3. upload: biggest photo kept, live video required, owner gets photo + video with approve buttons
upload(10)
p10 = pid_of(10)
assert g.one("SELECT file, status FROM gphotos WHERE id=?", p10)["file"] == "photo10"
assert g.one("SELECT status FROM gphotos WHERE id=?", p10)["status"] == "pending"
own = [m for m, p in api.to(OWNER)]
assert "sendPhoto" in own and "sendVideoNote" in own
msg(14, "/start"); cb(14, "agree"); msg(14, "1996"); cb(14, "g:f"); cb(14, "p:a")
msg(14, photo=[{"file_id": "photo14", "width": 10, "height": 10}])
msg(14, "hello")
assert "וידאו עגול" in api.texts(14)
assert g.one("SELECT status FROM gphotos WHERE owner=14")["status"] == "new"  # not sent to review without the live video

# 4. owner approves -> live; a non-owner can't approve
cb(10, f"ok:{p10}")
assert g.one("SELECT status FROM gphotos WHERE id=?", p10)["status"] == "pending"
cb(OWNER, f"ok:{p10}")
assert g.one("SELECT status FROM gphotos WHERE id=?", p10)["status"] == "live"
assert "אושרה" in api.texts(10)

# 5. rating: give-to-get, no self-rating, no double rating, speed limit
for uid in range(20, 40):
    onboard(uid, year="1994")
for uid in range(20, 33):
    rate(uid, p10, 8 if uid % 2 else 7)
s, n = g.score(p10)
assert n == 13 and s is not None and 6.0 < s < 8.0
rate(20, p10, 1)  # second rating of the same photo is ignored
assert g.score(p10)[1] == 13
cb(21, f"r:{p10}:9")  # same second as their last rating -> too fast
assert g.one("SELECT value FROM gratings WHERE rater=21 AND photo=?", p10)["value"] == 8
rate(10, p10, 10)  # can't rate yourself
assert g.score(p10)[1] == 13
msg(10, "/me")
assert "דרג עוד 10" in api.texts(10)  # locked until 10 given
assert "דרג עוד" in api.texts(10)

# 6. owner of photo rates 10 others -> unlock + score shown; score notification sent
for uid in range(20, 32):
    upload(uid)
    cb(OWNER, f"ok:{pid_of(uid)}")
for uid in range(20, 30):
    rate(10, pid_of(uid), 6)
assert "פתחת את הציון" in api.texts(10)
msg(10, "/me")
assert f"<b>{g.score(p10)[0]}</b>" in api.texts(10)
assert "יש לך ציון" in api.texts(10) or "קיבלה ציון" in api.texts(10)

# 7. the rater sees photos one message at a time (edited), never their own
eds = [p for m, p in api.to(10) if m == "editMessageMedia"]
assert eds and all(p["media"]["media"] != "photo10" for p in eds)
assert all(p.get("protect_content") for m, p in api.to(10) if m == "sendPhoto")

# 8. referral: friend rates the inviter first; friend ratings don't count in the official score
before = g.score(p10)
onboard(50, start="/start r_10")
assert g.one("SELECT ref FROM gusers WHERE id=50")["ref"] == 10
first = [p for m, p in api.to(50) if m == "sendPhoto"][0]
assert first["photo"] == "photo10"
rate(50, p10, 10)
assert g.score(p10) == before
assert g.one("SELECT friend FROM gratings WHERE rater=50")["friend"] == 1
k0 = g.one("SELECT karma FROM gusers WHERE id=10")["karma"]
for pid in [pid_of(u) for u in range(20, 30)]:
    rate(50, pid, 5)
assert g.one("SELECT karma FROM gusers WHERE id=10")["karma"] == k0 + 20
msg(51, "/start r_51")  # can't refer yourself
assert g.one("SELECT ref FROM gusers WHERE id=51")["ref"] is None

# 9. link and card
msg(10, "/link")
assert "start=r_10" in api.texts(10)
msg(10, "/card")
card = [p for m, p in api.to(10) if m == "sendMessage"][-1]
assert "Glow" in card["text"] and "share/url" in card["reply_markup"]["inline_keyboard"][0][0]["url"]

# 10. reports: a "looks under 18" report hides the photo at once and goes to the owner
cb(33, f"rr:{p10}:minor")
assert g.one("SELECT status FROM gphotos WHERE id=?", p10)["status"] == "hidden"
assert "הוסתרה" in api.texts(OWNER)
cb(OWNER, f"ok:{p10}")
assert g.one("SELECT status FROM gphotos WHERE id=?", p10)["status"] == "live"
p20 = pid_of(20)
for uid in (34, 35):
    cb(uid, f"rr:{p20}:other")
assert g.one("SELECT status FROM gphotos WHERE id=?", p20)["status"] == "live"
cb(36, f"rr:{p20}:other")
assert g.one("SELECT status FROM gphotos WHERE id=?", p20)["status"] == "hidden"

# 11. max 3 photos
for i in range(3):
    msg(21, photo=[{"file_id": f"extra{i}", "width": 5, "height": 5}])
assert "יש לך כבר 3" in api.texts(21)

# 12. notifications: at most 3 a day, none at night
clock[0] = 1_800_000_000 + 2 * 86400 - 9 * 3600  # 01:00 Israel
assert g.notify(10, "x") is False
clock[0] = 1_800_000_000 + 2 * 86400  # 10:00 Israel
assert [g.notify(10, "x") for _ in range(4)] == [True, True, True, False]

# 13. language switch, stats for the owner only, delete wipes everything
msg(10, "/lang")
assert g.one("SELECT lang FROM gusers WHERE id=10")["lang"] == "en"
msg(OWNER, "/start"); cb(OWNER, "agree"); msg(OWNER, "1990"); cb(OWNER, "g:m"); cb(OWNER, "p:a")
msg(OWNER, "/stats")
assert "משפך" in api.texts(OWNER) and "בדירוג" in api.texts(OWNER)
msg(OWNER, "/users 5")
assert "המשתמשים האחרונים" in api.texts(OWNER) and "נתן" in api.texts(OWNER)
msg(OWNER, "/u 10")
assert "👤" in api.texts(OWNER) and "דירוגים" in api.texts(OWNER)
msg(OWNER, "/u 999999")
assert "לא נמצא" in api.texts(OWNER)
for who in (20, 21):
    msg(who, "/stats"); msg(who, "/users"); msg(who, "/u 10")
    assert "משפך" not in api.texts(who) and "המשתמשים האחרונים" not in api.texts(who) and "👤" not in api.texts(who)
assert "נכנס משתמש חדש" in api.texts(OWNER)
msg(OWNER, "/feed")
assert "כבויות" in api.texts(OWNER)
n0 = len(api.to(OWNER)); msg(777, "/start")
assert len(api.to(OWNER)) == n0
msg(OWNER, "/feed")
assert "פועלות" in api.texts(OWNER)
msg(10, "/delete")
assert not g.one("SELECT 1 FROM gphotos WHERE owner=10") and not g.one("SELECT 1 FROM gratings WHERE photo=?", p10)
assert not g.one("SELECT 1 FROM gratings WHERE rater=10") and "deleted" in api.texts(10)

# 14. a rater who always gives the same number counts less
for uid in range(60, 61):
    onboard(uid)
for pid in [pid_of(u) for u in range(21, 32)]:
    rate(60, pid, 10)
assert g.weight(60) == 0.3 and g.weight(25) == 1.0

# 15. sample photos: owner-only, labelled, matched to preference, count toward unlocking, never scored
class PhotoApi(FakeApi):
    def call(self, method, **p):
        r = super().call(method, **p)
        if method == "sendPhoto" and str(p.get("photo", "")).startswith("http"):
            r["photo"] = [{"file_id": "small", "width": 90, "height": 90}, {"file_id": "big_" + p["photo"][-1], "width": 900, "height": 900}]
        return r
api2 = PhotoApi()
g2 = G.Glow(api2, sqlite3.connect(":memory:"), OWNER, "GlowTestBot", now=lambda: clock[0])
g, api = g2, api2
msg(OWNER, "/sample f https://x/1")
msg(OWNER, "/sample m https://x/2")
msg(OWNER, caption="sample f", photo=[{"file_id": "own_f", "width": 800, "height": 800}])
msg(20, "/sample f https://x/9")
assert g.one("SELECT COUNT(*) FROM gphotos WHERE owner=0 AND status='live'")[0] == 3
assert g.one("SELECT file FROM gphotos WHERE id=1")["file"] == "big_1"
msg(OWNER, "/samples")
assert "נשים 2" in api.texts(OWNER) and "גברים 1" in api.texts(OWNER)
onboard(70, pref="f"); msg(70, "/rate")
shown = [p for m, p in api.to(70) if m == "sendPhoto"]
assert shown and "דוגמה" in shown[-1]["caption"] and shown[-1]["photo"] in ("big_1", "own_f")
for _ in range(3):
    last = [p for m, p in api.calls if p.get("chat_id") == 70 and m in ("sendPhoto", "editMessageMedia")][-1]
    pid = int((last.get("reply_markup") or {"inline_keyboard": [[{"callback_data": "r:0:1"}]]})["inline_keyboard"][0][0]["callback_data"].split(":")[1])
    if pid:
        rate(70, pid, 8)
assert g.rated(70) == 2  # both women samples, never the man
assert g.one("SELECT COUNT(*) FROM gratings r JOIN gphotos p ON p.id=r.photo WHERE r.rater=70 AND p.sample='m'")[0] == 0
onboard(71, gender="f", pref="a"); msg(71, photo=[{"file_id": "real71", "width": 500, "height": 500}])
msg(71, video_note={"file_id": "v71"}); cb(OWNER, f"ok:{pid_of(71)}")
onboard(72, pref="a"); msg(72, "/rate")
first = [p for m, p in api.to(72) if m == "sendPhoto"][0]
assert first["photo"] == "real71" and "דוגמה" not in first["caption"]  # real people come before samples
msg(OWNER, "/stats")
assert "תמונות דוגמה: 3" in api.texts(OWNER)
msg(OWNER, "/sample del 1")
assert g.one("SELECT status FROM gphotos WHERE id=1")["status"] == "rejected"

# 16. rate me in the group: inline photo, anyone in the chat votes without joining, live average, no score impact
nu = g.one("SELECT COUNT(*) FROM gusers")[0]
g.handle({"inline_query": {"id": "q1", "from": frm(71), "query": ""}})
res = [p for m, p in api.calls if m == "answerInlineQuery"][-1]
assert res["results"] and res["results"][0]["photo_file_id"] == "real71" and "r_71" in str(res["results"][0]["reply_markup"])
g.handle({"inline_query": {"id": "q2", "from": frm(999), "query": ""}})
res = [p for m, p in api.calls if m == "answerInlineQuery"][-1]
assert res["results"] == [] and res["button"]["start_parameter"] == "share"
p71 = pid_of(71)
def gvote(uid, v):
    g.handle({"callback_query": {"id": str(next(cbid)), "from": frm(uid), "data": f"v:{p71}:{v}", "inline_message_id": "IM1"}})
gvote(5001, 9); gvote(5002, 7); gvote(5002, 8); gvote(71, 10)
assert g.one("SELECT COUNT(*) FROM gvotes WHERE photo=?", p71)[0] == 2
assert g.one("SELECT COUNT(*) FROM gusers")[0] == nu  # voters are not signed up
assert g.one("SELECT COUNT(*) FROM gratings WHERE photo=?", p71)[0] == 0  # never part of the real score
edit = [p for m, p in api.calls if m == "editMessageCaption" and p.get("inline_message_id") == "IM1"][-1]
assert "8.5" in edit["caption"] and "2" in edit["caption"]
toast = [p for m, p in api.calls if m == "answerCallbackQuery"][-1]
assert "שלך" in toast.get("text", "")
for i in range(3):
    gvote(5100 + i, 6)
assert "החברים בקבוצה" in api.texts(71)
msg(71, "/share")
assert "switch_inline_query" in str(api.to(71)[-1][1])
msg(OWNER, "/stats")
assert "דירוג בקבוצות: 1 תמונות שותפו" in api.texts(OWNER)

print("GLOW TESTS PASSED")

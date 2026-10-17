"""Social care: staff accounts, customers, and cases with their messages,
events and notes, spread across states, channels, agents and SLA outcomes."""
import json
import os
import math
from datetime import timedelta

from sqlalchemy import text
from werkzeug.security import generate_password_hash

from . import corpus as C
from .base import NOW, Seed, dt

PASSWORD = os.environ.get("DEMO_PASSWORD", "demo123")   # set DEMO_PASSWORD for anything reachable from the internet
STAFF = [("hira.agent", "agent"), ("bilal.agent", "agent"), ("sana.agent", "agent"), ("omar.agent", "agent"),
         ("zainab.senior", "senior_agent"), ("imran.senior", "senior_agent"), ("farah.supervisor", "supervisor"),
         ("kamran.lead", "team_lead"), ("demo.admin", "admin"), ("lumora.viewer", "bank_viewer")]
CARE_ROLES = {"agent", "senior_agent", "supervisor", "team_lead"}
FIRST = ["Ayesha", "Bilal", "Sana", "Hamza", "Maryam", "Usman", "Hira", "Ali", "Zara", "Danish", "Fatima", "Kashif",
         "Noor", "Rizwan", "Iqra", "Talha", "Mehwish", "Faisal", "Sidra", "Waqas", "Amna", "Junaid", "Rabia", "Shahid"]
LAST = ["Khan", "Ahmed", "Malik", "Sheikh", "Raza", "Qureshi", "Butt", "Siddiqui", "Hussain", "Chaudhry", "Baig", "Farooqi"]
SEGMENTS = ["retail", "retail", "retail", "premium", "sme", "corporate"]
CHANNELS = [("facebook", 0.3), ("x", 0.26), ("instagram", 0.16), ("messenger", 0.16), ("instagram_dm", 0.12)]
CLOSURES = [("resolved", 0.72), ("escalated", 0.08), ("no_response", 0.08), ("not_actionable", 0.06), ("duplicate", 0.04), ("spam", 0.02)]
REPLIES = [
 "Hi {name}, thank you for reaching out and sorry for the trouble. We have raised this with the concerned team and will update you within the day.",
 "Hello {name}, we are looking into this right now. For your security, please do not share your OTP, PIN or card number with anyone.",
 "Thanks for your patience {name}. Your issue has been resolved. Please check and let us know if anything else is needed.",
 "Dear {name}, we have escalated your case to our specialist team. Your reference number is C-{ref}. We will call you from our official helpline.",
]
TOPICS = ["cards", "app", "payments", "branch", "loans", "service", "deposits", "remittance"]


def people(sd: Seed) -> None:
    s, ws = sd.s, sd.ws
    pwd = generate_password_hash(PASSWORD)
    for username, role in STAFF:
        uid = s.execute(text("""INSERT INTO "user" (username, password_hash, role, workspace_id, active, created_at, email)
                                VALUES (:u, :p, :r, :ws, 1, :at, :e) RETURNING id"""),
                        {"u": username, "p": pwd, "r": role, "ws": ws, "at": NOW.isoformat(),
                         "e": f"{username}@lumorabank.example"}).scalar_one()
        s.execute(text("INSERT INTO user_role (user_id, role_key) VALUES (:u, :r) ON CONFLICT DO NOTHING"), {"u": uid, "r": role})
        sd.users[username] = uid
        if role in CARE_ROLES:
            s.execute(text("""INSERT INTO care_agent (workspace_id, user_id, capacity, available, last_seen)
                              VALUES (:ws, :u, :c, :a, :ls)"""),
                      {"ws": ws, "u": uid, "c": 8 if role == "agent" else 6, "a": 0 if username == "omar.agent" else 1, "ls": NOW})
    sd.bump("users", len(STAFF))


def customers(sd: Seed, n: int = 36) -> list[dict]:
    rng, out = sd.rng, []
    for i in range(n):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        platform = rng.choices([c for c, _ in CHANNELS], [w for _, w in CHANNELS])[0]
        handle = f"{name.split()[0].lower()}{rng.randint(10, 99)}"
        vip = i % 9 == 0
        cid = sd.s.execute(text("""
            INSERT INTO customer (workspace_id, display_name, platform, handle, email, phone, location, country, language, timezone,
                                  segment, account_status, vip, blocked, preferred_channel, tags, notes, created_at)
            VALUES (:ws, :n, :p, :h, :e, :ph, :loc, 'PK', :lang, 'Asia/Karachi', :seg, 'active', :vip, false, :p, :tags, :notes, :at)
            RETURNING id"""),
            {"ws": sd.ws, "n": name, "p": platform, "h": handle, "e": f"{handle}@mail.example",
             "ph": f"0300{rng.randint(1000000, 9999999)}", "loc": rng.choice(C.CITIES), "lang": rng.choice(["en", "en", "en", "ur", "roman_urdu"]),
             "seg": "premium" if vip else rng.choice(SEGMENTS), "vip": vip, "tags": "vip" if vip else "",
             "notes": "Demo customer. No real person.", "at": dt(rng.uniform(60, 700))}).scalar_one()
        out.append({"id": cid, "name": name, "handle": handle, "platform": platform, "vip": vip})
    sd.bump("customers", n)
    return out


def _closure(rng):
    return rng.choices([c for c, _ in CLOSURES], [w for _, w in CLOSURES])[0]


def cases(sd: Seed, custs: list[dict], n: int = 130) -> list[dict]:
    """Cases with messages/events/notes. Returns closed ones for the CSAT module."""
    rng, s, ws = sd.rng, sd.s, sd.ws
    staff = [sd.users[u] for u, r in STAFF if r in ("agent", "senior_agent")] + [sd.users["demo.admin"]]   # the demo login has its own queue too
    sup = sd.users["farah.supervisor"]
    closed_cases = []
    for i in range(n):
        cust = rng.choice(custs)
        age = min(59.5, rng.expovariate(1 / 13) + rng.random() * 0.5)   # skewed recent, like a live queue
        opened = dt(age, rng.randint(8, 22), rng.randint(0, 59))
        channel = cust["platform"]
        topic = rng.choice(TOPICS)
        tone_tpl = rng.choice(C.T[(topic, "neg")] if (topic, "neg") in C.T else C.T[("service", "neg")])
        body = tone_tpl.format(b=C.FOCUS, n=rng.randint(2, 6), amt="Rs 18,000", city=rng.choice(C.CITIES))
        if i % 30 == 0:
            body = rng.choice(C.CRITICAL).format(b=C.FOCUS, n=3, amt="Rs 85,000")
        recent = age < 8
        r = rng.random()
        state = ("open" if r < 0.12 else "assigned" if r < 0.25 else "in_progress" if r < 0.41 else "internal_hold" if r < 0.46
                 else "pending_approval" if r < 0.49 else "closed") if recent else ("closed" if r < 0.985 else "internal_hold")
        assignee = None if state == "open" else rng.choice(staff)
        first_min = max(0.7, rng.lognormvariate(math.log(7), 0.85))
        first_resp = None if state == "open" else opened + timedelta(minutes=first_min)   # an open case is one nobody has answered yet
        closed_at = None
        if state == "closed":
            closed_at = opened + timedelta(hours=min(60, max(0.6, rng.lognormvariate(math.log(7), 0.9))))
            if closed_at > NOW:
                closed_at = NOW - timedelta(minutes=20)
        last = closed_at or (first_resp or opened) + timedelta(minutes=rng.randint(2, 90))
        priority = "urgent" if i % 30 == 0 else rng.choices(["low", "normal", "high"], [0.15, 0.65, 0.2])[0]
        tags = [topic] + (["vip"] if cust["vip"] else []) + (["fraud"] if "fraud" in body.lower() or "unauthorized" in body.lower() else [])
        cid = s.execute(text("""
            INSERT INTO "case" (workspace_id, customer_id, channel, state, assignee_id, closure_category, opened_at, first_response_at,
                                closed_at, last_activity_at, priority, tags)
            VALUES (:ws, :cu, :ch, :st, :asg, :cl, :op, :fr, :cat, :la, :pr, CAST(:tags AS jsonb)) RETURNING id"""),
            {"ws": ws, "cu": cust["id"], "ch": channel, "st": state, "asg": assignee, "cl": _closure(rng) if state == "closed" else None,
             "op": opened, "fr": first_resp, "cat": closed_at, "la": last, "pr": priority, "tags": json.dumps(tags)}).scalar_one()
        _thread(sd, cid, cust, channel, body, opened, first_resp, closed_at, assignee, sup, state)
        if state == "closed":
            closed_cases.append({"id": cid, "customer_id": cust["id"], "channel": channel, "closed_at": closed_at})
    _held_replies(sd, sup)
    sd.bump("cases", n)
    return closed_cases


def _thread(sd, cid, cust, channel, body, opened, first_resp, closed_at, assignee, sup, state):
    rng, s, ws = sd.rng, sd.s, sd.ws

    def msg(direction, author, text_, at):
        at = min(at, NOW)
        s.execute(text("""INSERT INTO case_message (case_id, workspace_id, direction, channel, author, body, sent_at)
                          VALUES (:c, :ws, :d, :ch, :a, :b, :at)"""),
                  {"c": cid, "ws": ws, "d": direction, "ch": channel, "a": author, "b": text_, "at": at})

    def event(kind, actor, at, **detail):
        s.execute(text("INSERT INTO case_event (case_id, actor, kind, detail, at) VALUES (:c, :a, :k, CAST(:d AS jsonb), :at)"),
                  {"c": cid, "a": None if actor is None else str(actor), "k": kind, "d": json.dumps(detail), "at": at})

    msg("inbound", cust["handle"], body, opened)
    event("created", None, opened, channel=channel)
    event("message_in", None, opened)
    if assignee:
        event("assigned", sup, opened + timedelta(minutes=1), assignee_id=assignee)
    if first_resp:
        who = next((u for u, uid in sd.users.items() if uid == assignee), "agent")
        msg("outbound", who, rng.choice(REPLIES).format(name=cust["name"].split()[0], ref=cid + 1000), first_resp)
        event("message_out", assignee, first_resp)
        if rng.random() < 0.55 and state in ("closed", "in_progress", "pending_approval"):
            follow = first_resp + timedelta(minutes=rng.randint(10, 240))
            msg("inbound", cust["handle"], rng.choice(["Any update on this please?", "Still waiting, this is urgent.", "Thank you, that worked."]), follow)
            event("message_in", None, follow)
            msg("outbound", who, REPLIES[2].format(name=cust["name"].split()[0], ref=cid), follow + timedelta(minutes=rng.randint(5, 40)))
    if rng.random() < 0.28 and assignee:
        s.execute(text("INSERT INTO case_note (case_id, author_id, body, created_at) VALUES (:c, :a, :b, :at)"),
                  {"c": cid, "a": rng.choice([assignee, sup]), "b": rng.choice([
                      "Customer verified through the registered mobile number. Chargeback requested.",
                      "Escalated to cards operations; waiting on the processor's response.",
                      "VIP customer. Call back before end of day.",
                      "Pattern matches the WhatsApp impersonation scam; added to the fraud watchlist."]), "at": opened + timedelta(minutes=30)})
        event("note", assignee, opened + timedelta(minutes=30))
    # SLA misses: a first reply later than the 15-minute policy (or none yet on an old open case), a slow resolution
    waited = ((first_resp or NOW) - opened).total_seconds()
    if waited > 15 * 60:
        event("sla_breach", None, opened + timedelta(minutes=15), check="first_response")
    if closed_at and (closed_at - opened).total_seconds() > 24 * 3600:
        event("sla_breach", None, opened + timedelta(hours=24), check="resolution")
    if closed_at:
        event("closed", assignee, closed_at, closure_category="resolved")
        if rng.random() < 0.07:                      # the customer came back: reopened, then closed again
            back = min(closed_at + timedelta(hours=rng.randint(3, 40)), NOW)
            event("state_change", assignee, back, from_state="closed", to_state="open")
            event("closed", assignee, min(back + timedelta(hours=rng.randint(1, 8)), NOW), closure_category="resolved")


def _held_replies(sd: Seed, supervisor_id: int) -> None:
    """Put a handful of recent, assigned cases into ``pending_approval`` with the agent's reply held for
    a supervisor, the way a ``hold`` macro or a new agent's reply would be."""
    s, ws, rng = sd.s, sd.ws, sd.rng
    rows = s.execute(text("""
        SELECT c.id, c.channel, c.assignee_id, cu.display_name, cu.handle FROM "case" c JOIN customer cu ON cu.id = c.customer_id
        WHERE c.workspace_id = :ws AND c.state IN ('assigned', 'in_progress') AND c.assignee_id IS NOT NULL
        ORDER BY c.opened_at DESC LIMIT 3"""), {"ws": ws}).mappings().all()
    held = [
        "Hi {n}, we have traced your transfer and it will be reversed within 3 working days. Your reference is C-{c}. We apologise for the delay.",
        "Hello {n}, your card has been blocked and a replacement will arrive in 3 working days. We will never ask for your OTP or PIN.",
        "Dear {n}, we are sorry about the branch experience. Our regional head has been informed and will call you today.",
    ]
    for r in rows:
        first = r["display_name"].split()[0]
        who = next((u for u, uid in sd.users.items() if uid == r["assignee_id"]), "agent")
        s.execute(text("UPDATE \"case\" SET state = 'pending_approval' WHERE id = :c"), {"c": r["id"]})
        s.execute(text("""INSERT INTO outbound_action (workspace_id, platform, action, target_ref, request, actor, state, created_at)
                          VALUES (:ws, 'meta', 'reply_public', :t, CAST(:rq AS jsonb), :a, 'pending', :at)"""),
                  {"ws": ws, "t": f"demo_{r['id']}", "a": who, "at": NOW - timedelta(minutes=rng.randint(8, 240)),
                   "rq": json.dumps({"text": rng.choice(held).format(n=first, c=r["id"] + 1000), "case_id": r["id"]})})
    sd.bump("held_replies", len(rows))

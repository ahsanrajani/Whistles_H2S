"""Care operations: CSAT/NPS, knowledge base, macros and auto-rules, routing
policy and agent shift activity."""
import json
import secrets
from datetime import timedelta

from sqlalchemy import text

from core import surveys
from db.repositories import agent_activity

from .base import NOW, Seed, dt

KB = [
 ("Report a lost or stolen card", "Block the card immediately in the app (Cards > Block) or call the 24/7 helpline printed on the back of your card. A replacement is issued within 3 working days. Never share your PIN or OTP with anyone, including people claiming to be from the bank.", "cards,fraud"),
 ("A transaction was debited but not credited", "For InstaPay, interbank transfer and bill payments the amount is reversed automatically within 5 working days. If it has not been reversed, raise a dispute with the transaction reference and a screenshot. Typical resolution is 3-5 working days.", "payments,disputes"),
 ("Cannot log in to the mobile app", "Check you are on the latest app version, then use Forgot Password. If the OTP does not arrive, confirm your registered mobile number at a branch. Do not install the app from links sent over WhatsApp or SMS.", "app,login"),
 ("How to spot a fake Lumora Bank account", "We never ask for OTP, PIN or card details, never ask you to move to WhatsApp or Telegram, and never announce prizes in comments. Our verified account has the blue tick. Report impersonators to the helpline.", "fraud,social"),
 ("Savings account profit rate and payout dates", "Profit is calculated on daily balance and paid monthly. Current rates are published on the website and are subject to change. Rates are not guaranteed.", "deposits,rates"),
 ("Dispute a card transaction", "Submit the dispute within 60 days of the statement date. Provisional credit is given for unauthorized transactions after verification. Keep your card blocked until the investigation closes.", "cards,disputes"),
 ("Home remittance: how long does it take", "Remittances through Lumora Bank usually reach the beneficiary account within minutes. If it is pending beyond one working day, share the reference number with us.", "remittance"),
 ("Opening an account digitally", "You need your national ID, a selfie and a mobile number. Most accounts are approved within one working day. A branch visit is not required for basic accounts.", "onboarding,app"),
 ("ATM swallowed my card", "Visit the nearest Lumora branch with your national ID within 3 working days. Cards retained by non-Lumora ATMs must be claimed from the ATM's own bank.", "atm,cards"),
 ("Complaint escalation and timelines", "We acknowledge every complaint within 24 hours and aim to resolve within 10 working days. If unresolved, you may approach the Banking Ombudsman.", "complaints,regulatory"),
 ("Islamic banking: how profit sharing works", "Islamic savings accounts run on a Mudarabah basis certified by our Shariah board. Weightages are published monthly.", "islamic"),
 ("InstaPay: limits and QR payments", "InstaPay person-to-person and person-to-merchant limits are shown in the app under Limits. Merchants can accept QR payments from any participating bank.", "payments,instapay"),
 ("Phishing SMS: what to do", "Do not click links. Forward the SMS to our fraud desk and delete it. If you entered details, block your cards and change your password immediately, then call the helpline.", "fraud,phishing"),
 ("Branch timings and Ramadan hours", "Standard hours are 9am to 5pm Monday to Friday and 9am to 1pm Saturday. Ramadan hours are announced on our pages and in the app.", "branch"),
]
MACROS = [
 ("Acknowledge and ask for details", "acknowledge", "ack", True, "Hi {{customer.first_name}}, thank you for reaching out. We are sorry for the trouble. Please send us the transaction date, amount and reference number by direct message and we will look into it right away.", [{"type": "set_status", "status": "in_progress"}]),
 ("Fraud: secure the account", "fraud", "fraud", True, "Hi {{customer.first_name}}, your security matters most. Please block your card from the app now. We will never ask for your OTP, PIN or card number. Our fraud desk will call you from our official helpline.", [{"type": "set_priority", "priority": "urgent"}, {"type": "add_tags", "tags": ["fraud"]}]),
 ("InstaPay / transfer delay", "payments", "instapay", True, "Hi {{customer.first_name}}, we can see your transfer is in progress. Instant payments are reversed automatically within 5 working days if they fail. We will update you here.", [{"type": "add_tags", "tags": ["payments"]}]),
 ("Card dispute process", "cards", "dispute", False, "Hi {{customer.first_name}}, we have started a dispute on your card transaction. A provisional credit may apply after verification. Your reference is C-{{case.id}}.", [{"type": "add_tags", "tags": ["dispute"]}]),
 ("App login help", "app", "login", False, "Hi {{customer.first_name}}, please update to the latest app version and use Forgot Password. If the OTP still does not arrive, visit any branch to confirm your registered number.", []),
 ("Escalate to specialist", "escalation", "escalate", False, "Hi {{customer.first_name}}, we have escalated your case to a specialist team and will update you within one working day.", [{"type": "set_status", "status": "pending_approval"}, {"type": "add_note", "body": "Escalated to specialist team."}]),
 ("Resolved: closing note", "closing", "resolved", True, "Hi {{customer.first_name}}, this is now resolved. Thank you for your patience. If anything else comes up, message us any time.", [{"type": "set_status", "status": "closed", "closure_category": "resolved"}]),
 ("Branch complaint received", "branch", "branch", False, "Hi {{customer.first_name}}, we are sorry about your branch experience. We have shared your feedback with the branch manager and regional head.", [{"type": "add_tags", "tags": ["branch"]}]),
]
RULES = [
 ("Auto-acknowledge new cases", 0, [{"type": "new_case"}], {}, "hold"),
 ("Nudge after 30 minutes of silence", 0, [{"type": "no_response", "minutes": 30}], {}, "hold"),
 ("Fraud keywords: raise to urgent", 1, [{"type": "keyword", "words": ["fraud", "scam", "phishing", "unauthorized", "hacked"]}], {}, "none"),
]


def knowledge(sd: Seed) -> None:
    for title, body, tags in KB:
        sd.s.execute(text("""INSERT INTO kb_article (workspace_id, title, body, tags, published, created_by)
                             VALUES (:ws, :t, :b, :g, true, :u)"""),
                     {"ws": sd.ws, "t": title, "b": body, "g": tags, "u": sd.users["farah.supervisor"]})
    sd.bump("kb_article", len(KB))


def macros(sd: Seed) -> None:
    s, ws, ids = sd.s, sd.ws, []
    for order, (name, cat, shortcut, quick, body, actions) in enumerate(MACROS):
        ids.append(s.execute(text("""
            INSERT INTO care_template (workspace_id, name, category, body, shortcut, description, is_quick, quick_order, actions, active, created_by)
            VALUES (:ws, :n, :c, :b, :sc, :d, :q, :o, CAST(:a AS jsonb), true, :u) RETURNING id"""),
            {"ws": ws, "n": name, "c": cat, "b": body, "sc": shortcut, "d": f"Demo macro: {name}", "q": quick,
             "o": order if quick else 0, "a": json.dumps(actions), "u": sd.users["farah.supervisor"]}).scalar_one())
    for name, macro_idx, triggers, filters, mode in RULES:
        s.execute(text("""INSERT INTO care_macro_rule (workspace_id, macro_id, name, active, triggers, filters, reply_mode, created_by, last_fired_at)
                          VALUES (:ws, :m, :n, true, CAST(:t AS jsonb), CAST(:f AS jsonb), :rm, :u, :lf)"""),
                  {"ws": ws, "m": ids[macro_idx], "n": name, "t": json.dumps(triggers), "f": json.dumps(filters), "rm": mode,
                   "u": sd.users["farah.supervisor"], "lf": NOW - timedelta(hours=3)})
    # Auto-assignment stays on (least busy) but only touches cases newer than these, so the seeded queue keeps its
    # waiting cases instead of being drained the moment the scheduler first runs.
    s.execute(text("""INSERT INTO routing_policy (workspace_id, first_response_sla, resolution_sla, escalation_after, default_capacity,
                                                  assign_strategy, auto_assign_after_case)
                      VALUES (:ws, 900, 86400, 3600, 6, 'least_busy', (SELECT COALESCE(MAX(id), 0) FROM "case" WHERE workspace_id = :ws))
                      ON CONFLICT (workspace_id) DO UPDATE SET first_response_sla = 900, resolution_sla = 86400,
                        escalation_after = 3600, default_capacity = 6, assign_strategy = 'least_busy',
                        auto_assign_after_case = (SELECT COALESCE(MAX(id), 0) FROM "case" WHERE workspace_id = :ws)"""), {"ws": ws})
    sd.bump("macros", len(MACROS))


def csat(sd: Seed, closed: list[dict]) -> None:
    rng, s, ws = sd.rng, sd.s, sd.ws
    csat_id = surveys.ensure_default(s, ws)
    nps_id = s.execute(text("""INSERT INTO survey (workspace_id, name, kind, scale_min, scale_max, question)
                               VALUES (:ws, 'Relationship NPS', 'nps', 0, 10, 'How likely are you to recommend Lumora Bank?') RETURNING id"""),
                       {"ws": ws}).scalar_one()
    low = ["Took too long and I had to repeat myself.", "Issue still not fully fixed.", "Agent was polite but the process is slow."]
    high = ["Quick and clear, thank you.", "Resolved on the first reply.", "Very helpful agent.", ""]
    for c in closed:
        if rng.random() > 0.62:
            continue
        issued = c["closed_at"] + timedelta(minutes=5)
        answered = rng.random() < 0.78
        score = rng.choices([1, 2, 3, 4, 5], [0.06, 0.08, 0.14, 0.32, 0.4])[0] if answered else None
        s.execute(text("""INSERT INTO survey_response (workspace_id, survey_id, case_id, customer_id, channel, token, score, comment, bucket, issued_at, responded_at)
                          VALUES (:ws, :sv, :c, :cu, :ch, :tok, :sc, :cm, :bk, :iss, :resp)"""),
                  {"ws": ws, "sv": csat_id, "c": c["id"], "cu": c["customer_id"], "ch": c["channel"], "tok": secrets.token_urlsafe(18),
                   "sc": score, "cm": (rng.choice(low if score <= 2 else high) if answered else None),
                   "bk": surveys.bucket_for("csat", score, 1, 5) if answered else None, "iss": issued,
                   "resp": issued + timedelta(hours=rng.randint(1, 30)) if answered else None})
    for _ in range(40):
        score = rng.choices(range(0, 11), [1, 1, 1, 2, 2, 3, 4, 8, 12, 14, 12])[0]
        issued = dt(rng.uniform(0, 55), rng.randint(9, 20))
        s.execute(text("""INSERT INTO survey_response (workspace_id, survey_id, channel, token, score, bucket, issued_at, responded_at)
                          VALUES (:ws, :sv, 'in_app', :tok, :sc, :bk, :iss, :resp)"""),
                  {"ws": ws, "sv": nps_id, "tok": secrets.token_urlsafe(18), "sc": score,
                   "bk": surveys.bucket_for("nps", score, 0, 10), "iss": issued, "resp": issued + timedelta(hours=2)})
    sd.bump("survey_response", 40 + len(closed))


def shifts(sd: Seed, days: int = 21) -> None:
    """Login, ready/not-ready/idle transitions and logout per care agent per working day."""
    rng, s, ws = sd.rng, sd.s, sd.ws
    from .care import CARE_ROLES, STAFF
    for username, role in STAFF:
        if role not in CARE_ROLES:
            continue
        uid = sd.users[username]
        for d in range(1, days):
            if dt(d).weekday() >= 5:
                continue
            t = rng.randint(8, 9)
            for kind, offset_h in (("login", 0), ("ready", 0.05), ("not_ready", 2.6), ("ready", 3.1), ("idle", 4.6),
                                   ("ready", 4.9), ("not_ready", 6.3), ("ready", 6.6), ("logout", 9)):
                at = dt(d, t) + timedelta(hours=offset_h + rng.uniform(-0.1, 0.1))
                agent_activity.record(s, workspace_id=ws, user_id=uid, kind=kind, at=at)
        # today: signed in a few hours ago and still working (one agent on a break, one already off)
        start = NOW - timedelta(hours=rng.uniform(2.5, 4.5))
        events = [("login", 0), ("ready", 0.05), ("not_ready", 1.6), ("ready", 1.9)]
        if username == "omar.agent":
            events = [("login", 0), ("ready", 0.05), ("not_ready", 1.4)]
        elif username == "imran.senior":
            events += [("logout", 2.2)]
        for kind, offset_h in events:
            at = start + timedelta(hours=offset_h)
            if at <= NOW:
                agent_activity.record(s, workspace_id=ws, user_id=uid, kind=kind, at=at)
    sd.bump("agent_activity", 1)

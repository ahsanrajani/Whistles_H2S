"""Engineered risk signals: severe complaints (triage), churn intent, fraud
reports, incident spikes and regulator notices. Each is written so the
deterministic scanners score it for a reason a reader can trace to a rule."""
from . import corpus as C
from .base import Seed, stamp

# (days ago, regulator, title, body, names_focus_bank)
NOTICES = [
 (3, "NBA", "NBA approves Lumora Bank to onboard merchants on the InstaPay QR network",
  "The National Banking Authority has approved Lumora Bank's application to onboard small merchants on the InstaPay QR network, alongside four other banks."),
 (9, "NBA", "NBA imposes monetary penalty on Vantora Bank for AML/CFT lapses",
  "A fine has been imposed on Vantora Bank following an inspection that found violations of AML and customer due diligence rules."),
 (6, "NBA", "NBA issues framework on digital fraud prevention and customer authentication",
  "Banks must strengthen cyber and information security controls, adopt stronger authentication for instant payment and report phishing and social engineering fraud."),
 (14, "Banking Ombudsman", "Banking Ombudsman annual report highlights rise in card and digital banking complaints",
  "The ombudsman reports growth in consumer complaints on card disputes, unauthorized transactions and slow refund and redress."),
 (11, "NBA", "NBA expands InstaPay instant payment limits for person-to-merchant QR payments",
  "Instant payment system limits have been raised and merchants may now accept QR payments across all participating banks."),
 (20, "NBA", "NBA monetary policy committee holds policy rate; KIBOR steady",
  "The monetary policy committee kept the policy rate unchanged citing inflation outlook and stable exchange rate."),
 (17, "CMC", "CMC issues circular on disclosures for bank-sold investment and takaful products",
  "Banks distributing mutual funds and takaful must give clear risk disclosure and avoid guaranteed return claims."),
 (24, "NBA", "NBA revises incentive scheme for home remittance through formal channels",
  "Remittance incentive revised for banks and exchange companies; Overseas Digital Account flows to be tracked monthly."),
 (31, "Banking Ombudsman", "Banking Ombudsman directs banks to resolve complaints on blocked accounts within 10 days",
  "Consumer protection directive on grievance redress and fair treatment, including refund timelines for unauthorized debits."),
]


def complaints(sd: Seed) -> None:
    rng = sd.rng
    for i, tpl in enumerate(C.CRITICAL[:1]):
        sd.item(source=rng.choice(["x_recent", "dataforseo_serp", "youtube_v3"]), body=_fmt(rng, tpl), when=stamp(rng.uniform(0.3, 25), rng.randint(8, 22)),
                brands=[C.FOCUS], kind="mention", author=sd.handle(), outlet="x.com", sentiment="neg",
                category="fraud" if "unauthorized" in tpl.lower() or "fraudulent" in tpl.lower() else "complaint", label="risk:critical")
    for tpl in C.HIGH[:1]:
        sd.item(source=rng.choice(["x_recent", "dataforseo_serp"]), body=_fmt(rng, tpl), when=stamp(rng.uniform(0.2, 30), rng.randint(8, 22)),
                brands=[C.FOCUS], kind="mention", author=sd.handle(), outlet="x.com", sentiment="neg", category="complaint", label="risk:high")
    # a few severe complaints about rivals so the competitor view has contrast
    for brand in ("Vantora Bank", "Kestrel Trust Bank"):
        for tpl in C.HIGH[:1]:
            sd.item(source="x_recent", body=_fmt(rng, tpl, brand), when=stamp(rng.uniform(0.2, 30), rng.randint(8, 22)), brands=[brand],
                    kind="mention", author=sd.handle(), outlet="x.com", sentiment="neg", category="complaint", label="risk:rival")


def churn(sd: Seed) -> None:
    rng = sd.rng
    for tpl in C.SWITCH[:2]:
        rival = rng.choice(C.COMPETITORS)
        body = tpl.format(b=C.FOCUS, c=rival)
        sd.item(source=rng.choice(["x_recent", "dataforseo_serp", "youtube_v3"]), body=body, when=stamp(rng.uniform(0.2, 40), rng.randint(8, 22)),
                brands=[C.FOCUS, rival], kind="mention", author=sd.handle(), outlet="x.com", sentiment="neg", category="complaint", label="risk:churn")


def fraud_reports(sd: Seed) -> None:
    rng = sd.rng
    for brand in C.BRANDS:
        for _ in range(2 if brand == C.FOCUS else 1):
            sd.item(source=rng.choice(["x_recent", "dataforseo_serp", "googlenews_rss"]), body=_fmt(rng, rng.choice(C.FRAUD), brand),
                    when=stamp(rng.uniform(0.2, 45), rng.randint(8, 22)), brands=[brand], kind="mention",
                    author=sd.handle(), outlet="x.com", sentiment="neg", category="fraud", label="risk:fraud")


def incidents(sd: Seed) -> None:
    """Mention-velocity spikes with incident words: the focus brand's app outage and a rival's breach."""
    rng = sd.rng
    # large enough, with enough incident words, to clear the focus brand's own busy baseline (z >= 2.5 and >= 30% keywords)
    for day, count in ((2, 14), (1, 11)):
        for k in range(count):
            body = C.INCIDENT_FOCUS[k % len(C.INCIDENT_FOCUS)].format(b=C.FOCUS) if k % 6 else "just a normal comment about the bank"
            sd.item(source="x_recent", body=body, when=stamp(day, rng.randint(8, 22), rng.randint(0, 59)), brands=[C.FOCUS],
                    kind="mention", author=sd.handle(), outlet="x.com", sentiment="neg" if k % 6 else "neu",
                    category="complaint" if k % 6 else "other", label="risk:incident")
    for k in range(1):
        sd.item(source="x_recent", body=C.INCIDENT_RIVAL[k % 2].format(b="Vantora Bank"), when=stamp(4, rng.randint(8, 22), rng.randint(0, 59)),
                brands=["Vantora Bank"], kind="mention", author=sd.handle(), outlet="x.com", sentiment="neg", category="fraud", label="risk:incident")
    sd.item(source="googlenews_rss", body="Vantora Bank confirms security incident, customers advised to reset passwords", title="Vantora Bank confirms security incident",
            when=stamp(4, 10), brands=["Vantora Bank"], kind="post", outlet="Daily Ledger", sentiment="neg", category="news", label="risk:incident")


def regulatory(sd: Seed) -> None:
    for days, regulator, title, body in NOTICES:
        sd.item(source="regulatory_watch", body=body + " (demo notice)", title=title, when=stamp(days, 11),
                brands=[], kind="notice", outlet=f"{regulator} (demo)",
                raw={"regulator": regulator}, category="news", label="regulatory")


def _fmt(rng, tpl, brand=C.FOCUS):
    return tpl.format(b=brand, n=rng.randint(2, 6), amt=f"Rs {rng.choice([28000, 65000, 120000, 240000]):,}")


# (text, reason) -- items that name the brand but are about something else; the matcher rejects them and says why
_NAMESAKES = [
    ("{b} Cafe opens a second outlet on the lakeside with a new brunch menu", "no banking context (gated name rule)"),
    ("Annual sale at {b} Pharmacy: 30% off vitamins this week", "no banking context (gated name rule)"),
    ("{b} Industries announces a new textile plant and 400 jobs", "different company with the same name"),
    ("The {b} cricket club wins the regional league final", "different organisation with the same name"),
    ("{b} Travels launches summer tour packages to the northern valleys", "no banking context (gated name rule)"),
    ("Review: {b} Fitness gym is clean but the membership is pricey", "no banking context (gated name rule)"),
]


def boundary_rejections(sd: Seed) -> None:
    rng = sd.rng
    for brand in C.BRANDS:
        for tpl, reason in rng.sample(_NAMESAKES, k=3 if brand == C.FOCUS else 2):
            name = brand.replace(" Bank", "").replace(" Digital", "").replace(" Trust", "")
            sd.item(source=rng.choice(["x_recent", "dataforseo_serp", "googlenews_rss"]), body=tpl.format(b=name),
                    when=stamp(rng.uniform(0.2, 60), rng.randint(8, 22)), brands=[brand], kind="mention", author=sd.handle(),
                    outlet="x.com", excluded_reason=reason, label="rejected")


def gold_labels(sd: Seed) -> None:
    """A human-labelled sample of matches (for the precision report and the calibration queue):
    most correct, fewer among the ones the matcher flagged for review."""
    from sqlalchemy import text
    rng = sd.rng
    rows = sd.s.execute(text("SELECT id, needs_review FROM mention WHERE workspace_id = :ws AND excluded = 0 AND rule = 'demo'"),
                        {"ws": sd.ws}).all()
    n = 0
    for mid, review in rows:
        if review or rng.random() < 0.3:
            if review and rng.random() < 0.6:
                continue                              # leave most review-flagged ones in the queue
            sd.s.execute(text("""INSERT INTO gold_label (mention_id, workspace_id, correct, labelled_at, labelled_by)
                                 VALUES (:m, :ws, :c, :at, 'farah.supervisor')"""),
                         {"m": mid, "ws": sd.ws, "c": 1 if rng.random() < (0.68 if review else 0.95) else 0,
                          "at": stamp(rng.uniform(0, 20), 15)})
            n += 1
    sd.bump("gold_label", n)

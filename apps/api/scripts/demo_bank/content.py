"""The content calendar: posts in every workflow state with a real approval
trail (writer, reviewer, notes), signal origins for the closed loop, and a few
drafts that the compliance check should catch."""
from datetime import timedelta

from sqlalchemy import text

from core import content_calendar as cc

from .base import NOW, Seed

# (title, body, state, days from now [+ future / - past], origin signal or None, who writes)
ITEMS = [
 ("Warn customers: fake support on WhatsApp",
  "Fake accounts are posing as our support team and asking customers to chat on WhatsApp. We never ask you to move a conversation "
  "to WhatsApp or share your OTP, PIN or card details. Use only our verified app, website and helpline.", "published", -12, ("scam:whatsapp", "scam")),
 ("Phishing awareness: never share your OTP",
  "Beware of phishing calls and SMS pretending to be Lumora Bank. We will never ask for your OTP or PIN. Hang up and call the number on the back of your card.",
  "published", -28, ("scam:impersonation", "scam")),
 ("Service update: app login restored",
  "Some customers had trouble logging in to the app earlier today. The issue is fixed and we are sorry for the inconvenience. If you still need help, use our verified helpline.",
  "published", -3, ("incident:today", "incident")),
 ("Savings profit rate revision explained",
  "Our savings profit rate has been revised. Here is how it is calculated and what it means for your balance. Profit rates are not guaranteed and subject to change. Terms apply.",
  "published", -20, None),
 ("Eid cashback on card payments",
  "Earn 5% cashback on Lumora credit card payments this Eid. Terms and conditions apply. Cashback is capped at Rs 2,000 per customer.", "scheduled", 2, None),
 ("InstaPay QR limits increased",
  "Good news for merchants: InstaPay QR payment limits have been raised. Accept payments from any bank through one QR code.", "scheduled", 5, None),
 ("Home finance webinar for first-time buyers",
  "Join our free webinar on home finance: documents, down payment and monthly instalments explained in plain language. Seats are limited.", "approved", 7, None),
 ("New Faisalabad branch opening", "We are opening a new branch on Textile Square, Faisalabad. Visit us for account opening, cards and locker service.", "in_review", 4, None),
 ("Weekend investment push",
  "Guaranteed returns of 30% per month, risk-free! Invest today, limited time only. WhatsApp us on 0300 1234567.", "in_review", 6, None),
 ("Fake WhatsApp support warning (suggested from live signals)",
  "Fake accounts are posing as our support team and asking customers to chat on WhatsApp. We never ask you to move a conversation to WhatsApp or share your OTP, PIN or card details.",
  "draft", None, ("scam:whatsapp", "scam")),
 ("Ramadan branch timings", "Our branches will open from 9am to 2pm during Ramadan. Digital banking is available 24/7.", "draft", 9, None),
 ("Win an Umrah package: like, share and inbox us!",
  "Congratulations! You could win an Umrah package. Like, share and inbox me your account number to claim your prize.", "rejected", 8, None),
]


def calendar(sd: Seed) -> None:
    s, ws = sd.s, sd.ws
    writers = [sd.users[k] for k in ("hira.agent", "bilal.agent", "sana.agent")]
    approver = sd.users["farah.supervisor"]
    for i, (title, body, state, days, origin) in enumerate(ITEMS):
        writer = writers[i % len(writers)]
        slot = None if days is None else NOW + timedelta(days=days)
        cid = cc.create(s, ws, writer, title=title, body=body, channel=["facebook", "instagram", "x", "linkedin"][i % 4],
                        scheduled_for=slot if state != "published" else None)
        if origin:
            cc.record_origin(s, cid, writer, {"signal": origin[0], "signal_kind": origin[1]})
        if state in ("in_review", "approved", "scheduled", "published", "rejected"):
            cc.transition(s, ws, cid, "submit", writer, at=None)
        if state in ("approved", "scheduled", "published"):
            cc.transition(s, ws, cid, "approve", approver, note="Compliance clear")
        if state in ("scheduled", "published"):
            cc.transition(s, ws, cid, "schedule", approver, at=slot or NOW)
        if state == "published":
            cc.transition(s, ws, cid, "publish", approver, at=NOW + timedelta(days=days))
            s.execute(text("UPDATE content_item SET scheduled_for = :t WHERE id = :i"), {"t": NOW + timedelta(days=days), "i": cid})
        if state == "rejected":
            cc.transition(s, ws, cid, "reject", approver, note="Prize lure and request for account number: breaks our fraud-awareness rules")
    sd.bump("content_item", len(ITEMS))

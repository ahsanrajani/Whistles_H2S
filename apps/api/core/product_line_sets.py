"""Product-line keyword sets per vertical (see core/vertical.py). Each entry is
(key, label, [keywords]); a trailing "*" drops the closing word boundary."""

BANKING = [
    ("cards", "Cards", [
        "credit card", "debit card", "visa", "mastercard", "card limit",
        "card declined", "card blocked", "annual fee", "reward point*",
        "instalment plan", "installment plan", "supplementary card"]),
    ("auto", "Auto finance", [
        "car loan", "car financ*", "auto loan", "auto financ*",
        "vehicle financ*", "bike financ*"]),
    ("islamic", "Islamic banking", [
        "islamic", "shariah", "sharia", "riba", "halal bank*", "takaful",
        "musharak*", "ijarah", "mudarab*", "islamic banking"]),
    ("remittance", "Remittances", [
        "remittanc*", "remit", "send money home", "home remittance",
        "western union", "roshan digital", "rda", "overseas account",
        "foreign remittance"]),
    ("app", "Digital & app", [
        "banking app", "mobile app", "mobile banking", "internet banking",
        "digital banking", "app crash*", "app update", "app not working",
        "otp", "e-statement", "estatement", "online banking"]),
    ("deposits", "Accounts & deposits", [
        "savings account", "current account", "term deposit", "profit rate",
        "account opening", "minimum balance", "monthly profit"]),
    ("payments", "Payments & transfers", [
        "ibft", "raast", "fund transfer", "bill payment", "1link",
        "online transfer", "qr code", "qr payment", "interbank transfer"]),
    ("loans", "Personal & SME loans", [
        "personal loan", "running finance", "working capital", "sme loan",
        "sme financ*", "business loan", "salary loan"]),
    ("branch", "Branch & ATM", [
        "branch", "atm", "cash deposit machine", "cash withdrawal", "cdm",
        "teller", "counter staff"]),
]

INSURANCE = [
    ("claims", "Claims & settlement", [
        "claim*", "death claim",
        "hospitalisation", "hospitalization", "reimbursement", "claim form"]),
    ("surrender", "Surrender & lapse", [
        "surrender", "surrender value", "lapse*", "policy lapsed", "cancel*",
        "cancellation", "free look", "refund", "premium refund", "paid up"]),
    ("maturity", "Maturity & payouts", [
        "maturity", "matured", "maturity payment", "payout", "pay out",
        "maturity amount", "policy matured"]),
    ("bancassurance", "Bancassurance & mis-selling", [
        "bancassurance", "banca", "mis-sold", "missold", "mis sold", "misled", "mis-sell*",
        "missell*", "sold to me as", "told it was", "fixed deposit",
        "bank employee", "bank staff", "without my consent"]),
    ("takaful", "Family takaful", [
        "takaful", "family takaful", "shariah", "sharia", "islamic",
        "wakala", "contribution", "riba", "halal"]),
    ("savings", "Savings & investment plans", [
        "investment plan", "savings plan", "endowment", "unit linked",
        "unit-linked", "fund value", "bonus",
        "education plan", "child plan", "retirement plan", "pension"]),
    ("health", "Health & protection", [
        "health insurance", "medical", "hospital", "opd", "life cover",
        "term life", "term plan", "sum assured", "accidental", "critical illness"]),
    ("service", "Service & agents", [
        "agent", "advisor", "adviser", "customer service", "call centre",
        "call center", "helpline", "no response", "not responding",
        "follow up"]),
    ("premium", "Premium & billing", [
        "premium", "premium payment", "installment", "instalment",
        "auto debit", "deducted", "increased premium", "policy number",
        "policy document"]),
    ("app", "Digital & app", [
        "jubilee active", "mobile app", "app not working", "app crash*",
        "login", "otp", "portal", "online payment", "website", "e-policy"]),
]

SETS = {"banking": BANKING, "insurance": INSURANCE}

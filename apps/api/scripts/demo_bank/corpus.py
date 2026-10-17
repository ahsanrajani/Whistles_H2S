"""Static text and reference data for the fictional Lumora Bank demo corpus.

Everything here is invented. Brand names are fictional, people are generic, and
nothing is scraped. ``{b}`` is the brand the item is about, ``{c}`` a rival,
``{n}`` a small random number, ``{amt}`` a rupee amount.
"""

NAME = "Lumora Bank"
SLUG_HINT = "lumora-bank"
FOCUS = "Lumora Bank"
# name -> (share of mentions, positive, neutral share; the rest is negative)
BRANDS = {
    "Lumora Bank": (0.36, 0.34, 0.25),          # the focus: strong digital, weak branches/cards
    "Vantora Bank": (0.22, 0.30, 0.27),          # hit by a breach story
    "Kestrel Trust Bank": (0.17, 0.36, 0.30),
    "Solenne Bank": (0.14, 0.44, 0.28),           # profit-rate leader
    "Nimbus Digital Bank": (0.11, 0.40, 0.22),    # digital challenger
}
COMPETITORS = [b for b in BRANDS if b != FOCUS]

# topic -> weight of conversation, per brand (focus overrides below)
TOPIC_WEIGHT = {"cards": 15, "app": 22, "deposits": 11, "payments": 14, "loans": 8,
                "islamic": 5, "remittance": 6, "branch": 14, "service": 5}
FOCUS_TOPIC_BIAS = {"cards": 1.35, "branch": 1.45, "app": 0.9, "payments": 1.0}
# topic -> probability that a post on it is negative, for the focus brand
FOCUS_NEG = {"cards": 0.36, "branch": 0.40, "app": 0.16, "payments": 0.12, "deposits": 0.18,
             "loans": 0.24, "islamic": 0.10, "remittance": 0.16, "service": 0.32}

# (topic, tone) -> templates. tone: neg / pos / neu
T = {
 ("cards", "neg"): [
  "{b} credit card annual fee charged again after I asked to cancel it. {n}rd call, no resolution.",
  "My {b} debit card was declined at the store even though the balance was fine. Card blocked and no SMS.",
  "{b} reduced my credit card limit without any notice and the reward points expired too.",
  "Disputed a card transaction with {b} {n} weeks ago, still no chargeback. Card statement shows it again.",
  "{b} supplementary card never arrived, and card blocked on the primary after I followed up.",
 ],
 ("cards", "pos"): [
  "Got my {b} credit card approved in two days and the reward points actually add up.",
  "{b} contactless debit card works everywhere, no declines so far. Good card experience.",
  "Switched my instalment plan to {b} credit card at 0% for {n} months. Smooth process.",
 ],
 ("cards", "neu"): [
  "Does {b} charge an annual fee on the platinum credit card in the first year?",
  "How do I increase my {b} card limit? Any minimum salary requirement?",
 ],
 ("app", "neg"): [
  "{b} mobile app freezes every time I open the fund transfer screen. The update made it worse.",
  "Unable to sign in to {b} mobile banking since the update, the OTP never arrives. The app has been unusable for {n} days.",
  "{b} app keeps logging me out mid-transaction. Internet banking is no better.",
  "Why does the {b} app need a full re-registration after every update? The app is slow again today.",
 ],
 ("app", "pos"): [
  "The new {b} app update is clean and fast, e-statement download takes seconds.",
  "{b} digital banking is the best I have used, account opening took ten minutes from my phone.",
  "Love the spending insights in the {b} mobile app. Online banking done right.",
 ],
 ("app", "neu"): [
  "Is the {b} app available for Huawei phones? Looking for mobile banking options.",
  "Feature request for {b}: please add biometric login and dark mode to the mobile app.",
 ],
 ("deposits", "neg"): [
  "{b} cut the profit rate on savings accounts again while rivals went up. Time to look around.",
  "Minimum balance charges at {b} took {amt} from my current account without a warning message.",
  "{b} account opening requires a visit even for existing customers. Outdated process.",
 ],
 ("deposits", "pos"): [
  "{b} monthly profit on the savings account landed on time and the rate is competitive.",
  "Opened a term deposit with {b}, the profit rate was better than I expected.",
 ],
 ("deposits", "neu"): ["What is the current {b} savings account profit rate for balances above 1 million?"],
 ("payments", "neg"): [
  "InstaPay transfer from {b} stuck for {n} days, amount deducted but not credited. Customer care just says wait.",
  "{b} interbank transfer limit is too low for business use, fund transfer fails above {amt}.",
  "Bill payment through {b} failed twice but money was deducted. Still waiting for the reversal.",
 ],
 ("payments", "pos"): [
  "interbank transfer through {b} app was instant today, bill payment and QR payments work smoothly.",
  "{b} InstaPay integration is excellent, instant payment to any bank in seconds.",
  "Paid my utility bills in one tap with {b}, no more queues.",
 ],
 ("payments", "neu"): ["Does {b} support unified bill payment bill payment for school fees?"],
 ("loans", "neg"): [
  "Applied for a {b} personal loan {n} weeks ago, still no update. Documents verified twice.",
  "{b} auto finance rate quoted on call was different from the offer letter. Misleading.",
  "{b} SME loan processing takes forever, working capital needed now not next quarter.",
 ],
 ("loans", "pos"): [
  "{b} auto finance approval was smooth, car loan installments are reasonable.",
  "Got a {b} salary loan in 48 hours with clear charges. Honest pricing.",
 ],
 ("loans", "neu"): ["What documents does {b} need for a home finance application as a salaried person?"],
 ("islamic", "neg"): ["{b} takaful charges were not explained properly when I opened the Islamic account."],
 ("islamic", "pos"): [
  "Switched to {b} Islamic banking, the musharakah home financing explanation was transparent.",
  "{b} Shariah board certification is published openly, that matters to me.",
 ],
 ("islamic", "neu"): ["Is the {b} Islamic savings account profit calculated on mudarabah?"],
 ("remittance", "neg"): [
  "My remittance through {b} has been pending for {n} days, the receiver is still waiting.",
  "{b} remittance exchange rate was worse than the open market by {n} rupees today.",
 ],
 ("remittance", "pos"): [
  "Home remittance via {b} arrived within minutes, better rate than the exchange company.",
  "Overseas Digital Account setup with {b} was surprisingly smooth from abroad.",
 ],
 ("remittance", "neu"): ["Does {b} charge a fee for foreign remittance credited to a savings account?"],
 ("branch", "neg"): [
  "Waited {n}0 minutes at the {b} branch, counter staff rude and the ATM cash deposit machine was out of order.",
  "{b} ATM ate my card in {city} and the branch says come back after three days.",
  "Long queue at the {b} {city} branch again and only one teller on duty. Cash withdrawal took an hour.",
  "{b} branch refused to update my national ID without a manager who is never there. Terrible branch service.",
 ],
 ("branch", "pos"): [
  "{b} branch staff in {city} were helpful in opening the account, no queue at all.",
  "Quick and polite counter service at {b} today, ATM was working too.",
 ],
 ("branch", "neu"): ["What are the {b} branch timings in {city} on Saturdays?"],
 ("service", "neg"): [
  "{b} customer care put me on hold for 40 minutes and then dropped the call. Worst customer service.",
  "Raised a complaint with {b} {n} days ago, ticket number given but zero response.",
 ],
 ("service", "pos"): ["{b} support resolved my issue on the first call, the agent was patient and clear."],
 ("service", "neu"): ["What is the {b} helpline number for lost card reporting?"],
}

# Roman Urdu / Urdu variants (lang_guess roman_urdu / ur)
ROMAN = {
 "neg": ["{b} ki app bohat slow hai, transfer kabhi nahi hota.",
         "{b} ka customer care koi jawab nahi deta, paisay kat gaye lekin credit nahi hue.",
         "{b} branch mein bohat lamba intezar, staff ka rawaiya bura."],
 "pos": ["{b} ki service achi hai, account khulwana asaan tha.",
         "{b} ka instapay transfer foran ho gaya, shukriya."],
 "neu": ["{b} ke savings account ka profit rate kitna hai?"],
}
URDU = {
 "neg": ["{b} کی ایپ بہت سست ہے اور ٹرانسفر نہیں ہوتا۔", "{b} کے اے ٹی ایم نے کارڈ رکھ لیا اور برانچ والے کچھ نہیں بتا رہے۔"],
 "pos": ["{b} کی ڈیجیٹل بینکنگ استعمال میں آسان ہے۔"],
 "neu": ["{b} کا سیونگ اکاؤنٹ منافع کتنا ہے؟"],
}

# Headlines for the news surface: (tone, text)
NEWS = [
 ("pos", "{b} reports {n}% rise in half-year profit on strong deposit growth"),
 ("pos", "{b} launches InstaPay-enabled merchant QR solution for small businesses"),
 ("pos", "{b} partners with a fintech to expand digital onboarding to 30 more cities"),
 ("pos", "{b} named best retail bank in regional industry awards"),
 ("neu", "{b} appoints new head of consumer banking"),
 ("neu", "{b} opens {n} new branches as part of its expansion plan"),
 ("neu", "{b} board approves interim dividend; results due next week"),
 ("neg", "{b} faces customer backlash over repeated mobile app outages"),
 ("neg", "Consumers complain about card fees as {b} revises its tariff"),
 ("neg", "{b} under scrutiny after rise in complaints to the banking ombudsman"),
]

# Fraud / scam-awareness items about a brand (category fraud)
FRAUD = [
 "Beware: fake {b} support accounts on WhatsApp are asking customers for their OTP and card number.",
 "Got a phishing SMS pretending to be {b} asking me to verify my account on a strange link. Reported it.",
 "Someone called pretending to be {b} fraud department and knew my name. Almost gave them the OTP.",
 "A {b} customer lost {amt} to a fake lucky draw call. Please warn your parents about these scams.",
]

# Branch reviews: (rating, text)
BRANCH_REVIEWS = {
 "bad": [
  (1, "Terrible. Waited over an hour in the queue, only one counter open and the staff rude."),
  (1, "ATM not working again and the branch manager never available. Cash not available either."),
  (2, "Very slow service, the token system is broken and the waiting area is chaos."),
  (1, "Staff misbehaved when I asked about a failed transaction. Will move my account."),
  (2, "Cash deposit machine out of order for weeks. Long queue every single day."),
  (2, "Rude staff and long waiting time. Needs a new branch manager."),
 ],
 "ok": [
  (4, "Decent branch, staff are helpful and the queue moves fast in the morning."),
  (3, "Average service. The ATM works but the waiting area is cramped."),
  (5, "Excellent counter staff, opened my account in 15 minutes."),
  (4, "Clean branch, friendly manager, quick locker service."),
  (5, "Very professional team, no queue and the ATM was stocked."),
  (3, "Okay experience, waited 20 minutes but the issue was resolved."),
 ],
}

# Engineered high-severity complaints (triage Critical / High)
CRITICAL = [
 "Unauthorized transaction of {amt} left my {b} account and the money was not reversed. I complained to the regulator and the federal ombudsman, "
 "now sending a legal notice. This is the third time I am following up since {n} weeks, no response.",
 "{b} froze my salary account and I am locked out with no money for school fee. Complaint number given, still not resolved. "
 "Going to post everything and tag the media if this is not fixed this week.",
 "Amount deducted but not credited, {amt} lost through a {b} fraudulent debit. I have filed a complaint to the regulator and will sue if "
 "there is no update, screenshots attached.",
]
HIGH = [
 "My {b} account blocked without notice and I can't withdraw or transfer. Ticket number given {n} days ago, no update.",
 "{b} card declined everywhere and money debited twice. Second time this month, nobody calls back.",
 "Salary account stuck at {b}, salary not credited for {n} days. Pension money needed for medicine.",
 "{b} charged me a fee I never agreed to and refuses a refund. I will escalate to the regulator if there is no reply.",
]
SWITCH = [
 "I have been a long-time customer of {b} for 8 years but I am done with this bank. Closing my account and moving my salary account to {c}.",
 "Had enough of {b}. Switching banks to {c} next week, the last straw was the card block. Do not open an account here.",
 "Wish I had opened with {c}. Better service at {c} than {b}. Fix this or I am closing my account and moving banks.",
 "Taking my money elsewhere. Transferring my salary to {c}, avoid this bank {b}, would not recommend to anyone.",
]
INCIDENT_FOCUS = [
 "{b} app crash and login outage again, transaction failed",
 "cannot login to {b} app, system down since morning",
 "{b} server down? money stuck and transfer failed",
 "{b} service unavailable, not working for hours",
]
INCIDENT_RIVAL = [
 "{b} data breach? customers reporting hacked accounts and phishing calls",
 "{b} suspended online services after a security incident, unauthorized transactions reported",
]
SCAM_COMMENTS = [
 "Contact our official support on WhatsApp 0300 1234567 to claim your refund",
 "You have won a lucky draw prize, inbox me to claim your reward points",
 "Quick support team here, message me privately with your account details",
 "Customer care number 0321 7654321, call now for refund department help",
 "Claim your cashback offer at bit.ly/claim-now or t.me/bank_support",
 "Official support: dm me your card number and OTP to unblock your account",
]
CLEAN_COMMENTS = [
 "Thanks for the update, the new feature works well.", "Can you share the profit rate for the new savings plan?",
 "Great service at the Canal View branch today.", "The app update fixed my login problem, thanks.",
 "Helpful staff, resolved my card issue quickly.", "When will the InstaPay limit increase?",
 "Appreciate the quick reply from your team.", "Is there a branch near Lakeside Phase 7?",
]
POSTS = [
 ("Profit rate update on our savings accounts", "deposits"), ("Update your mobile banking app for the new login screen", "app"),
 ("Beware of fake accounts and phishing calls, never share your OTP", "fraud"), ("Cashback campaign on card payments this Eid", "cards"),
 ("Debit card payments now work on InstaPay QR", "payments"), ("Home finance made simple: three steps to your keys", "loans"),
 ("Digital banking tips for senior customers", "app"), ("Our new branch is open in your city", "branch"),
 ("Remit home with better rates this month", "remittance"), ("Islamic banking explained: how profit sharing works", "islamic"),
]

# key facts for the branch catalogue: (city, name, kind, lat, lng, mean_rating, review_n)
LOCATIONS = [
 ("Karachi", "Head Office Founders Avenue", "office", 24.8486, 67.0110, 4.1, 30),
 ("Karachi", "Harbour Point Branch", "branch", 24.8138, 67.0300, 4.3, 24), ("Karachi", "Marina Court Branch", "branch", 24.8056, 67.0580, 4.5, 20),
 ("Karachi", "Garden Row Branch", "branch", 24.9215, 67.0924, 3.9, 18), ("Karachi", "Old Market Branch", "branch", 24.8546, 67.0299, 2.3, 26),
 ("Karachi", "Northgate Branch", "branch", 24.9420, 67.0400, 4.0, 14), ("Lahore", "Canal View Branch", "branch", 31.5204, 74.3587, 3.5, 28),
 ("Lahore", "Orchard Park Branch", "branch", 31.4697, 74.4036, 4.4, 18), ("Lahore", "Rosewood Branch", "branch", 31.4697, 74.2728, 4.0, 16),
 ("Lahore", "Clocktower Branch", "branch", 31.4826, 74.3239, 3.8, 15), ("Lahore", "Central Boulevard Branch", "branch", 31.5656, 74.3242, 3.7, 14),
 ("Islamabad", "Skyline Plaza Branch", "branch", 33.7077, 73.0561, 4.6, 22), ("Islamabad", "Pinecrest Market Branch", "branch", 33.7215, 73.0553, 4.4, 17),
 ("Islamabad", "Greenfield Sector Branch", "branch", 33.6677, 72.9981, 3.9, 12), ("Rawalpindi", "Cantonment Road Branch", "branch", 33.5973, 73.0479, 3.6, 13),
 ("Rawalpindi", "Lakeside Phase 7 Branch", "branch", 33.5200, 73.1100, 4.2, 14), ("Faisalabad", "Millers Colony Branch", "branch", 31.4181, 73.0897, 3.8, 12),
 ("Faisalabad", "Textile Square Branch", "branch", 31.4310, 73.0780, 4.1, 11), ("Multan", "Fort Road Branch", "branch", 30.1950, 71.4750, 3.7, 12),
 ("Multan", "Garden Town Branch", "branch", 30.2300, 71.4500, 4.0, 10), ("Peshawar", "Campus Road Branch", "branch", 34.0030, 71.4850, 3.2, 19),
 ("Peshawar", "Bazaar Road Branch", "branch", 34.0120, 71.5400, 3.9, 11), ("Quetta", "Alpine Road Branch", "branch", 30.1950, 67.0100, 3.8, 10),
 ("Karachi", "Harbour Point ATM Block 9", "atm", 24.8200, 67.0250, None, 0), ("Lahore", "Canal View ATM Main Boulevard", "atm", 31.5150, 74.3500, None, 0),
]
CITY_REGION = {"Karachi": "Sindh", "Lahore": "Punjab", "Islamabad": "ICT", "Rawalpindi": "Punjab",
               "Faisalabad": "Punjab", "Multan": "Punjab", "Peshawar": "KP", "Quetta": "Balochistan"}
CITIES = list(CITY_REGION)

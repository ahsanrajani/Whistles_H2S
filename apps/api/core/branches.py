"""Branch resolver: map a mention's text to one physical Bank Alfalah branch.

Deterministic and auditable — a small alias table per branch (name tokens, the
area/road it sits on, the city, the branch code), a fixed weight per signal,
and a confidence floor below which the mention stays *unresolved* rather than
guessed. Google Maps reviews carry their branch id in ``raw_json`` and skip the
resolver entirely; social mentions (Facebook, X, forums) go through it.

The catalogue here is the PoC subset — the ~14 branches we have real,
documented problems for. Extend ``BRANCHES`` from the full branch list when the
live Google Maps collector lands.
"""

# key, display name, branch code, city, [alias phrases]. An alias matches on
# word boundaries with any run of whitespace between its tokens.
BRANCHES = [
    ("bahria-ph7-rwp", "Bahria Town Phase 7, Rawalpindi", "0442", "Rawalpindi", [
        "bahria town phase 7", "bahria town phase vii", "bahria town ph7",
        "bahria phase 7", "phase 7 bahria", "bahria town phase 8",
        "bahria town rawalpindi", "bahria rawalpindi"]),
    ("ait-lahore", "Allama Iqbal Town, Lahore", "0042", "Lahore", [
        "allama iqbal town", "iqbal town lahore", "ait branch", "karim block",
        "college block allama iqbal"]),
    ("peoples-colony-fsd", "Peoples Colony / D-Ground, Faisalabad", "0054", "Faisalabad", [
        "peoples colony faisalabad", "d-ground faisalabad", "d ground faisalabad",
        "babar chowk faisalabad", "peoples colony branch"]),
    ("cavalry-ground-lhr", "Cavalry Ground, Lahore", "0157", "Lahore", [
        "cavalry ground", "cavalry ground lahore"]),
    ("sargodha", "Main Sargodha", "0043", "Sargodha", [
        "sargodha branch", "university road sargodha", "satellite town sargodha",
        "liaquat road sargodha", "main sargodha"]),
    ("haroonabad", "Haroonabad", "0125", "Bahawalnagar", [
        "haroonabad branch", "haroonabad", "grain market haroonabad",
        "quaid e azam road haroonabad"]),
    ("i8-markaz-isb", "I-8 Markaz, Islamabad", "0146", "Islamabad", [
        "i-8 markaz", "i 8 markaz", "i8 markaz", "sector i-8 islamabad",
        "i-8 islamabad"]),
    ("abbottabad-mansehra-rd", "Abbottabad, Mansehra Road", "0068", "Abbottabad", [
        "abbottabad mansehra road", "mansehra road abbottabad", "main mansehra road abbottabad",
        "kala pul mansehra road", "abbottabad branch", "supply bazar abbottabad"]),
    ("hyderi-khi", "Hyderi, Karachi", "0084", "Karachi", [
        "hyderi karachi", "hyderi branch", "hydri branch", "hydri karachi",
        "north nazimabad hyderi"]),
    ("johar-town-lhr", "Johar Town, Lahore", "0195", "Lahore", [
        "johar town lahore", "m a johar town", "ma johar town",
        "johar town branch", "r block johar town", "j block johar town"]),
    ("dha-ext-lhr", "Defence Extension, Lahore", "0220", "Lahore", [
        "defence extension lahore", "dha extension lahore", "dha extension branch",
        "bhatta chowk lahore", "new airport road lahore cantt"]),
    ("napier-road-khi", "Napier Road, Karachi", "0003", "Karachi", [
        "napier road", "napier quarters", "napier road karachi"]),
    ("f8-markaz-isb", "F-8 Markaz, Islamabad", "0148", "Islamabad", [
        "f-8 markaz", "f 8 markaz", "f8 markaz", "al-baber center f-8"]),
    ("bosan-road-mtn", "Bosan Road, Multan", "0198", "Multan", [
        "bosan road multan", "bosan road branch", "officers colony bosan road"]),
    ("paris-road-skt", "Paris Road, Sialkot", "0029", "Sialkot", [
        "paris road sialkot", "paris road branch", "main sialkot paris road"]),
    ("clifton-khi", "Clifton, Karachi", "0031", "Karachi", [
        "clifton karachi branch", "clifton block 9", "bc-6 clifton",
        "schon circle clifton"]),
    ("dha-ph5-lhr", "DHA Phase 5, Lahore", "0343", "Lahore", [
        "dha phase 5 lahore", "dha phase v lahore", "defence phase 5 lahore",
        "dha phase 5 branch", "phase 5 dha lahore"]),
    ("shadbagh-lhr", "Shad Bagh, Lahore", "0221", "Lahore", [
        "shad bagh lahore", "shadbagh lahore", "shad bagh branch", "shadbagh branch",
        "shad bagh road"]),
    ("qasimabad-hyd", "Qasimabad, Hyderabad", "0306", "Hyderabad", [
        "qasimabad hyderabad", "qasimabad branch", "phase 1 qasimabad",
        "main qasimabad road"]),
    ("tariq-road-khi", "Tariq Road, Karachi", "0089", "Karachi", [
        "tariq road karachi", "tariq road branch", "main tariq road",
        "124/a block 2 pechs tariq road"]),
]

from .branch_resolver import Resolver

DEFAULT = Resolver(BRANCHES)
catalog = DEFAULT.catalog
resolve_by_name = DEFAULT.resolve_by_name
resolve = DEFAULT.resolve

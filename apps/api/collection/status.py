"""Write the per-surface collection ledger (`surface_status`) after a run.
Called by `collector.run_collection`; re-exported as `collector.write_status`."""
from core import sources
from core.stats import estimable
from db import pipeline as p


def write_status(db, ws, run_id, used, keys=None):
    # The client ledger is an operational view. Experimental, unlicensed and
    # non-commercial adapters must never be presented as active coverage.
    keys = keys or {}
    s = db.session
    used = [a for a in used if a.meta.get("client_safe")]
    by_surface = {}
    for a in used:
        by_surface.setdefault(a.meta["surface"], []).append(a)

    for surface, ads in by_surface.items():
        n_ind = sum(1 for a in ads if a.meta["independent"])
        sampled = any(a.meta.get("sampled") for a in ads)
        p.upsert_surface_status(
            s, run_id=run_id, ws=ws, surface=surface,
            state="sampled" if sampled else "collected", n_sources=n_ind,
            estimable=1 if estimable(n_ind) else 0,
            note="; ".join(a.meta["label"] for a in ads))

    # Per-source scheduling (P2.7) means most runs only touch the sources
    # that are actually due -- a surface absent from `used` is usually just
    # "not due this tick", not broken. Only a surface with NO credentialled
    # source at all is really "failed"; everything else carries its last
    # known real status forward so the ledger doesn't flip to false
    # negatives every partial run.
    covered = set(by_surface)
    prior = p.latest_surface_status(s, ws)
    for sid, meta in sources.SOURCES.items():
        surface = meta["surface"]
        if not meta.get("client_safe") or surface in covered or surface == "—":
            continue
        if all(keys.get(k) for k in meta["needs"]):
            carry = prior.get(surface)
            if carry:
                p.upsert_surface_status(
                    s, run_id=run_id, ws=ws, surface=surface, state=carry["state"],
                    n_sources=carry["n_sources"], estimable=carry["estimable"],
                    note=carry["note"])
            # else: credentialled but never successfully collected yet --
            # leave it out of this run's ledger rather than call it "failed".
        else:
            p.upsert_surface_status(
                s, run_id=run_id, ws=ws, surface=surface, state="failed",
                n_sources=0, estimable=0,
                note="No credentials: " + ", ".join(meta["needs"]))
        covered.add(surface)

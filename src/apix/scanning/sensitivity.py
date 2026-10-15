"""
What an endpoint handles, inferred from its path, and how urgently it matters.

A forgotten endpoint that serves a product catalogue and one that checks an
OTP are not the same risk. A bank triages by what is exposed, so every
endpoint gets a data category read from its path segments and handler name,
and every finding is ranked by a priority that combines the category with the
evidence against the endpoint.

The category is a heuristic and is labelled as one: it reads words, not data
flows. It decides the order of the queue, never whether anything is removed.
"""

from __future__ import annotations

import re
from typing import Any

#: (category, level, words). Checked in order; the first match wins, so the
#: most sensitive categories come first.
CATEGORIES: list[tuple[str, str, tuple[str, ...]]] = [
    ("Authentication", "high", (
        "auth", "login", "logout", "signin", "signup", "otp", "mfa", "2fa", "password",
        "passwd", "token", "session", "oauth", "jwt", "credential", "verify", "reset",
        "check-otp", "forgot", "pin")),
    ("Payments", "high", (
        "pay", "payment", "payments", "transfer", "transfers", "transaction",
        "transactions", "upi", "neft", "imps", "rtgs", "swift", "wallet", "refund",
        "payout", "remit", "remittance", "beneficiary", "beneficiaries", "debit",
        "credit", "settlement", "checkout", "order", "orders", "invoice", "billing")),
    ("Cards", "high", ("card", "cards", "cvv", "pan-card", "tokenize", "tokenization")),
    # Administration before identity: "/identity/management/admin/lockUser" is an
    # admin action in a service that happens to be called identity.
    ("Administration", "high", (
        "admin", "internal", "management", "debug", "actuator", "config",
        "createdb", "migrate", "shell", "exec", "_debug", "ops", "sudo")),
    # Not "identity" or "documents" alone: both are common service and folder names.
    ("Identity and KYC", "high", (
        "kyc", "ekyc", "aadhaar", "aadhar", "pan", "passport", "ssn", "biometric",
        "id-proof", "proof-of-address")),
    ("Accounts and customers", "medium", (
        "account", "accounts", "balance", "balances", "statement", "statements", "customer",
        "customers", "user", "users", "profile", "profiles", "me", "loan", "loans",
        "deposit", "deposits", "address", "contact", "email", "phone", "mobile")),
    ("Personal data", "medium", ("dob", "birth", "gender", "photo", "avatar", "picture",
                                  "location", "gps", "medical", "health-record")),
]
PRIORITY_WEIGHT = {"high": 3, "medium": 1, "low": 0}

_SPLIT = re.compile(r"[/_\-.{}]+")


def classify(path: str, function: str | None = None) -> dict[str, str]:
    words = {w.lower() for w in _SPLIT.split(path) if w}
    raw = path.lower()
    if function:
        words |= {w.lower() for w in re.split(r"[_\W]+|(?<=[a-z])(?=[A-Z])", function) if w}
    for name, level, keys in CATEGORIES:
        hit = next((k for k in keys if k in words or ("-" in k and k in raw)), None)
        if hit:
            return {"category": name, "level": level, "because": f"the word '{hit}'"}
    return {"category": "General", "level": "low", "because": "no sensitive word in the path"}


def priority(e: dict[str, Any], usage: dict[str, Any] | None = None) -> int:
    """Higher first. Evidence against the endpoint, weighted by what it handles."""
    s = e.get("sensitivity") or classify(e.get("path", ""), e.get("function"))
    score = PRIORITY_WEIGHT.get(s["level"], 0)
    cand = e.get("candidate")
    if cand:
        score += int(cand.get("score", 0))
    if not e.get("documented"):
        score += 1
    if usage:
        if usage.get("lifecycle") == "ZOMBIE":
            score += 4
            if usage.get("failed"):
                score += 2          # dead to customers, alive to whoever is probing it
        elif usage.get("lifecycle") == "ORPHANED":
            score += 1
    return score


def enrich(report: dict[str, Any], traffic: dict[str, Any] | None = None) -> None:
    """Add sensitivity and priority to every endpoint row, in place.

    Done when a report is read rather than when it is written, so scans stored
    before this existed get it too, and the stored report (whose hash is in the
    audit chain) is never changed.
    """
    rows = (traffic or {}).get("endpoints") or {}
    for e in report.get("endpoints", []):
        e["sensitivity"] = classify(e.get("path", ""), e.get("function"))
        e["priority"] = priority(e, rows.get(e["id"]))

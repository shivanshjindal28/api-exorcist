"""
Bearer-token authentication for the REST API.

Why every endpoint needs a token, including reads
-------------------------------------------------
What this API serves is, to an attacker, a map: which endpoints are
unauthenticated, which nobody owns, which serve raw identity documents. In a
bank that inventory is sensitive in its own right, so there is no anonymous
read access. `/v1/health` is the only open route, and it says nothing.

Why identity comes from the token and never from the request
------------------------------------------------------------
Safe Kill records *who* approved a removal. If the approver's name came from
the request body, anyone holding any token could approve as anyone else, and
the hash-chained audit log would faithfully preserve a lie. The name written to
the audit log is the name bound to the presented token, and request bodies
reject unknown fields, so there is no field to forge.

Tokens
------
A token is 32 random bytes, URL-safe encoded, prefixed `apx_` so a leaked one is
recognisable in logs and secret scanners. The server stores only its SHA-256:
the configuration file, the environment and any backup of either reveal no
usable credential. A 256-bit random token needs no slow hash; there is nothing
to brute-force.

    APIX_API_TOKENS="alice:approver:<sha256>;bob:viewer:<sha256>"

`apix token NAME --role approver` prints a fresh token and the line to add.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from enum import Enum

TOKEN_PREFIX = "apx_"


class Role(str, Enum):
    VIEWER = "viewer"        # read everything
    APPROVER = "approver"    # also start shadows, decide removals, re-scan

    def allows(self, required: Role) -> bool:
        return self is Role.APPROVER or required is Role.VIEWER


@dataclass(frozen=True)
class Principal:
    name: str
    role: Role


class TokenConfigError(ValueError):
    """The token configuration is malformed. Raised at startup, never later."""


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


@dataclass(frozen=True)
class TokenStore:
    """Maps token hashes to principals. Immutable once built."""

    entries: tuple[tuple[str, Principal], ...]

    @classmethod
    def parse(cls, spec: str) -> TokenStore:
        """Parse `name:role:sha256;...`. Rejects anything ambiguous."""
        entries: list[tuple[str, Principal]] = []
        names: set[str] = set()
        for raw in spec.split(";"):
            item = raw.strip()
            if not item:
                continue
            parts = item.split(":")
            if len(parts) != 3:
                raise TokenConfigError(f"expected name:role:sha256, got {item!r}")
            name, role, digest = (x.strip() for x in parts)
            if not name or name in names:
                raise TokenConfigError(f"empty or duplicate principal name {name!r}")
            try:
                parsed_role = Role(role)
            except ValueError:
                raise TokenConfigError(
                    f"{name}: role must be 'viewer' or 'approver', got {role!r}"
                ) from None
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise TokenConfigError(
                    f"{name}: expected a lowercase SHA-256 hex digest, not a raw token"
                )
            names.add(name)
            entries.append((digest, Principal(name, parsed_role)))
        return cls(tuple(entries))

    @classmethod
    def single(cls, name: str, role: Role, token: str) -> TokenStore:
        return cls(((hash_token(token), Principal(name, role)),))

    def __bool__(self) -> bool:
        return bool(self.entries)

    def authenticate(self, token: str) -> Principal | None:
        """The principal for a presented token, or None.

        Every stored digest is compared, in constant time, whether or not an
        earlier one matched, so the response time does not reveal how many
        principals exist or where a near-miss sits.
        """
        presented = hash_token(token)
        found: Principal | None = None
        for digest, principal in self.entries:
            if hmac.compare_digest(digest, presented):
                found = principal
        return found

    def config_line(self) -> str:
        return ";".join(f"{p.name}:{p.role.value}:{d}" for d, p in self.entries)

"""
Ground truth definition of the simulated retail-banking API estate.

This module is the single source of truth for the simulated environment.
Everything else in the project (traffic generation, gateway logs, code
scanning fixtures, DNS records, and the labelled ML dataset) is derived
from what is declared here.

IMPORTANT (for evaluation integrity):
    The `true_label` field is GROUND TRUTH. It is used only by
    `dataset/` to score the classifier and must never be read by any
    connector or by the classification engine itself. Connectors see
    only the observable signals; the label is what we are trying to
    recover from those signals.

Why a synthetic estate at all?
    There is no public dataset of zombie / shadow / orphaned APIs. Real
    banks cannot share their API inventories, and no labelled corpus
    exists in the literature. To measure detection accuracy we need
    ground-truth labels, so we generate an environment whose answers we
    already know, modelled on realistic decay patterns:
      - version migrations that were never completed (v1 left running)
      - features that were decommissioned but not undeployed
      - internal tools built by teams that no longer exist
      - endpoints added directly to a service, bypassing the gateway
        registry and the OpenAPI spec (true shadow APIs)
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum


class Label(str, Enum):
    """The four classification outcomes (see Slide 12 quadrant)."""

    ACTIVE = "ACTIVE"            # documented + in genuine use
    DEPRECATED = "DEPRECATED"    # documented, announced as retiring, still responding
    ORPHANED = "ORPHANED"        # still used, but no owning team
    ZOMBIE = "ZOMBIE"            # undocumented / forgotten, no meaningful use


class Sensitivity(str, Enum):
    """Data sensitivity of the payload the endpoint handles."""

    NONE = "NONE"
    INTERNAL = "INTERNAL"
    PII = "PII"                  # personally identifiable information
    FINANCIAL = "FINANCIAL"      # balances, transactions, card data


class Auth(str, Enum):
    """Authentication posture actually enforced by the endpoint."""

    OAUTH2 = "OAUTH2"            # current standard in this estate
    JWT = "JWT"
    API_KEY = "API_KEY"          # legacy
    MTLS = "MTLS"                # service-to-service
    NONE = "NONE"                # dangerous: unauthenticated


@dataclass(frozen=True)
class Endpoint:
    """One API endpoint in the simulated estate.

    Observable fields are those a connector could realistically learn.
    `true_label` and `decay_story` are ground truth / documentation and
    are excluded from anything the detection pipeline consumes.
    """

    # --- identity ---
    service: str                  # owning microservice
    method: str                   # HTTP verb
    path: str                     # URL path
    version: str                  # api version segment

    # --- observable characteristics ---
    auth: Auth
    sensitivity: Sensitivity
    deployed_on: date             # when it first appeared
    in_openapi_spec: bool         # is it in the published spec?
    in_gateway_registry: bool     # is the gateway aware of it?
    owner_team: str | None     # None => nobody owns it
    dns_record: bool              # still resolvable via DNS
    daily_calls: int              # typical calls/day at present (0 = silent)
    last_meaningful_use_days_ago: int  # days since a real (non-probe) call
    internal_callers: tuple[str, ...] = ()  # other services that call it
    # OpenAPI `deprecated: true` vendor flag. This is a genuine OBSERVABLE the
    # spec carries, declared independently of `true_label` so no connector ever
    # reads ground truth. It is imperfect on purpose: a team can mark something
    # deprecated and never retire it, and can equally forget to mark it at all.
    spec_deprecated_flag: bool = False

    # --- ground truth (NEVER read by connectors or the classifier) ---
    true_label: Label = Label.ACTIVE
    decay_story: str = ""         # why it ended up in this state

    @property
    def endpoint_id(self) -> str:
        """Stable identifier used to correlate the same endpoint across sources."""
        return f"{self.method} /{self.version}{self.path}"

    @property
    def fqdn(self) -> str:
        return f"{self.service}.internal.examplebank.in"


# ---------------------------------------------------------------------------
# THE ESTATE
# ---------------------------------------------------------------------------
# Six services modelled on a real retail bank. Roughly 20% of endpoints are
# deliberately decayed, which matches the industry picture that most
# organisations cannot account for a meaningful slice of their API surface.

ESTATE: list[Endpoint] = [

    # ================= accounts-service =================
    Endpoint(
        service="accounts-service", method="GET", path="/accounts/{id}", version="v2",
        auth=Auth.OAUTH2, sensitivity=Sensitivity.FINANCIAL, deployed_on=date(2024, 3, 12),
        in_openapi_spec=True, in_gateway_registry=True, owner_team="core-banking",
        dns_record=True, daily_calls=412_000, last_meaningful_use_days_ago=0,
        internal_callers=("payments-service", "lending-service", "mobile-bff"),
        true_label=Label.ACTIVE,
    ),
    Endpoint(
        service="accounts-service", method="GET", path="/accounts/{id}/balance", version="v2",
        auth=Auth.OAUTH2, sensitivity=Sensitivity.FINANCIAL, deployed_on=date(2024, 3, 12),
        in_openapi_spec=True, in_gateway_registry=True, owner_team="core-banking",
        dns_record=True, daily_calls=980_000, last_meaningful_use_days_ago=0,
        internal_callers=("payments-service", "mobile-bff", "cards-service"),
        true_label=Label.ACTIVE,
    ),
    Endpoint(
        service="accounts-service", method="GET", path="/accounts/{id}", version="v1",
        auth=Auth.API_KEY, sensitivity=Sensitivity.FINANCIAL, deployed_on=date(2021, 6, 1),
        in_openapi_spec=True, in_gateway_registry=True, owner_team="core-banking",
        dns_record=True, daily_calls=340, last_meaningful_use_days_ago=2,
        internal_callers=("legacy-branch-terminal",), spec_deprecated_flag=True,
        true_label=Label.DEPRECATED,
        decay_story="v2 shipped Mar-2024 and migration was announced, but the branch "
                    "terminal estate still calls v1. Documented as deprecated, still live.",
    ),
    Endpoint(
        service="accounts-service", method="GET", path="/accounts/{id}/statement.pdf", version="v1",
        auth=Auth.API_KEY, sensitivity=Sensitivity.FINANCIAL, deployed_on=date(2021, 6, 1),
        in_openapi_spec=False, in_gateway_registry=True, owner_team=None,
        dns_record=True, daily_calls=0, last_meaningful_use_days_ago=486,
        true_label=Label.ZOMBIE,
        decay_story="Replaced by the statements-service in 2025. The route was removed "
                    "from the spec but the handler was never deleted and the gateway "
                    "rule still forwards to it. Serves financial PDFs with a legacy API key.",
    ),
    Endpoint(
        service="accounts-service", method="POST", path="/internal/accounts/reindex", version="v1",
        auth=Auth.NONE, sensitivity=Sensitivity.INTERNAL, deployed_on=date(2022, 9, 8),
        in_openapi_spec=False, in_gateway_registry=False, owner_team=None,
        dns_record=True, daily_calls=0, last_meaningful_use_days_ago=612,
        true_label=Label.ZOMBIE,
        decay_story="Built during a 2022 data-migration project by a team that has since "
                    "been dissolved. Unauthenticated, undocumented, invisible to the "
                    "gateway. Discoverable only via traffic capture and code scanning.",
    ),

    # ================= payments-service =================
    Endpoint(
        service="payments-service", method="POST", path="/payments/upi/collect", version="v3",
        auth=Auth.OAUTH2, sensitivity=Sensitivity.FINANCIAL, deployed_on=date(2025, 1, 20),
        in_openapi_spec=True, in_gateway_registry=True, owner_team="payments",
        dns_record=True, daily_calls=2_400_000, last_meaningful_use_days_ago=0,
        internal_callers=("mobile-bff", "merchant-gateway"),
        true_label=Label.ACTIVE,
    ),
    Endpoint(
        service="payments-service", method="POST", path="/payments/upi/pay", version="v3",
        auth=Auth.OAUTH2, sensitivity=Sensitivity.FINANCIAL, deployed_on=date(2025, 1, 20),
        in_openapi_spec=True, in_gateway_registry=True, owner_team="payments",
        dns_record=True, daily_calls=3_100_000, last_meaningful_use_days_ago=0,
        internal_callers=("mobile-bff",),
        true_label=Label.ACTIVE,
    ),
    Endpoint(
        service="payments-service", method="GET", path="/payments/{id}/status", version="v3",
        auth=Auth.OAUTH2, sensitivity=Sensitivity.FINANCIAL, deployed_on=date(2025, 1, 20),
        in_openapi_spec=True, in_gateway_registry=True, owner_team="payments",
        dns_record=True, daily_calls=1_750_000, last_meaningful_use_days_ago=0,
        internal_callers=("mobile-bff", "merchant-gateway", "notifications-service"),
        true_label=Label.ACTIVE,
    ),
    Endpoint(
        service="payments-service", method="POST", path="/payments/upi/pay", version="v2",
        auth=Auth.JWT, sensitivity=Sensitivity.FINANCIAL, deployed_on=date(2023, 4, 4),
        in_openapi_spec=True, in_gateway_registry=True, owner_team="payments",
        dns_record=True, daily_calls=1_200, last_meaningful_use_days_ago=1,
        internal_callers=("partner-psp-adapter",), spec_deprecated_flag=True,
        true_label=Label.DEPRECATED,
        decay_story="v3 is the current UPI path. v2 is documented as deprecated but one "
                    "external PSP partner has not migrated, so it cannot be killed yet. "
                    "A correct system must NOT flag this as a zombie.",
    ),
    Endpoint(
        service="payments-service", method="POST", path="/payments/wallet/topup", version="v1",
        auth=Auth.JWT, sensitivity=Sensitivity.FINANCIAL, deployed_on=date(2022, 2, 14),
        in_openapi_spec=False, in_gateway_registry=True, owner_team=None,
        dns_record=True, daily_calls=0, last_meaningful_use_days_ago=398,
        true_label=Label.ZOMBIE,
        decay_story="The bank exited the wallet business in 2025. The product was shut "
                    "down and the team reassigned, but the service kept running. Still "
                    "accepts topup requests against a dead ledger.",
    ),
    Endpoint(
        service="payments-service", method="POST", path="/debug/payments/replay", version="v1",
        auth=Auth.NONE, sensitivity=Sensitivity.FINANCIAL, deployed_on=date(2024, 11, 2),
        in_openapi_spec=False, in_gateway_registry=False, owner_team="payments",
        dns_record=True, daily_calls=3, last_meaningful_use_days_ago=41,
        true_label=Label.ZOMBIE,
        decay_story="A debug route added during a production incident and never removed. "
                    "Unauthenticated and able to replay financial transactions. The "
                    "highest-risk finding in the estate: low traffic, undocumented, "
                    "invisible to the gateway, but critically dangerous.",
    ),

    # ================= cards-service =================
    Endpoint(
        service="cards-service", method="GET", path="/cards/{id}", version="v1",
        auth=Auth.OAUTH2, sensitivity=Sensitivity.FINANCIAL, deployed_on=date(2023, 8, 19),
        in_openapi_spec=True, in_gateway_registry=True, owner_team="cards",
        dns_record=True, daily_calls=520_000, last_meaningful_use_days_ago=0,
        internal_callers=("mobile-bff",),
        true_label=Label.ACTIVE,
    ),
    Endpoint(
        service="cards-service", method="POST", path="/cards/{id}/block", version="v1",
        auth=Auth.OAUTH2, sensitivity=Sensitivity.FINANCIAL, deployed_on=date(2023, 8, 19),
        in_openapi_spec=True, in_gateway_registry=True, owner_team="cards",
        dns_record=True, daily_calls=18_400, last_meaningful_use_days_ago=0,
        internal_callers=("mobile-bff", "fraud-service"),
        true_label=Label.ACTIVE,
    ),
    Endpoint(
        service="cards-service", method="GET", path="/cards/{id}/pin", version="v1",
        auth=Auth.API_KEY, sensitivity=Sensitivity.FINANCIAL, deployed_on=date(2023, 8, 19),
        in_openapi_spec=False, in_gateway_registry=False, owner_team=None,
        dns_record=True, daily_calls=0, last_meaningful_use_days_ago=705,
        true_label=Label.ZOMBIE,
        decay_story="An early PIN-retrieval design abandoned before launch on security "
                    "review, but the handler shipped and was never removed. Never "
                    "documented, never registered. Only code scanning finds it.",
    ),
    Endpoint(
        service="cards-service", method="GET", path="/cards/rewards/catalogue", version="v1",
        auth=Auth.JWT, sensitivity=Sensitivity.NONE, deployed_on=date(2023, 12, 1),
        in_openapi_spec=True, in_gateway_registry=True, owner_team=None,
        dns_record=True, daily_calls=6_800, last_meaningful_use_days_ago=0,
        internal_callers=("mobile-bff",),
        true_label=Label.ORPHANED,
        decay_story="The rewards squad was disbanded in a 2026 reorg and ownership was "
                    "never reassigned. The endpoint is documented and genuinely in use, "
                    "so it must NOT be killed, but it has no owner and no one patching it.",
    ),

    # ================= kyc-service =================
    Endpoint(
        service="kyc-service", method="POST", path="/kyc/verify", version="v2",
        auth=Auth.OAUTH2, sensitivity=Sensitivity.PII, deployed_on=date(2024, 7, 7),
        in_openapi_spec=True, in_gateway_registry=True, owner_team="onboarding",
        dns_record=True, daily_calls=74_000, last_meaningful_use_days_ago=0,
        internal_callers=("onboarding-bff", "lending-service"),
        true_label=Label.ACTIVE,
    ),
    Endpoint(
        service="kyc-service", method="POST", path="/kyc/aadhaar/ekyc", version="v1",
        auth=Auth.MTLS, sensitivity=Sensitivity.PII, deployed_on=date(2022, 5, 30),
        in_openapi_spec=True, in_gateway_registry=True, owner_team="onboarding",
        dns_record=True, daily_calls=210, last_meaningful_use_days_ago=3,
        internal_callers=("onboarding-bff",), spec_deprecated_flag=False,
        true_label=Label.DEPRECATED,
        decay_story="Superseded by the v2 unified verify flow. Retained for a small "
                    "assisted-onboarding channel pending regulatory sign-off.",
    ),
    Endpoint(
        service="kyc-service", method="GET", path="/kyc/documents/{id}/raw", version="v1",
        auth=Auth.NONE, sensitivity=Sensitivity.PII, deployed_on=date(2022, 5, 30),
        in_openapi_spec=False, in_gateway_registry=False, owner_team=None,
        dns_record=True, daily_calls=0, last_meaningful_use_days_ago=548,
        true_label=Label.ZOMBIE,
        decay_story="An internal document-fetch helper used by a decommissioned ops "
                    "console. Serves raw identity documents with no authentication. "
                    "Exactly the class of endpoint that causes reportable breaches.",
    ),

    # ================= lending-service =================
    Endpoint(
        service="lending-service", method="POST", path="/loans/apply", version="v1",
        auth=Auth.OAUTH2, sensitivity=Sensitivity.PII, deployed_on=date(2025, 3, 3),
        in_openapi_spec=True, in_gateway_registry=True, owner_team="lending",
        dns_record=True, daily_calls=31_500, last_meaningful_use_days_ago=0,
        internal_callers=("mobile-bff",),
        true_label=Label.ACTIVE,
    ),
    Endpoint(
        service="lending-service", method="GET", path="/loans/{id}/schedule", version="v1",
        auth=Auth.OAUTH2, sensitivity=Sensitivity.FINANCIAL, deployed_on=date(2025, 3, 3),
        in_openapi_spec=True, in_gateway_registry=True, owner_team="lending",
        dns_record=True, daily_calls=44_200, last_meaningful_use_days_ago=0,
        internal_callers=("mobile-bff", "notifications-service"),
        true_label=Label.ACTIVE,
    ),
    Endpoint(
        service="lending-service", method="POST", path="/loans/scorecard/experiment", version="v1",
        auth=Auth.JWT, sensitivity=Sensitivity.PII, deployed_on=date(2025, 9, 15),
        in_openapi_spec=False, in_gateway_registry=False, owner_team="data-science",
        dns_record=True, daily_calls=0, last_meaningful_use_days_ago=214,
        true_label=Label.ZOMBIE,
        decay_story="A credit-scoring A/B experiment that concluded in 2025. The owning "
                    "team still exists, which is what separates this from an orphan: it "
                    "is forgotten rather than unowned. Consumes PII.",
    ),

    # ================= notifications-service =================
    Endpoint(
        service="notifications-service", method="POST", path="/notify/push", version="v1",
        auth=Auth.MTLS, sensitivity=Sensitivity.INTERNAL, deployed_on=date(2023, 1, 11),
        in_openapi_spec=True, in_gateway_registry=True, owner_team="platform",
        dns_record=True, daily_calls=890_000, last_meaningful_use_days_ago=0,
        internal_callers=("payments-service", "cards-service", "lending-service"),
        true_label=Label.ACTIVE,
    ),
    Endpoint(
        service="notifications-service", method="POST", path="/notify/sms", version="v1",
        auth=Auth.MTLS, sensitivity=Sensitivity.PII, deployed_on=date(2023, 1, 11),
        in_openapi_spec=True, in_gateway_registry=True, owner_team="platform",
        dns_record=True, daily_calls=610_000, last_meaningful_use_days_ago=0,
        internal_callers=("payments-service", "kyc-service"),
        true_label=Label.ACTIVE,
    ),
    Endpoint(
        service="notifications-service", method="POST", path="/notify/email/bulk", version="v1",
        auth=Auth.API_KEY, sensitivity=Sensitivity.PII, deployed_on=date(2023, 1, 11),
        in_openapi_spec=True, in_gateway_registry=True, owner_team=None,
        dns_record=True, daily_calls=1_400, last_meaningful_use_days_ago=6,
        internal_callers=("marketing-batch",),
        true_label=Label.ORPHANED,
        decay_story="Owned by a marketing-platform team that was outsourced. Still used "
                    "by a nightly batch job, so it is live and must not be killed, but "
                    "no internal team maintains it.",
    ),
    Endpoint(
        service="notifications-service", method="GET", path="/notify/templates/preview", version="v1",
        auth=Auth.NONE, sensitivity=Sensitivity.INTERNAL, deployed_on=date(2023, 6, 22),
        in_openapi_spec=False, in_gateway_registry=False, owner_team="platform",
        dns_record=False, daily_calls=0, last_meaningful_use_days_ago=430,
        true_label=Label.ZOMBIE,
        decay_story="A template preview tool for an internal CMS that was retired. Note "
                    "it has NO DNS record, so DNS-based discovery misses it entirely and "
                    "only code scanning plus in-cluster traffic reveals it. Tests whether "
                    "multi-source correlation actually works.",
    ),
]


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------

SERVICES: tuple[str, ...] = tuple(sorted({e.service for e in ESTATE}))


def by_id() -> dict[str, Endpoint]:
    """Map of endpoint_id -> Endpoint. Used by the dataset builder for labels."""
    return {e.endpoint_id: e for e in ESTATE}


def label_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in ESTATE:
        counts[e.true_label.value] = counts.get(e.true_label.value, 0) + 1
    return counts


def summary() -> str:
    lines = [
        "Simulated retail-banking API estate",
        f"  services : {len(SERVICES)}",
        f"  endpoints: {len(ESTATE)}",
        "  labels   : " + ", ".join(f"{k}={v}" for k, v in sorted(label_counts().items())),
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
    print()
    for svc in SERVICES:
        print(f"[{svc}]")
        for e in ESTATE:
            if e.service == svc:
                flags = []
                if not e.in_openapi_spec:
                    flags.append("no-spec")
                if not e.in_gateway_registry:
                    flags.append("no-gateway")
                if e.owner_team is None:
                    flags.append("no-owner")
                if e.auth is Auth.NONE:
                    flags.append("UNAUTH")
                if not e.dns_record:
                    flags.append("no-dns")
                flag_s = ("  [" + ",".join(flags) + "]") if flags else ""
                print(f"   {e.true_label.value:<11} {e.endpoint_id:<44}{flag_s}")
        print()

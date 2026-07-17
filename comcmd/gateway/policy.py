"""Assurance tiers A0..A4 and risk->tier classification.

Reconciled with STRATEGY.md §7.2 and the passkey reconciliation:
  A0 observe            -> auto, logged
  A1 bounded internal   -> auto within scope/budget; A1-dagger bounded-auto
                           escalates on crossing quota/blast/magnitude bounds
  A2 external reversible -> user-verified passkey step-up
  A3 consequential       -> device-bound hardware key + distinct-person dual control
  A4 prohibited          -> deny
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from comcmd.spec.models import Risk


class Tier(str, Enum):
    A0 = "A0"
    A1 = "A1"
    A2 = "A2"
    A3 = "A3"
    A4 = "A4"


_RISK_TO_TIER = {
    Risk.observe: Tier.A0,
    Risk.bounded_internal: Tier.A1,
    Risk.external_reversible: Tier.A2,
    Risk.consequential: Tier.A3,
    Risk.prohibited: Tier.A4,
}

AUTO_TIERS = {Tier.A0, Tier.A1}
APPROVAL_TIERS = {Tier.A2, Tier.A3}
DENY_TIERS = {Tier.A4}

# Minimum approval strength per approving tier.
TIER_REQUIRES = {
    Tier.A2: "passkey",           # user-verified passkey
    Tier.A3: "hardware_passkey",  # device-bound + dual control (quorum>=2)
}


@dataclass(frozen=True)
class Bounds:
    """A1-dagger bounded-auto envelope. Crossing any bound escalates to A2."""

    max_amount: float | None = None
    max_calls: int | None = None

    def within(self, *, amount: float | None, calls_so_far: int) -> bool:
        if self.max_amount is not None and amount is not None and amount > self.max_amount:
            return False
        if self.max_calls is not None and calls_so_far >= self.max_calls:
            return False
        return True


def classify(risk: Risk) -> Tier:
    return _RISK_TO_TIER[risk]

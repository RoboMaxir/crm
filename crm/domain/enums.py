"""CRM domain enums (string-valued so they persist plainly in any DB)."""
from __future__ import annotations

import enum


class StrEnum(str, enum.Enum):
    def _generate_next_value_(name, *_, **__):  # noqa: N805
        return name.lower()


class OrganizationType(StrEnum):
    customer = enum.auto()
    prospect = enum.auto()
    partner = enum.auto()
    vendor = enum.auto()
    other = enum.auto()


class RecordStatus(StrEnum):
    active = enum.auto()
    inactive = enum.auto()
    archived = enum.auto()


class LeadStatus(StrEnum):
    new = enum.auto()
    contacted = enum.auto()
    qualified = enum.auto()
    unqualified = enum.auto()
    converted = enum.auto()
    lost = enum.auto()


class Qualification(StrEnum):
    unknown = enum.auto()
    bad_fit = enum.auto()          # BANT-style qualitative flag, deterministic
    no_budget = enum.auto()
    no_authority = enum.auto()
    no_need = enum.auto()
    no_timeline = enum.auto()
    qualified = enum.auto()


class ActivityType(StrEnum):
    call = enum.auto()
    meeting = enum.auto()
    email = enum.auto()
    message = enum.auto()
    note = enum.auto()
    task = enum.auto()
    follow_up = "follow_up"
    demo = enum.auto()
    proposal = enum.auto()
    other = enum.auto()


class ActivityStatus(StrEnum):
    pending = enum.auto()
    completed = enum.auto()
    cancelled = enum.auto()


class Priority(StrEnum):
    low = enum.auto()
    medium = enum.auto()
    high = enum.auto()
    urgent = enum.auto()


class OpportunityStatus(StrEnum):
    open = enum.auto()
    won = enum.auto()
    lost = enum.auto()


# Sources are free-form but seeded with the canonical list.
LEAD_SOURCES = [
    "website", "referral", "instagram", "telegram", "linkedin",
    "cold_outreach", "existing_customer", "partner", "event", "manual",
]

LEAD_LOST_REASONS = [
    "no_response", "no_budget", "chose_competitor", "not_ready",
    "bad_fit", "unreachable", "other",
]

OPPORTUNITY_LOST_REASONS = [
    "price", "competitor", "no_decision", "timing", "scope",
    "budget_cut", "ghosted", "other",
]

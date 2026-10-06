"""CRM ORM models.

Conventions
-----------
* Every business row carries ``tenant_id`` (indexed) — isolation is enforced
  in the service layer on every query, and cross-tenant reads return 404.
* Datetimes are stored as naive UTC strings via helpers to keep SQLite and
  Postgres behaviour identical (``utcnow()`` = timezone-naive UTC).
* Money: Integer minor units + currency string. weighted_value is a stored,
  deterministic column: round(value * probability / 100).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from crm.core.db import Base


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    """Naive UTC now — consistent across DB backends."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow,
                                                 nullable=False)


# ----------------------------------------------------------------- tenant
class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class User(Base, TimestampMixin):
    """Mirror of OrgOS users (SSO-owned); used for owner display/assignment."""
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(200))
    full_name: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(20), default="member")
    external_id: Mapped[str | None] = mapped_column(String(64))  # OrgOS user id


# --------------------------------------------------------- organization
class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_org_tenant_name"),
        Index("ix_org_tenant_status", "tenant_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(20), default="prospect")
    industry: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(300))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str | None] = mapped_column(String(50))
    owner_id: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default="active")
    notes: Mapped[str | None] = mapped_column(Text)

    contacts: Mapped[list["Contact"]] = relationship(back_populates="organization")


# --------------------------------------------------------------- contact
class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"
    __table_args__ = (Index("ix_contact_tenant_org", "tenant_id", "organization_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), default="")
    job_title: Mapped[str | None] = mapped_column(String(100))
    department: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(50))
    mobile: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(200))
    linkedin: Mapped[str | None] = mapped_column(String(300))
    owner_id: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default="active")
    notes: Mapped[str | None] = mapped_column(Text)

    organization: Mapped[Organization | None] = relationship(back_populates="contacts")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


# ------------------------------------------------------------------ lead
class Lead(Base, TimestampMixin):
    __tablename__ = "leads"
    __table_args__ = (Index("ix_lead_tenant_status", "tenant_id", "status"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id"), index=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"), index=True)
    source: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    qualification: Mapped[str] = mapped_column(String(30), default="unknown")
    score: Mapped[int] = mapped_column(Integer, default=0)          # 0..100
    estimated_value: Mapped[int] = mapped_column(Integer, default=0)  # minor units
    currency: Mapped[str] = mapped_column(String(8), default="IRR")
    owner_id: Mapped[str | None] = mapped_column(String(32), index=True)
    expected_close_date: Mapped[datetime | None] = mapped_column(DateTime)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_activity_at: Mapped[datetime | None] = mapped_column(DateTime)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime)
    lost_reason: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    # conversion links (set when converted)
    converted_organization_id: Mapped[str | None] = mapped_column(String(32))
    converted_opportunity_id: Mapped[str | None] = mapped_column(String(32))


# -------------------------------------------------------------- pipeline
class Pipeline(Base, TimestampMixin):
    __tablename__ = "pipelines"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class Stage(Base, TimestampMixin):
    __tablename__ = "stages"
    __table_args__ = (UniqueConstraint("pipeline_id", "order", name="uq_stage_order"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("pipelines.id", ondelete="CASCADE"),
                                             index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0)
    probability: Mapped[int] = mapped_column(Integer, default=10)  # 0..100 default
    color: Mapped[str] = mapped_column(String(20), default="#8899aa")
    is_won: Mapped[bool] = mapped_column(Boolean, default=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------- opportunity
class Opportunity(Base, TimestampMixin):
    __tablename__ = "opportunities"
    __table_args__ = (
        Index("ix_opp_tenant_status", "tenant_id", "status"),
        Index("ix_opp_tenant_stage", "tenant_id", "stage_id"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True,
                                                 nullable=False)
    primary_contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"))
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"), index=True)
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("pipelines.id"), nullable=False)
    stage_id: Mapped[str] = mapped_column(ForeignKey("stages.id"), nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String(32), index=True)
    value: Mapped[int] = mapped_column(Integer, default=0)             # minor units
    currency: Mapped[str] = mapped_column(String(8), default="IRR")
    probability: Mapped[int] = mapped_column(Integer, default=10)      # 0..100 override
    weighted_value: Mapped[int] = mapped_column(Integer, default=0)    # stored, derived
    expected_close_date: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    lost_reason: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_activity_at: Mapped[datetime | None] = mapped_column(DateTime)
    stage_entered_at: Mapped[datetime | None] = mapped_column(DateTime)  # aging basis
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)

    stage: Mapped[Stage] = relationship()
    pipeline: Mapped[Pipeline] = relationship()
    organization: Mapped[Organization] = relationship()


# -------------------------------------------------------------- activity
class Activity(Base, TimestampMixin):
    """Activity covers both logged interactions (calls/meetings/notes) and
    actionable items (task/follow-up with due_at). Next Action for any record
    = its earliest pending Activity with due_at >= now (or overdue pending)."""
    __tablename__ = "activities"
    __table_args__ = (
        Index("ix_act_tenant_status_due", "tenant_id", "status", "due_at"),
        Index("ix_act_tenant_org", "tenant_id", "organization_id"),
        Index("ix_act_tenant_opp", "tenant_id", "opportunity_id"),
        Index("ix_act_tenant_lead", "tenant_id", "lead_id"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"))
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"))
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"))
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"))
    assigned_to: Mapped[str | None] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime)  # for logged interactions
    created_by: Mapped[str | None] = mapped_column(String(32))
    overdue_notified: Mapped[bool] = mapped_column(Boolean, default=False)


# ------------------------------------------------------------------ tags
class Tag(Base, TimestampMixin):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_tag_tenant_name"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="#6b7280")


class TaggedItem(Base):
    __tablename__ = "tagged_items"
    __table_args__ = (
        UniqueConstraint("tag_id", "entity", "entity_id", name="uq_tag_item"),
        Index("ix_tagged_entity", "tenant_id", "entity", "entity_id"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    tag_id: Mapped[str] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), index=True)
    entity: Mapped[str] = mapped_column(String(30))   # organization|contact|lead|opportunity|activity
    entity_id: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    tag: Mapped[Tag] = relationship()


# ------------------------------------------------------------ saved views
class SavedFilter(Base, TimestampMixin):
    __tablename__ = "saved_filters"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(32), index=True)
    entity: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(100))
    params_json: Mapped[str] = mapped_column(Text, default="{}")


# ---------------------------------------------------------------- audit
class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_tenant_entity", "tenant_id", "entity", "entity_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    entity: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


# ------------------------------------------------------- domain events
class DomainEvent(Base):
    """Transactional outbox: written in the same transaction as state change."""
    __tablename__ = "domain_events"
    __table_args__ = (Index("ix_event_tenant_type", "tenant_id", "event_type"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[str] = mapped_column(String(32))
    payload: Mapped[str] = mapped_column(Text, default="{}")
    actor_id: Mapped[str | None] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)


# ------------------------------------------------------------- webhooks
class WebhookEndpoint(Base, TimestampMixin):
    __tablename__ = "webhook_endpoints"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    events: Mapped[str] = mapped_column(Text, default="*")   # comma list or "*"
    secret: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    endpoint_id: Mapped[str] = mapped_column(ForeignKey("webhook_endpoints.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[str] = mapped_column(Text)
    signature: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|delivered|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=5)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    response_code: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)


# -------------------------------------------------------- intelligence
class IntelligenceItem(Base, TimestampMixin):
    """Consumer-side store for AI/OrgOS insights.

    The CRM NEVER computes these itself; an external Intelligence layer
    pushes them via POST /intelligence. They are displayed read-only in
    Customer 360 and are excluded from all core business logic.
    """
    __tablename__ = "intelligence_items"
    __table_args__ = (Index("ix_intel_tenant_entity", "tenant_id", "entity", "entity_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    entity: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(20))   # insight|risk|recommendation
    text: Mapped[str] = mapped_column(Text)
    source_system: Mapped[str] = mapped_column(String(40), default="shora")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

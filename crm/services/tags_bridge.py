"""Tag bridge — generic tagging for ALL CRM entities.

orgs.set_tags only covers organization/contact (models imported at module
level there). This module extends the same tag system to leads, opportunities
and activities without circular imports.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from crm.core.auth import Identity
from crm.domain.models import Activity, Contact, Lead, Opportunity, Organization, Tag, TaggedItem
from crm.services.common import get_tenant

TAGGABLE_MODELS = {
    "organization": Organization,
    "contact": Contact,
    "lead": Lead,
    "opportunity": Opportunity,
    "activity": Activity,
}


def entity_ids_with_tag(session: Session, identity: Identity, entity: str,
                        tag_name: str) -> list[str]:
    rows = session.execute(
        select(TaggedItem.entity_id).join(Tag, Tag.id == TaggedItem.tag_id).where(
            TaggedItem.tenant_id == identity.tenant_id,
            TaggedItem.entity == entity,
            Tag.name == tag_name)).scalars().all()
    return list(rows)


def tags_of(session: Session, identity: Identity, entity: str, entity_id: str) -> list[str]:
    rows = session.execute(
        select(Tag.name).join(TaggedItem, TaggedItem.tag_id == Tag.id).where(
            TaggedItem.tenant_id == identity.tenant_id,
            TaggedItem.entity == entity,
            TaggedItem.entity_id == entity_id).order_by(Tag.name)).scalars().all()
    return list(rows)


def set_entity_tags(session: Session, identity: Identity, entity: str, entity_id: str,
                    names: list[str]) -> list[str]:
    model = TAGGABLE_MODELS.get(entity)
    if model is None:
        raise ValueError(f"Cannot tag entity '{entity}'")
    get_tenant(session, model, identity, entity_id)
    keep = {n.strip() for n in names if n and n.strip()}
    existing = session.execute(select(TaggedItem).where(
        TaggedItem.tenant_id == identity.tenant_id,
        TaggedItem.entity == entity,
        TaggedItem.entity_id == entity_id)).scalars().all()
    current = {}
    for ti in existing:
        current[ti.tag.name] = ti
    for name, ti in current.items():
        if name not in keep:
            session.delete(ti)
    from crm.services.orgs import ensure_tag
    for name in keep - set(current):
        tag = ensure_tag(session, identity, name)
        session.add(TaggedItem(tenant_id=identity.tenant_id, tag_id=tag.id,
                               entity=entity, entity_id=entity_id))
    session.flush()
    return sorted(keep)

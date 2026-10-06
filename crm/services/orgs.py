"""CRUD services for Organizations, Contacts and Tags.

Every function:
  * takes Identity -> every query is tenant-scoped (backend-enforced),
  * writes an audit entry for create/update/delete/assignment,
  * emits domain events for state changes that matter downstream.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from crm.core.audit import audit
from crm.core.auth import Identity
from crm.core.events import emit
from crm.domain.models import Contact, Organization, Tag, TaggedItem
from crm.services.common import conflict, finalize_list, apply_list_query, get_tenant

TAGGABLE = {"organization": Organization, "contact": Contact}


def _snapshot(obj) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns
            if c.key not in ("created_at", "updated_at")}


# ------------------------------------------------------------ organizations
def list_organizations(session: Session, identity: Identity, *, q=None, status=None,
                       type=None, owner_id=None, city=None, tag=None,
                       sort=None, order="desc", page=1, per_page=25):
    stmt = select(Organization).where(Organization.tenant_id == identity.tenant_id)
    filters = {"status": status, "type": type, "owner_id": owner_id, "city": city}
    if tag:
        sub = select(TaggedItem.entity_id).where(
            TaggedItem.tenant_id == identity.tenant_id,
            TaggedItem.entity == "organization",
            TaggedItem.tag_id.in_(select(Tag.id).where(
                Tag.tenant_id == identity.tenant_id, Tag.name == tag)))
        stmt = stmt.where(Organization.id.in_(sub))
    stmt, count_stmt = apply_list_query(
        stmt, search_fields=[Organization.name, Organization.legal_name,
                             Organization.website, Organization.city],
        q=q, filters=filters, model=Organization)
    return finalize_list(session, stmt, count_stmt, Organization,
                         sort=sort or "created_at", order=order, page=page, per_page=per_page)


def create_organization(session: Session, identity: Identity, data: dict) -> Organization:
    name = (data.get("name") or "").strip()
    if not name:
        raise conflict("Organization name is required")
    payload = {k: v for k, v in data.items() if k not in ("tags", "name")}
    org = Organization(tenant_id=identity.tenant_id, name=name, **payload)
    session.add(org)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise conflict(f"Organization '{name}' already exists in this tenant")
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="create", entity="organization", entity_id=org.id, after=_snapshot(org))
    emit(session, "customer.created", identity.tenant_id, "organization", org.id,
         {"name": org.name}, actor_id=identity.user_id)
    if data.get("tags"):
        set_tags(session, identity, "organization", org.id, data["tags"])
    return org


def get_organization(session: Session, identity: Identity, oid: str) -> Organization:
    return get_tenant(session, Organization, identity, oid)


def update_organization(session: Session, identity: Identity, oid: str,
                        data: dict) -> Organization:
    org = get_tenant(session, Organization, identity, oid)
    before = _snapshot(org)
    tags = data.pop("tags", None)
    owner_changed = "owner_id" in data and data["owner_id"] != org.owner_id
    for k, v in data.items():
        if hasattr(org, k) and k not in ("id", "tenant_id", "created_at"):
            setattr(org, k, v)
    session.flush()
    after = _snapshot(org)
    action = "owner_change" if owner_changed else "update"
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action=action, entity="organization", entity_id=oid, before=before, after=after)
    emit(session, "customer.updated", identity.tenant_id, "organization", oid,
         {"changed": sorted(k for k in after if before.get(k) != after.get(k))},
         actor_id=identity.user_id)
    if tags is not None:
        set_tags(session, identity, "organization", oid, tags)
    return org


def delete_organization(session: Session, identity: Identity, oid: str) -> None:
    org = get_tenant(session, Organization, identity, oid)
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="delete", entity="organization", entity_id=oid, before=_snapshot(org))
    session.delete(org)
    session.flush()


# ------------------------------------------------------------------ contacts
def list_contacts(session: Session, identity: Identity, *, q=None, status=None,
                  organization_id=None, owner_id=None, tag=None,
                  sort=None, order="desc", page=1, per_page=25):
    full_name = Contact.first_name + " " + Contact.last_name
    stmt = select(Contact).where(Contact.tenant_id == identity.tenant_id)
    filters = {"status": status, "organization_id": organization_id, "owner_id": owner_id}
    if tag:
        sub = select(TaggedItem.entity_id).where(
            TaggedItem.tenant_id == identity.tenant_id,
            TaggedItem.entity == "contact",
            TaggedItem.tag_id.in_(select(Tag.id).where(
                Tag.tenant_id == identity.tenant_id, Tag.name == tag)))
        stmt = stmt.where(Contact.id.in_(sub))
    stmt, count_stmt = apply_list_query(
        stmt, search_fields=[Contact.first_name, Contact.last_name, full_name,
                             Contact.email, Contact.phone, Contact.job_title],
        q=q, filters=filters, model=Contact)
    return finalize_list(session, stmt, count_stmt, Contact,
                         sort=sort or "created_at", order=order, page=page, per_page=per_page)


def create_contact(session: Session, identity: Identity, data: dict) -> Contact:
    if not (data.get("first_name") or "").strip():
        raise conflict("Contact first_name is required")
    if data.get("organization_id"):
        get_tenant(session, Organization, identity, data["organization_id"])
    tags = data.pop("tags", None)
    contact = Contact(tenant_id=identity.tenant_id, **data)
    session.add(contact)
    session.flush()
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="create", entity="contact", entity_id=contact.id, after=_snapshot(contact))
    emit(session, "contact.created", identity.tenant_id, "contact", contact.id,
         {"name": contact.full_name, "organization_id": contact.organization_id},
         actor_id=identity.user_id)
    if tags:
        set_tags(session, identity, "contact", contact.id, tags)
    return contact


def get_contact(session: Session, identity: Identity, cid: str) -> Contact:
    return get_tenant(session, Contact, identity, cid)


def update_contact(session: Session, identity: Identity, cid: str, data: dict) -> Contact:
    contact = get_tenant(session, Contact, identity, cid)
    before = _snapshot(contact)
    tags = data.pop("tags", None)
    for k, v in data.items():
        if hasattr(contact, k) and k not in ("id", "tenant_id", "created_at"):
            setattr(contact, k, v)
    session.flush()
    after = _snapshot(contact)
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="update", entity="contact", entity_id=cid, before=before, after=after)
    if tags is not None:
        set_tags(session, identity, "contact", cid, tags)
    return contact


def delete_contact(session: Session, identity: Identity, cid: str) -> None:
    contact = get_tenant(session, Contact, identity, cid)
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="delete", entity="contact", entity_id=cid, before=_snapshot(contact))
    session.delete(contact)
    session.flush()


# --------------------------------------------------------------------- tags
def ensure_tag(session: Session, identity: Identity, name: str) -> Tag:
    name = name.strip()
    tag = session.execute(select(Tag).where(Tag.tenant_id == identity.tenant_id,
                                            Tag.name == name)).scalar_one_or_none()
    if tag is None:
        tag = Tag(tenant_id=identity.tenant_id, name=name)
        session.add(tag)
        session.flush()
    return tag


def list_tags(session: Session, identity: Identity):
    return session.execute(select(Tag).where(Tag.tenant_id == identity.tenant_id)
                           .order_by(Tag.name)).scalars().all()


def set_tags(session: Session, identity: Identity, entity: str, entity_id: str,
             names: list[str]) -> list[Tag]:
    """Replace the tag set of an entity."""
    model = TAGGABLE.get(entity)
    if model is None:
        raise conflict(f"Cannot tag entity '{entity}'")
    get_tenant(session, model, identity, entity_id)
    existing = session.execute(select(TaggedItem).where(
        TaggedItem.tenant_id == identity.tenant_id,
        TaggedItem.entity == entity,
        TaggedItem.entity_id == entity_id)).scalars().all()
    keep_names = {n.strip() for n in names if n.strip()}
    current_map = {}
    for ti in existing:
        current_map[ti.tag.name] = ti
    for name, ti in current_map.items():
        if name not in keep_names:
            session.delete(ti)
    for name in keep_names - set(current_map):
        tag = ensure_tag(session, identity, name)
        session.add(TaggedItem(tenant_id=identity.tenant_id, tag_id=tag.id,
                               entity=entity, entity_id=entity_id))
    session.flush()
    return get_entity_tags(session, identity, entity, entity_id)


def get_entity_tags(session: Session, identity: Identity, entity: str,
                    entity_id: str) -> list[Tag]:
    rows = session.execute(
        select(Tag).join(TaggedItem, TaggedItem.tag_id == Tag.id).where(
            TaggedItem.tenant_id == identity.tenant_id,
            TaggedItem.entity == entity,
            TaggedItem.entity_id == entity_id)).scalars().all()
    return list(rows)

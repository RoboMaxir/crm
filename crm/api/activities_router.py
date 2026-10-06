"""/api/v1/activities — interactions, tasks and follow-ups (Next Action)."""
from __future__ import annotations

from datetime import datetime

from fastapi import Depends, APIRouter, Body, Query

from crm.api.deps import DB, IDP, coerce_dates, dump
from crm.core.auth import PERM_ASSIGN, PERM_CREATE, PERM_UPDATE, require
from crm.services import activities as svc
from crm.services.tags_bridge import set_entity_tags, tags_of

router = APIRouter(prefix="/activities", tags=["activities"])


def _view(db, me, act) -> dict:
    d = dump(act)
    d["tags"] = tags_of(db, me, "activity", act.id)
    return d


@router.get("")
def list_activities(db=DB, me=IDP, q: str | None = None, type: str | None = None,
                    status: str | None = None, priority: str | None = None,
                    assigned_to: str | None = None, organization_id: str | None = None,
                    lead_id: str | None = None, opportunity_id: str | None = None,
                    contact_id: str | None = None,
                    due_before: datetime | None = None, due_after: datetime | None = None,
                    sort: str | None = None, order: str = "desc",
                    page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=200)):
    res = svc.list_activities(db, me, q=q, type=type, status=status, priority=priority,
                              assigned_to=assigned_to, organization_id=organization_id,
                              lead_id=lead_id, opportunity_id=opportunity_id,
                              contact_id=contact_id, due_before=due_before,
                              due_after=due_after, sort=sort, order=order,
                              page=page, per_page=per_page)
    return {"items": [_view(db, me, a) for a in res["items"]],
            "total": res["total"], "page": res["page"], "per_page": res["per_page"],
            "pages": res["pages"]}


@router.post("", status_code=201)
def create_activity(data: dict = Body(...), db=DB, me=Depends(require(PERM_CREATE))):
    if data.get("assigned_to") and data["assigned_to"] != me.user_id \
            and not me.can(PERM_ASSIGN):
        from crm.services.common import unprocessable
        raise unprocessable("Role lacks 'assign' permission to assign to others")
    return _view(db, me, svc.create_activity(db, me, coerce_dates(dict(data))))


@router.get("/{aid}")
def get_activity(aid: str, db=DB, me=IDP):
    return _view(db, me, _fetch(db, me, aid))


def _fetch(db, me, aid):
    from crm.domain.models import Activity
    from crm.services.common import get_tenant
    return get_tenant(db, Activity, me, aid)


@router.patch("/{aid}")
def update_activity(aid: str, data: dict = Body(...), db=DB,
                    me=Depends(require(PERM_UPDATE))):
    if data.get("assigned_to") and data["assigned_to"] != me.user_id \
            and not me.can(PERM_ASSIGN):
        from crm.services.common import unprocessable
        raise unprocessable("Role lacks 'assign' permission to reassign")
    return _view(db, me, svc.update_activity(db, me, aid, coerce_dates(dict(data))))


@router.post("/{aid}/complete")
def complete(aid: str, db=DB, me=Depends(require(PERM_UPDATE))):
    return _view(db, me, svc.complete_activity(db, me, aid))


@router.post("/{aid}/cancel")
def cancel(aid: str, db=DB, me=Depends(require(PERM_UPDATE))):
    return _view(db, me, svc.cancel_activity(db, me, aid))


@router.put("/{aid}/tags")
def replace_tags(aid: str, tags: list[str] = Body(...), db=DB,
                 me=Depends(require(PERM_UPDATE))):
    return {"tags": set_entity_tags(db, me, "activity", aid, tags)}


@router.post("/sweep-overdue")
def sweep_overdue(db=DB, me=Depends(require(PERM_UPDATE))):
    """Deterministic sweep emitting activity.overdue once per overdue item.
    Intended to be called by a scheduler; safe to call repeatedly."""
    return {"marked": svc.mark_overdue_events(db, me)}

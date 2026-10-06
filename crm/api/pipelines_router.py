"""/api/v1/pipelines — configurable pipelines & stages."""
from __future__ import annotations

from fastapi import Depends, APIRouter, Body

from crm.api.deps import DB, IDP, dump
from crm.core.auth import PERM_CREATE, PERM_MANAGE, PERM_UPDATE, require
from crm.services import pipelines as svc

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.get("")
def list_pipelines(db=DB, me=IDP):
    return {"items": [dump(p) for p in svc.list_pipelines(db, me)]}


@router.post("", status_code=201)
def create_pipeline(data: dict = Body(...), db=DB, me=Depends(require(PERM_MANAGE))):
    pipe = svc.create_pipeline(db, me, data.get("name", ""), data.get("stages") or [])
    return dump(pipe) | {"stages": [dump(s) for s in svc.get_stages(db, me, pipe.id)]}


@router.post("/ensure-default")
def ensure_default(db=DB, me=Depends(require(PERM_CREATE))):
    """Idempotently seed the standard Sales pipeline for this tenant."""
    return dump(svc.ensure_default_pipeline(db, me))


@router.get("/{pid}/stages")
def get_stages(pid: str, db=DB, me=IDP):
    return {"items": [dump(s) for s in svc.get_stages(db, me, pid)]}


@router.patch("/stages/{sid}")
def update_stage(sid: str, data: dict = Body(...), db=DB,
                 me=Depends(require(PERM_MANAGE))):
    return dump(svc.update_stage(db, me, sid, dict(data)))

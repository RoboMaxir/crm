"""/api/v1/quick — Quick Capture: Org + Contact + Lead + Next Action in one call."""
from __future__ import annotations

from fastapi import Depends, APIRouter, Body

from crm.api.deps import DB, IDP, coerce_dates
from crm.core.auth import PERM_CREATE, require
from crm.services import quick_capture as svc


def _plain(obj) -> dict | None:
    if obj is None:
        return None
    out = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.key)
        out[c.key] = v.isoformat() if hasattr(v, "isoformat") else v
    return out


router = APIRouter(prefix="/quick", tags=["quick"])


@router.post("/capture", status_code=201)
def capture(data: dict = Body(...), db=DB, me=Depends(require(PERM_CREATE))):
    res = svc.quick_capture(db, me, coerce_dates(dict(data)))
    return {"organization": _plain(res["organization"]),
            "organization_created": res["organization_created"],
            "contact": _plain(res["contact"]),
            "contact_created": res["contact_created"],
            "lead": _plain(res["lead"]),
            "next_action": _plain(res["next_action"])}

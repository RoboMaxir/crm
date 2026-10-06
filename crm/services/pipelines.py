"""Pipelines & Stages (configurable), seeded with a default Sales pipeline."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from crm.core.audit import audit
from crm.core.auth import Identity
from crm.domain.models import Pipeline, Stage
from crm.services.common import get_tenant, unprocessable

DEFAULT_STAGES = [
    # name, order, probability, color, is_won, is_lost
    ("New",         1, 10,  "#94a3b8", False, False),
    ("Discovery",   2, 25,  "#60a5fa", False, False),
    ("Qualified",   3, 40,  "#38bdf8", False, False),
    ("Proposal",    4, 60,  "#a78bfa", False, False),
    ("Negotiation", 5, 80,  "#fbbf24", False, False),
    ("Won",         6, 100, "#34d399", True,  False),
    ("Lost",        7, 0,   "#f87171", False, True),
]


def ensure_default_pipeline(session: Session, identity: Identity) -> Pipeline:
    """Idempotent seed of the standard Sales pipeline for a tenant."""
    pipe = session.execute(select(Pipeline).where(
        Pipeline.tenant_id == identity.tenant_id,
        Pipeline.is_default.is_(True))).scalars().first()
    if pipe:
        return pipe
    pipe = Pipeline(tenant_id=identity.tenant_id, name="Sales", is_default=True)
    session.add(pipe)
    session.flush()
    for name, order, prob, color, won, lost in DEFAULT_STAGES:
        session.add(Stage(tenant_id=identity.tenant_id, pipeline_id=pipe.id,
                          name=name, order=order, probability=prob, color=color,
                          is_won=won, is_lost=lost))
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="create", entity="pipeline", entity_id=pipe.id, after={"name": "Sales"})
    session.flush()
    return pipe


def list_pipelines(session: Session, identity: Identity):
    return session.execute(select(Pipeline).where(
        Pipeline.tenant_id == identity.tenant_id).order_by(Pipeline.created_at)
    ).scalars().all()


def get_stages(session: Session, identity: Identity, pipeline_id: str):
    get_tenant(session, Pipeline, identity, pipeline_id)
    return session.execute(select(Stage).where(
        Stage.pipeline_id == pipeline_id,
        Stage.tenant_id == identity.tenant_id).order_by(Stage.order)
    ).scalars().all()


def create_pipeline(session: Session, identity: Identity, name: str,
                    stages: list[dict]) -> Pipeline:
    if not name.strip():
        raise unprocessable("Pipeline name required")
    pipe = Pipeline(tenant_id=identity.tenant_id, name=name.strip())
    session.add(pipe)
    session.flush()
    for i, s in enumerate(stages or [], start=1):
        session.add(Stage(
            tenant_id=identity.tenant_id, pipeline_id=pipe.id,
            name=s.get("name", f"Stage {i}"), order=s.get("order", i),
            probability=max(0, min(100, int(s.get("probability", 10)))),
            color=s.get("color", "#8899aa"),
            is_won=bool(s.get("is_won")), is_lost=bool(s.get("is_lost"))))
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="create", entity="pipeline", entity_id=pipe.id, after={"name": name})
    session.flush()
    return pipe


def update_stage(session: Session, identity: Identity, stage_id: str,
                 data: dict) -> Stage:
    stage = get_tenant(session, Stage, identity, stage_id)
    before = {"probability": stage.probability, "name": stage.name, "order": stage.order}
    for k in ("name", "order", "probability", "color"):
        if k in data and data[k] is not None:
            setattr(stage, k, data[k])
    if "probability" in data and data["probability"] is not None:
        stage.probability = max(0, min(100, int(data["probability"])))
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="update", entity="stage", entity_id=stage_id,
          before=before, after={"probability": stage.probability, "name": stage.name,
                                "order": stage.order})
    session.flush()
    return stage

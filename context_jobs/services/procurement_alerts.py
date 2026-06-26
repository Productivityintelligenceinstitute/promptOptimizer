"""Procurement alert query and dismiss services."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from schemas.context_jobs_model import ProcurementAlertModel


def list_undismissed_alerts(db: Session, owner: str) -> list[ProcurementAlertModel]:
    return (
        db.query(ProcurementAlertModel)
        .filter(
            ProcurementAlertModel.owner == owner,
            ProcurementAlertModel.dismissed.is_(False),
        )
        .order_by(ProcurementAlertModel.expiry_date.asc())
        .all()
    )


def dismiss_alert(db: Session, owner: str, alert_id: UUID) -> ProcurementAlertModel | None:
    alert = (
        db.query(ProcurementAlertModel)
        .filter(
            ProcurementAlertModel.id == alert_id,
            ProcurementAlertModel.owner == owner,
        )
        .first()
    )
    if not alert:
        return None
    alert.dismissed = True
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert

"""Procurement intelligence API routes (Tier 3)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from context_jobs.auth import get_context_jobs_owner_with_access
from context_jobs.schemas import ProcurementAlertOut
from context_jobs.services import procurement_alerts as alert_services
from database import database

router = APIRouter(prefix="/procurement", tags=["Context Jobs - Procurement"])


@router.get("/alerts", response_model=list[ProcurementAlertOut])
async def list_procurement_alerts(
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
) -> list[ProcurementAlertOut]:
    alerts = alert_services.list_undismissed_alerts(db, owner)
    return [ProcurementAlertOut.model_validate(alert) for alert in alerts]


@router.post("/alerts/{alert_id}/dismiss", response_model=ProcurementAlertOut)
async def dismiss_procurement_alert(
    alert_id: UUID,
    owner: str = Depends(get_context_jobs_owner_with_access),
    db: Session = Depends(database.get_db),
) -> ProcurementAlertOut:
    alert = alert_services.dismiss_alert(db, owner, alert_id)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found.")
    return ProcurementAlertOut.model_validate(alert)

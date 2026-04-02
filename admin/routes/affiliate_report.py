"""
Admin affiliate reporting via Stripe API (Subscription + Invoice list).
Uses only standard Stripe resources available on every account.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from apis.routers.stripe import _stripe_get
from core.config import (
    AFFILIATE_CODES,
    STRIPE_PRICE_ID_ESSENTIAL,
    STRIPE_PRICE_ID_PRO,
    STRIPE_SECRET_KEY,
)
from database import database
from repositories.check_role import RoleRepository

logger = logging.getLogger(__name__)

affiliate_report_router = APIRouter()


def _sum_paid_invoice_amounts_by_currency(subscription_id: str) -> dict[str, int]:
    """Sum amount_paid for all paid invoices for this subscription (cents per currency)."""
    totals: dict[str, int] = defaultdict(int)
    try:
        for inv in stripe.Invoice.list(
            subscription=subscription_id,
            status="paid",
            limit=100,
        ).auto_paging_iter():
            cents = int(_stripe_get(inv, "amount_paid", 0) or 0)
            cur = (_stripe_get(inv, "currency") or "usd").lower()
            totals[cur] += cents
    except stripe.error.StripeError as e:
        logger.warning("Invoice list failed for subscription %s: %s", subscription_id, e)
    return dict(totals)


def _merge_currency_maps(
    target: dict[str, int], source: dict[str, int]
) -> None:
    for cur, cents in source.items():
        target[cur] = target.get(cur, 0) + cents


def _plan_display_name(sub: Any) -> str:
    """Prefer subscription metadata plan_name from checkout; else map price id to Essential/Pro."""
    md = _stripe_get(sub, "metadata", {}) or {}
    plan = _stripe_get(md, "plan_name")
    if plan and str(plan).strip():
        return str(plan).strip()
    try:
        items = _stripe_get(sub, "items", {}) or {}
        data = _stripe_get(items, "data", []) or []
        if not data:
            return "—"
        price_obj = _stripe_get(data[0], "price", {})
        pid = _stripe_get(price_obj, "id")
        if pid and STRIPE_PRICE_ID_ESSENTIAL and pid == STRIPE_PRICE_ID_ESSENTIAL:
            return "Essential"
        if pid and STRIPE_PRICE_ID_PRO and pid == STRIPE_PRICE_ID_PRO:
            return "Pro"
        nick = _stripe_get(price_obj, "nickname")
        if nick and str(nick).strip():
            return str(nick).strip()
        return str(pid) if pid else "—"
    except Exception:
        return "—"


def _customer_display_name(
    customer_id: str, cache: dict[str, str]
) -> str:
    if not customer_id:
        return "—"
    if customer_id in cache:
        return cache[customer_id]
    try:
        c = stripe.Customer.retrieve(customer_id)
        name = _stripe_get(c, "name")
        email = _stripe_get(c, "email")
        if name and str(name).strip():
            out = str(name).strip()
        elif email and str(email).strip():
            out = str(email).strip()
        else:
            out = "—"
        cache[customer_id] = out
        return out
    except stripe.error.StripeError:
        cache[customer_id] = "—"
        return "—"


@affiliate_report_router.get("/admin/affiliate-report")
async def get_affiliate_report(
    user_id: str = Query(..., description="Current admin user id"),
    db: Session = Depends(database.get_db),
) -> dict[str, Any]:
    """
    Lists all Stripe subscriptions that have `affiliate_code` in subscription metadata,
    groups by code, and sums paid invoice amounts per subscription.

    Revenue = sum of `amount_paid` on invoices with status=paid for that subscription.
    """
    role = RoleRepository.check_role(db, user_id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can view this report")

    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe is not configured")

    allowlist = AFFILIATE_CODES

    # affiliate_code -> list of subscription detail dicts
    by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grand_totals_by_currency: dict[str, int] = defaultdict(int)
    grand_subscription_count = 0
    customer_name_cache: dict[str, str] = {}

    try:
        for sub in stripe.Subscription.list(limit=100).auto_paging_iter():
            md = _stripe_get(sub, "metadata", {}) or {}
            code_raw = _stripe_get(md, "affiliate_code")
            if not code_raw:
                continue
            code = str(code_raw).strip().lower()
            if not code:
                continue
            if allowlist and code not in allowlist:
                continue

            sub_id = _stripe_get(sub, "id")
            if not sub_id:
                continue

            cust = _stripe_get(sub, "customer")
            customer_id = str(cust) if cust else ""

            rev_by_cur = _sum_paid_invoice_amounts_by_currency(sub_id)
            _merge_currency_maps(grand_totals_by_currency, rev_by_cur)

            row = {
                "customer_name": _customer_display_name(customer_id, customer_name_cache),
                "plan_name": _plan_display_name(sub),
                "status": str(_stripe_get(sub, "status", "") or ""),
                "revenue_by_currency": rev_by_cur,
                # Stable id for clients; not shown in the admin UI table
                "stripe_subscription_id": sub_id,
            }
            by_code[code].append(row)
            grand_subscription_count += 1
    except stripe.error.StripeError as e:
        logger.exception("Stripe error building affiliate report")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to load data from Stripe: {str(e)}",
        ) from e

    rows_out: list[dict[str, Any]] = []
    for code in sorted(by_code.keys()):
        subs = by_code[code]
        code_totals: dict[str, int] = defaultdict(int)
        for s in subs:
            _merge_currency_maps(code_totals, s["revenue_by_currency"])
        rows_out.append(
            {
                "affiliate_code": code,
                "subscription_count": len(subs),
                "revenue_by_currency": dict(code_totals),
                "subscriptions": subs,
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "stripe_api",
        "note": (
            "Revenue is the sum of paid invoice amount_paid per subscription. "
            "Only subscriptions with affiliate_code in metadata are included; "
            "when AFFILIATE_CODES is set, codes outside the allowlist are omitted."
        ),
        "rows": rows_out,
        "grand_totals_by_currency": dict(grand_totals_by_currency),
        "grand_subscription_count": grand_subscription_count,
    }

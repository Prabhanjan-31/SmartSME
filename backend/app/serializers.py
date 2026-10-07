"""JSON shapes returned to the SPA.

Keys are camelCase so the React code reads naturally; the database stays
snake_case.
"""

from __future__ import annotations

from datetime import datetime

from .core.utils import round2
from .models import (
    Event,
    Expense,
    Notification,
    Party,
    Payment,
    Product,
    Purchase,
    PurchaseItem,
    Sale,
    SaleItem,
    StockMovement,
    WorkflowExecution,
    WorkflowRule,
)


def _money_state(doc: Sale | Purchase) -> dict:
    """The payment side of a document: what is owed, by when, and whether
    that day has passed."""
    due = 0 if doc.status == "cancelled" else round2(doc.total - doc.amount_paid)
    return {
        "total": doc.total,
        "amountPaid": doc.amount_paid,
        "due": due,
        "dueDate": doc.due_date.isoformat(),
        "overdue": due > 0 and doc.due_date < datetime.now(),
        "paymentStatus": doc.payment_status,
    }


def payment(p: Payment) -> dict:
    return {
        "id": str(p.id),
        "amount": p.amount,
        "reason": p.reason,
        "date": p.date.isoformat(),
        "mode": p.mode,
        "reference": p.reference,
        "details": p.details or {},
    }


def sale_row(sale: Sale, party_name: str | None) -> dict:
    return {
        "id": str(sale.id),
        "invoiceNumber": sale.invoice_number,
        "date": sale.date.isoformat(),
        "partyName": party_name,
        "source": sale.source,
        "status": sale.status,
        **_money_state(sale),
    }


def line_item(item: SaleItem | PurchaseItem) -> dict:
    return {
        "id": str(item.id),
        "productId": str(item.product_id) if item.product_id else None,
        "description": item.description,
        "quantity": item.quantity,
        "unitPrice": item.unit_price,
        "lineTotal": item.line_total,
    }


def _party_brief(party: Party | None) -> dict | None:
    if party is None:
        return None
    return {
        "id": str(party.id),
        "name": party.name,
        "phone": party.phone,
        "gstNumber": party.gst_number,
        "address": party.address,
    }


def sale_detail(
    sale: Sale, party: Party | None, items: list[SaleItem], payments: list[Payment] = ()
) -> dict:
    return {
        "id": str(sale.id),
        "invoiceNumber": sale.invoice_number,
        "date": sale.date.isoformat(),
        "createdAt": sale.created_at.isoformat(),
        "status": sale.status,
        "source": sale.source,
        "subtotal": sale.subtotal,
        "discountType": sale.discount_type,
        "discountValue": sale.discount_value,
        "discountAmount": sale.discount_amount,
        "tax": sale.tax,
        **_money_state(sale),
        "notes": sale.notes,
        "party": _party_brief(party),
        "items": [line_item(i) for i in items],
        "payments": [payment(p) for p in payments],
    }


def purchase_row(purchase: Purchase, party_name: str | None) -> dict:
    return {
        "id": str(purchase.id),
        "referenceNumber": purchase.reference_number,
        "date": purchase.date.isoformat(),
        "partyName": party_name,
        "source": purchase.source,
        "status": purchase.status,
        **_money_state(purchase),
    }


def purchase_detail(
    purchase: Purchase,
    party: Party | None,
    items: list[PurchaseItem],
    payments: list[Payment] = (),
) -> dict:
    return {
        "id": str(purchase.id),
        "referenceNumber": purchase.reference_number,
        "date": purchase.date.isoformat(),
        "createdAt": purchase.created_at.isoformat(),
        "status": purchase.status,
        "source": purchase.source,
        "subtotal": purchase.subtotal,
        "discountType": purchase.discount_type,
        "discountValue": purchase.discount_value,
        "discountAmount": purchase.discount_amount,
        "tax": purchase.tax,
        **_money_state(purchase),
        "notes": purchase.notes,
        "party": _party_brief(party),
        "items": [line_item(i) for i in items],
        "payments": [payment(p) for p in payments],
    }


def product(p: Product) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "sku": p.sku,
        "hsn": p.hsn,
        "unit": p.unit,
        "purchasePrice": p.purchase_price,
        "sellingPrice": p.selling_price,
        "stock": p.stock,
        "lowStockThreshold": p.low_stock_threshold,
        "stockValue": round2(p.stock * p.purchase_price),
        "low": p.stock <= p.low_stock_threshold,
    }


def party(p: Party) -> dict:
    return {
        "id": str(p.id),
        "type": p.type,
        "name": p.name,
        "phone": p.phone,
        "email": p.email,
        "gstNumber": p.gst_number,
        "address": p.address,
        "balance": p.balance,
        "creditDays": p.credit_days,
    }


def expense(e: Expense) -> dict:
    return {
        "id": str(e.id),
        "category": e.category,
        "description": e.description,
        "amount": e.amount,
        "flagged": e.flagged,
        "date": e.date.isoformat(),
    }


def stock_movement(m: StockMovement, product_name: str | None = None) -> dict:
    return {
        "id": str(m.id),
        "productId": str(m.product_id),
        "productName": product_name,
        "delta": m.delta,
        "reason": m.reason,
        "refType": m.ref_type,
        "note": m.note,
        "createdAt": m.created_at.isoformat(),
    }


def notification(n: Notification, source: dict | None = None) -> dict:
    """`source` names the rule and event that raised it, resolved by the caller
    in one query rather than a lookup per row."""
    return {
        "id": str(n.id),
        "type": n.type,
        "severity": n.severity,
        "title": n.title,
        "message": n.message,
        "read": n.read,
        "eventId": str(n.event_id) if n.event_id else None,
        "ruleId": str(n.rule_id) if n.rule_id else None,
        "source": source,
        "createdAt": n.created_at.isoformat(),
    }


def event(e: Event, actor: str | None = None) -> dict:
    """`actor` is the author's name, resolved by the caller in one query rather
    than a lookup per row."""
    return {
        "id": str(e.id),
        "type": e.type,
        "payload": e.payload,
        "status": e.status,
        "retryCount": e.retry_count,
        "error": e.error,
        "actor": actor,
        "createdAt": e.created_at.isoformat(),
        "processedAt": e.processed_at.isoformat() if e.processed_at else None,
    }


def workflow_rule(r: WorkflowRule) -> dict:
    return {
        "id": str(r.id),
        "name": r.name,
        "eventType": r.event_type,
        "conditionField": r.condition_field,
        "conditionOp": r.condition_op,
        "conditionValue": r.condition_value,
        "actionType": r.action_type,
        "actionConfig": r.action_config,
        "enabled": r.enabled,
        "builtIn": r.built_in,
    }


def workflow_execution(x: WorkflowExecution) -> dict:
    return {
        "id": str(x.id),
        "ruleName": x.rule_name,
        "eventType": x.event_type,
        "status": x.status,
        "detail": x.detail,
        "createdAt": x.created_at.isoformat(),
    }

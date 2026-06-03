"""
Payment Routes — Razorpay Integration
======================================
Endpoints:
  GET  /api/payment/plans                  — available plans + pricing
  POST /api/payment/order                  — Razorpay order create karo
  POST /api/payment/verify                 — payment verify + credits add
  POST /api/payment/webhook                — Razorpay webhook (auto credits)
  GET  /api/payment/history                — user ke payment history
  GET  /api/payment/status                 — user ka current plan + credits

Plans:
  starter  — ₹199  → 100 credits
  pro      — ₹499  → 300 credits  (plan upgrade to "pro")
  elite    — ₹999  → 700 credits  (plan upgrade to "pro")
  team     — ₹2999 → unlimited    (plan upgrade to "enterprise")
"""

import os
import hmac
import hashlib
import json
import sqlite3
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel

payment_router = APIRouter(prefix="/api/payment", tags=["payment"])

# ── Config ────────────────────────────────────────────────────────────────────

RAZORPAY_KEY_ID     = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
DB_PATH             = os.getenv("MARKAR_DB_PATH", "markar.db")

# ── Plans — change prices/credits yahan ───────────────────────────────────────

PLANS = {
    "pro": {
        "name":        "pro",
        "price_inr":   100,
        "amount_paise": 10000,       # Razorpay paisa mein leta hai
        "credits":     30,
        "plan_tier":   "free",       # user_limits plan nahi badlega
        "description": "30 credits — small projects ke liye",
        "popular":     False,
    },
    # "pro": {
    #     "name":        "Pro",
    #     "price_inr":   499,
    #     "amount_paise": 49900,
    #     "credits":     300,
    #     "plan_tier":   "pro",        # user ko pro plan milega
    #     "description": "300 credits + Pro limits — serious developers ke liye",
    #     "popular":     True,
    # },
    # "elite": {
    #     "name":        "Elite",
    #     "price_inr":   999,
    #     "amount_paise": 99900,
    #     "credits":     700,
    #     "plan_tier":   "pro",
    #     "description": "700 credits + Pro limits — power users ke liye",
    #     "popular":     False,
    # },
    # "team": {
    #     "name":        "Team",
    #     "price_inr":   2999,
    #     "amount_paise": 299900,
    #     "credits":     0,            # unlimited milega
    #     "plan_tier":   "enterprise",
    #     "description": "Unlimited credits + Enterprise limits — teams ke liye",
    #     "popular":     False,
    #     "unlimited":   True,
    # },
}

# ── DB Init ───────────────────────────────────────────────────────────────────

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_payment_db():
    """Startup pe call karo."""
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS payments (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          TEXT    NOT NULL,
            razorpay_order_id   TEXT UNIQUE,
            razorpay_payment_id TEXT,
            razorpay_signature  TEXT,
            plan_key         TEXT    NOT NULL,
            amount_paise     INTEGER NOT NULL,
            credits_added    INTEGER NOT NULL DEFAULT 0,
            unlimited_granted INTEGER NOT NULL DEFAULT 0,
            status           TEXT    NOT NULL DEFAULT 'created',
            created_at       TEXT    NOT NULL,
            verified_at      TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_payments_user
            ON payments(user_id);
        CREATE INDEX IF NOT EXISTS idx_payments_order
            ON payments(razorpay_order_id);
        """)


def _now() -> str:
    return datetime.utcnow().isoformat()


# ── Auth helper ───────────────────────────────────────────────────────────────

async def _get_user(authorization: Optional[str]):
    from app.core.auth import get_current_user
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Login karo pehle.")
    return user


# ── Razorpay client ───────────────────────────────────────────────────────────

def _razorpay_client():
    try:
        import razorpay
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="razorpay package install nahi hai. Run: pip install razorpay"
        )
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise HTTPException(
            status_code=500,
            detail="RAZORPAY_KEY_ID aur RAZORPAY_KEY_SECRET .env mein set karo."
        )
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

# ── GET /plans ─────────────────────────────────────────────────────────────────

@payment_router.get("/plans", summary="Available plans aur pricing")
async def get_plans():
    """
    Frontend ke liye saare plans return karo.
    Auth ki zaroorat nahi.
    """
    plans_list = []
    for key, plan in PLANS.items():
        plans_list.append({
            "key":         key,
            "name":        plan["name"],
            "price_inr":   plan["price_inr"],
            "credits":     plan["credits"],
            "unlimited":   plan.get("unlimited", False),
            "plan_tier":   plan["plan_tier"],
            "description": plan["description"],
            "popular":     plan.get("popular", False),
        })
    return {
        "status": "success",
        "data": {
            "plans":          plans_list,
            "razorpay_key_id": RAZORPAY_KEY_ID,   # frontend ko chahiye
        }
    }


# ── POST /order ────────────────────────────────────────────────────────────────

class CreateOrderRequest(BaseModel):
    plan_key: str   # "starter" | "pro" | "elite" | "team"


@payment_router.post("/order", summary="Razorpay order create karo")
async def create_order(
    req: CreateOrderRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Frontend pe Razorpay checkout open karne ke liye order_id chahiye.
    Yeh endpoint woh order_id return karta hai.
    """
    user = await _get_user(authorization)

    plan = PLANS.get(req.plan_key)
    if not plan:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid plan '{req.plan_key}'. Valid: {list(PLANS.keys())}"
        )

    client = _razorpay_client()

    # Razorpay order create karo
    try:
        order_data = client.order.create({
            "amount":   plan["amount_paise"],
            "currency": "INR",
            "notes": {
                "user_id":  user.user_id,
                "plan_key": req.plan_key,
                "credits":  str(plan["credits"]),
            }
        })
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Razorpay order failed: {e}")

    order_id = order_data["id"]

    # DB mein save karo — status=created
    with _conn() as conn:
        conn.execute("""
            INSERT INTO payments
                (user_id, razorpay_order_id, plan_key, amount_paise,
                 credits_added, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'created', ?)
        """, (
            user.user_id, order_id, req.plan_key,
            plan["amount_paise"], plan["credits"], _now()
        ))

    return {
        "status": "success",
        "data": {
            "order_id":      order_id,
            "amount_paise":  plan["amount_paise"],
            "amount_inr":    plan["price_inr"],
            "currency":      "INR",
            "plan":          plan["name"],
            "razorpay_key":  RAZORPAY_KEY_ID,
            # Frontend ke liye prefill data
            "prefill": {
                "name":  getattr(user, "full_name", "") or "",
                "email": getattr(user, "email", "") or "",
            }
        }
    }


# ── POST /verify ───────────────────────────────────────────────────────────────

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id:   str
    razorpay_payment_id: str
    razorpay_signature:  str


@payment_router.post("/verify", summary="Payment verify karo aur credits add karo")
async def verify_payment(
    req: VerifyPaymentRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Frontend se payment complete hone ke baad yeh call karo.
    Signature verify hoti hai — tamper-proof.
    Credits + plan auto-update ho jaata hai.
    """
    user = await _get_user(authorization)

    # ── 1. Signature verify karo ──────────────────────────────────────────────
    expected_sig = hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        f"{req.razorpay_order_id}|{req.razorpay_payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, req.razorpay_signature):
        raise HTTPException(status_code=400, detail="Invalid payment signature — tampered!")

    # ── 2. DB mein order dhundho ──────────────────────────────────────────────
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM payments WHERE razorpay_order_id = ?",
            (req.razorpay_order_id,)
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Order nahi mila.")

    payment = dict(row)

    # Already processed? Double credit se bachao
    if payment["status"] == "paid":
        return {
            "status": "success",
            "message": "Payment already processed hai.",
            "data": {"already_done": True}
        }

    # ── 3. Credits + plan update karo ────────────────────────────────────────
    plan     = PLANS[payment["plan_key"]]
    credits  = plan["credits"]
    tier     = plan["plan_tier"]
    is_unlimited = plan.get("unlimited", False)

    from app.core.user_admin import add_credits, set_unlimited, set_user_limits

    if is_unlimited:
        set_unlimited(user.user_id, True, admin_id="razorpay")
    elif credits > 0:
        add_credits(
            user.user_id,
            amount   = credits,
            reason   = f"razorpay:{payment['plan_key']}:{req.razorpay_payment_id}",
            admin_id = "razorpay",
        )

    # Plan tier upgrade karo (free → pro / enterprise)
    if tier != "free":
        set_user_limits(
            user_id    = user.user_id,
            plan       = tier,
            updated_by = "razorpay",
        )

    # ── 4. DB update karo ────────────────────────────────────────────────────
    with _conn() as conn:
        conn.execute("""
            UPDATE payments
            SET razorpay_payment_id = ?,
                razorpay_signature  = ?,
                status              = 'paid',
                unlimited_granted   = ?,
                verified_at         = ?
            WHERE razorpay_order_id = ?
        """, (
            req.razorpay_payment_id,
            req.razorpay_signature,
            1 if is_unlimited else 0,
            _now(),
            req.razorpay_order_id,
        ))

    return {
        "status": "success",
        "message": f"Payment successful! {credits} credits add ho gaye." if not is_unlimited
                   else "Payment successful! Unlimited access activated!",
        "data": {
            "plan":              plan["name"],
            "credits_added":     credits,
            "unlimited":         is_unlimited,
            "plan_upgraded_to":  tier,
        }
    }


# ── POST /webhook ──────────────────────────────────────────────────────────────

@payment_router.post("/webhook", summary="Razorpay webhook — auto payment processing")
async def razorpay_webhook(request: Request):
    """
    Razorpay Dashboard mein webhook URL set karo:
    https://yourdomain.com/api/payment/webhook

    Events handled:
    - payment.captured → credits add karo
    - payment.failed   → status update karo
    """
    body_bytes = await request.body()

    # ── Webhook signature verify karo ────────────────────────────────────────
    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    if webhook_secret:
        received_sig = request.headers.get("x-razorpay-signature", "")
        expected_sig = hmac.new(
            webhook_secret.encode(),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_sig, received_sig):
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        payload = json.loads(body_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event   = payload.get("event", "")
    entity  = payload.get("payload", {}).get("payment", {}).get("entity", {})
    notes   = entity.get("notes", {})

    order_id    = entity.get("order_id", "")
    payment_id  = entity.get("id", "")
    user_id     = notes.get("user_id", "")
    plan_key    = notes.get("plan_key", "")

    if event == "payment.captured":
        # Already verify endpoint se processed? Skip karo
        with _conn() as conn:
            row = conn.execute(
                "SELECT status FROM payments WHERE razorpay_order_id = ?",
                (order_id,)
            ).fetchone()

        if row and dict(row)["status"] == "paid":
            return {"status": "already_processed"}

        # Credits add karo
        if user_id and plan_key and plan_key in PLANS:
            plan         = PLANS[plan_key]
            credits      = plan["credits"]
            tier         = plan["plan_tier"]
            is_unlimited = plan.get("unlimited", False)

            from app.core.user_admin import add_credits, set_unlimited, set_user_limits

            if is_unlimited:
                set_unlimited(user_id, True, admin_id="razorpay_webhook")
            elif credits > 0:
                add_credits(
                    user_id,
                    amount   = credits,
                    reason   = f"razorpay_webhook:{plan_key}:{payment_id}",
                    admin_id = "razorpay_webhook",
                )

            if tier != "free":
                set_user_limits(user_id=user_id, plan=tier, updated_by="razorpay_webhook")

            with _conn() as conn:
                conn.execute("""
                    UPDATE payments
                    SET razorpay_payment_id = ?,
                        status              = 'paid',
                        unlimited_granted   = ?,
                        verified_at         = ?
                    WHERE razorpay_order_id = ?
                """, (payment_id, 1 if is_unlimited else 0, _now(), order_id))

        print(f"[Payment] Webhook: payment.captured — user={user_id} plan={plan_key}")

    elif event == "payment.failed":
        with _conn() as conn:
            conn.execute("""
                UPDATE payments SET status = 'failed'
                WHERE razorpay_order_id = ?
            """, (order_id,))
        print(f"[Payment] Webhook: payment.failed — order={order_id}")

    return {"status": "ok"}


# ── GET /history ───────────────────────────────────────────────────────────────

@payment_router.get("/history", summary="User ke payment history")
async def payment_history(
    authorization: Optional[str] = Header(None),
):
    user = await _get_user(authorization)

    with _conn() as conn:
        rows = conn.execute("""
            SELECT id, plan_key, amount_paise, credits_added,
                   unlimited_granted, status, created_at, verified_at,
                   razorpay_payment_id
            FROM payments
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 20
        """, (user.user_id,)).fetchall()

    payments = []
    for row in rows:
        r = dict(row)
        plan_info = PLANS.get(r["plan_key"], {})
        r["plan_name"]  = plan_info.get("name", r["plan_key"])
        r["amount_inr"] = r["amount_paise"] // 100
        payments.append(r)

    return {"status": "success", "data": payments}


# ── GET /status ────────────────────────────────────────────────────────────────

@payment_router.get("/status", summary="User ka current plan + credits")
async def payment_status(
    authorization: Optional[str] = Header(None),
):
    user = await _get_user(authorization)

    from app.core.user_admin import get_user_credits, get_user_limits

    credits = get_user_credits(user.user_id)
    limits  = get_user_limits(user.user_id)

    # Last successful payment
    with _conn() as conn:
        last = conn.execute("""
            SELECT plan_key, verified_at FROM payments
            WHERE user_id = ? AND status = 'paid'
            ORDER BY verified_at DESC LIMIT 1
        """, (user.user_id,)).fetchone()

    return {
        "status": "success",
        "data": {
            "plan":             limits.get("plan", "free"),
            "credits":          credits.get("credits", 0),
            "unlimited":        bool(credits.get("unlimited", 0)),
            "total_used":       credits.get("total_used", 0),
            "max_repos":        limits.get("max_repos", 3),
            "max_messages_day": limits.get("max_messages_day", 50),
            "last_payment": {
                "plan":        dict(last)["plan_key"] if last else None,
                "verified_at": dict(last)["verified_at"] if last else None,
            }
        }
    }
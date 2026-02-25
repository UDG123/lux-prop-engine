from fastapi import APIRouter, Request

from ai import consult_risk_engine
from db import insert_trade
from market import get_price, get_atr, classify_regime, calculate_levels
from schemas import LuxSignal, TradeResponse

router = APIRouter()


@router.get("/", tags=["Health"])
def health():
    return {"status": "Lux Prop Engine Running"}


@router.post("/webhook/lux", response_model=TradeResponse, tags=["Signals"])
async def webhook(signal: LuxSignal, request: Request):
    pool = request.app.state.pool

    # --- Market data ---
    price = await get_price(signal.symbol)
    atr = await get_atr(signal.symbol)
    regime = classify_regime(atr)
    stop_loss, take_profit = calculate_levels(signal.direction, price, atr)

    # --- AI risk assessment ---
    ai = await consult_risk_engine(
        symbol=signal.symbol,
        direction=signal.direction,
        price=price,
        atr=atr,
        regime=regime,
    )

    # --- Persist ---
    trade = {
        "symbol": signal.symbol,
        "direction": signal.direction,
        "entry": price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "regime": regime,
        "ai_confidence": ai["confidence"],
        "ai_reason": ai["reason"],
    }
    await insert_trade(pool, trade)

    return TradeResponse(status="Trade queued", **trade)

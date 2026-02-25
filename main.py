from fastapi import FastAPI, Request, HTTPException
import os
import asyncpg
import requests
import json

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

pool = None


# ===============================
# STARTUP
# ===============================
@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    print("Database connected")


# ===============================
# MARKET DATA + REGIME ENGINE
# ===============================
def get_price_and_atr(symbol):
    # Normalize FX symbol
    if "/" not in symbol and len(symbol) == 6:
        symbol = symbol[:3] + "/" + symbol[3:]

    if not TWELVEDATA_API_KEY:
        print("TWELVEDATA_API_KEY not set")
        return None, None, None

    # ---- PRICE ----
    price_url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={TWELVEDATA_API_KEY}"
    price_response = requests.get(price_url).json()

    if "price" not in price_response:
        print("PRICE ERROR:", price_response)
        return None, None, None

    price = float(price_response["price"])

    # ---- ATR HISTORY ----
    atr_url = (
        f"https://api.twelvedata.com/atr?"
        f"symbol={symbol}&interval=15min&time_period=14&outputsize=50&apikey={TWELVEDATA_API_KEY}"
    )

    atr_response = requests.get(atr_url).json()

    if "values" not in atr_response:
        print("ATR ERROR:", atr_response)
        return price, None, None

    atr_values = [float(x["atr"]) for x in atr_response["values"]]

    current_atr = atr_values[0]
    sorted_atr = sorted(atr_values)

    percentile = sorted_atr.index(current_atr) / len(sorted_atr)

    if percentile < 0.3:
        regime = "LOW"
    elif percentile < 0.7:
        regime = "NORMAL"
    else:
        regime = "HIGH"

    return price, current_atr, regime


# ===============================
# CLAUDE VALIDATION
# ===============================
def claude_validate_trade(symbol, direction, regime, atr, rr_ratio):
    if not CLAUDE_API_KEY:
        print("CLAUDE_API_KEY not set")
        return {"approved": True, "confidence": 0.5, "reason": "No AI key"}

    headers = {
        "Content-Type": "application/json",
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01"
    }

    prompt = f"""
You are a quantitative trading risk evaluator.

Evaluate this trade objectively.

Symbol: {symbol}
Direction: {direction}
Volatility Regime: {regime}
ATR: {atr}
Risk/Reward: {rr_ratio}

Rules:
- Reject weak RR in high volatility.
- Reject trades in low volatility unless RR is strong.
- Approve trades aligned with volatility regime.
- Return JSON only.

Format:
{{
  "approved": true/false,
  "confidence": 0-1,
  "reason": "short explanation"
}}
"""

    body = {
        "model": "claude-3-haiku-20240307",
        "max_tokens": 200,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=body
    )

    result = response.json()

    try:
        content = result["content"][0]["text"]
        return json.loads(content)
    except:
        print("CLAUDE ERROR:", result)
        return {"approved": True, "confidence": 0.5, "reason": "Fallback"}


# ===============================
# ROOT
# ===============================
@app.get("/")
async def root():
    return {"status": "Lux Prop Engine Running"}


# ===============================
# LUX WEBHOOK
# ===============================
@app.post("/webhook/lux")
async def lux_webhook(request: Request):
    data = await request.json()

    symbol = data.get("symbol")
    direction = data.get("direction")
    bot_name = data.get("bot")

    if not symbol or not direction or not bot_name:
        raise HTTPException(status_code=400, detail="Invalid payload")

    current_price, atr, regime = get_price_and_atr(symbol)

    if not current_price or not atr:
        raise HTTPException(status_code=500, detail="Market data unavailable")

    # ===============================
    # REGIME-BASED RISK ENGINE
    # ===============================
    if regime == "LOW":
        risk_multiplier = 0.9
        rr_ratio = 1.5
    elif regime == "NORMAL":
        risk_multiplier = 1.2
        rr_ratio = 1.8
    else:
        risk_multiplier = 1.5
        rr_ratio = 2.2

    risk_distance = atr * risk_multiplier

    if direction.upper() == "BUY":
        stop_loss = current_price - risk_distance
        take_profit = current_price + (risk_distance * rr_ratio)
    else:
        stop_loss = current_price + risk_distance
        take_profit = current_price - (risk_distance * rr_ratio)

    # ===============================
    # CLAUDE VALIDATION
    # ===============================
    ai_decision = claude_validate_trade(
        symbol=symbol,
        direction=direction.upper(),
        regime=regime,
        atr=atr,
        rr_ratio=rr_ratio
    )

    if not ai_decision.get("approved", False):
        return {
            "status": "Rejected by AI",
            "reason": ai_decision.get("reason"),
            "confidence": ai_decision.get("confidence")
        }

    # ===============================
    # DATABASE INSERT
    # ===============================
    async with pool.acquire() as conn:
        bot = await conn.fetchrow(
            "SELECT id FROM bots WHERE name = $1",
            bot_name
        )

        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")

        await conn.execute(
            """
            INSERT INTO trade_queue
            (bot_id, symbol, direction, entry, stop_loss, take_profit)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            bot["id"],
            symbol,
            direction.upper(),
            current_price,
            stop_loss,
            take_profit
        )

    return {
        "status": "Trade queued",
        "entry": round(current_price, 5),
        "stop_loss": round(stop_loss, 5),
        "take_profit": round(take_profit, 5),
        "atr": round(atr, 6),
        "regime": regime,
        "ai_confidence": ai_decision.get("confidence"),
        "ai_reason": ai_decision.get("reason")
    }

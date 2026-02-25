import os
import requests
import asyncpg
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

# =========================
# ENV VARIABLES
# =========================

DATABASE_URL = os.getenv("DATABASE_URL")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

# =========================
# DATABASE CONNECTION
# =========================

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    print("Database connected")

# =========================
# MODELS
# =========================

class LuxSignal(BaseModel):
    symbol: str
    direction: str
    bot: str

# =========================
# UTILITIES
# =========================

def format_symbol(symbol: str):
    # Convert EURUSD -> EUR/USD
    if "/" not in symbol and len(symbol) == 6:
        return f"{symbol[:3]}/{symbol[3:]}"
    return symbol

def get_current_price(symbol):
    symbol = format_symbol(symbol)

    url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={TWELVEDATA_API_KEY}"
    response = requests.get(url)
    data = response.json()

    print("PRICE RESPONSE:", data)

    if "price" not in data:
        raise HTTPException(status_code=400, detail="Market data unavailable")

    return float(data["price"])

def get_atr(symbol):
    symbol = format_symbol(symbol)

    url = f"https://api.twelvedata.com/atr?symbol={symbol}&interval=15min&time_period=14&apikey={TWELVEDATA_API_KEY}"
    response = requests.get(url)
    data = response.json()

    print("ATR RESPONSE:", data)

    if "values" not in data:
        raise HTTPException(status_code=400, detail="ATR unavailable")

    latest = float(data["values"][0]["atr"])
    return latest

def classify_regime(atr):
    if atr < 0.0003:
        return "LOW"
    elif atr < 0.0006:
        return "MEDIUM"
    else:
        return "HIGH"

# =========================
# CLAUDE AI RISK ENGINE
# =========================

def consult_claude(symbol, direction, price, atr, regime):
    url = "https://api.anthropic.com/v1/messages"

    headers = {
        "Content-Type": "application/json",
        "x-api-key": CLAUDE_API_KEY,  # Correct header
        "anthropic-version": "2023-06-01"
    }

    prompt = f"""
You are a professional prop firm risk committee.

Symbol: {symbol}
Direction: {direction}
Entry Price: {price}
ATR: {atr}
Market Regime: {regime}

Return ONLY JSON like:
{{
    "confidence": 0.0 to 1.0,
    "reason": "short explanation"
}}
"""

    payload = {
        "model": "claude-3-haiku-20240307",
        "max_tokens": 200,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        raw = response.json()

        print("CLAUDE RAW RESPONSE:", raw)

        if "content" not in raw:
            return {
                "confidence": 0.5,
                "reason": "Fallback - Invalid Claude response"
            }

        text = raw["content"][0]["text"]

        parsed = json.loads(text)

        return {
            "confidence": parsed.get("confidence", 0.5),
            "reason": parsed.get("reason", "No reason provided")
        }

    except Exception as e:
        print("CLAUDE ERROR:", e)
        return {
            "confidence": 0.5,
            "reason": "Fallback - Exception"
        }

# =========================
# WEBHOOK
# =========================

@app.post("/webhook/lux")
async def receive_lux_signal(signal: LuxSignal):

    price = get_current_price(signal.symbol)
    atr = get_atr(signal.symbol)
    regime = classify_regime(atr)

    # Basic ATR based SL/TP
    if signal.direction.upper() == "BUY":
        stop_loss = price - (atr * 2)
        take_profit = price + (atr * 4)
    else:
        stop_loss = price + (atr * 2)
        take_profit = price - (atr * 4)

    # Consult Claude
    ai = consult_claude(
        signal.symbol,
        signal.direction,
        price,
        atr,
        regime
    )

    # Store in DB
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO trade_queue(symbol, direction, entry, stop_loss, take_profit, regime, ai_confidence, ai_reason)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8)
        """,
        signal.symbol,
        signal.direction,
        price,
        stop_loss,
        take_profit,
        regime,
        ai["confidence"],
        ai["reason"]
        )

    return {
        "status": "Trade queued",
        "entry": price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "atr": atr,
        "regime": regime,
        "ai_confidence": ai["confidence"],
        "ai_reason": ai["reason"]
    }

# =========================
# HEALTH CHECK
# =========================

@app.get("/")
def health():
    return {"status": "Lux Prop Engine Running"}
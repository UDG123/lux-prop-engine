import os
import requests
import asyncpg
import json
import re
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

# =========================
# ENV VARIABLES
# =========================

DATABASE_URL = os.getenv("DATABASE_URL")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OPENAI_MODEL = "gpt-4o"

print("======================================")
print("🚀 LUX PROP ENGINE STARTING")
print("🔥 USING OPENAI MODEL:", OPENAI_MODEL)
print("======================================")

# =========================
# DATABASE CONNECTION
# =========================

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    print("✅ Database connected")

# =========================
# REQUEST MODEL
# =========================

class LuxSignal(BaseModel):
    symbol: str
    direction: str
    bot: str

# =========================
# HELPERS
# =========================

def format_symbol(symbol: str):
    if "/" not in symbol and len(symbol) == 6:
        return f"{symbol[:3]}/{symbol[3:]}"
    return symbol

def get_current_price(symbol):
    symbol = format_symbol(symbol)
    url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={TWELVEDATA_API_KEY}"
    response = requests.get(url)
    data = response.json()

    if "price" not in data:
        raise HTTPException(status_code=400, detail="Market data unavailable")

    return float(data["price"])

def get_atr(symbol):
    symbol = format_symbol(symbol)
    url = f"https://api.twelvedata.com/atr?symbol={symbol}&interval=15min&time_period=14&apikey={TWELVEDATA_API_KEY}"
    response = requests.get(url)
    data = response.json()

    if "values" not in data:
        raise HTTPException(status_code=400, detail="ATR unavailable")

    return float(data["values"][0]["atr"])

def classify_regime(atr):
    if atr < 0.0003:
        return "LOW"
    elif atr < 0.0006:
        return "MEDIUM"
    else:
        return "HIGH"

# =========================
# OPENAI ENGINE
# =========================

def consult_openai(symbol, direction, price, atr, regime):

    print("🤖 CALLING OPENAI MODEL:", OPENAI_MODEL)

    url = "https://api.openai.com/v1/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }

    prompt = f"""
You are an institutional prop firm risk committee.

Symbol: {symbol}
Direction: {direction}
Entry Price: {price}
ATR: {atr}
Market Regime: {regime}

Return ONLY valid JSON:

{{
  "confidence": number between 0 and 1,
  "reason": "short professional explanation"
}}
"""

    payload = {
        "model": OPENAI_MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "You respond only in valid JSON."},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        raw = response.json()

        print("🧠 OPENAI RAW RESPONSE:", raw)

        content = raw["choices"][0]["message"]["content"]

        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return {
                "confidence": 0.5,
                "reason": "Fallback - JSON not found"
            }

        parsed = json.loads(match.group())

        return {
            "confidence": float(parsed.get("confidence", 0.5)),
            "reason": parsed.get("reason", "No reason provided")
        }

    except Exception as e:
        print("🚨 OPENAI ERROR:", str(e))
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

    if signal.direction.upper() == "BUY":
        stop_loss = price - (atr * 2)
        take_profit = price + (atr * 4)
    else:
        stop_loss = price + (atr * 2)
        take_profit = price - (atr * 4)

    ai = consult_openai(
        signal.symbol,
        signal.direction,
        price,
        atr,
        regime
    )

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO trade_queue(
                symbol,
                direction,
                entry,
                stop_loss,
                take_profit,
                regime,
                ai_confidence,
                ai_reason
            )
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

@app.get("/")
def health():
    return {"status": "Lux Prop Engine Running (OpenAI)"}
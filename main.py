from fastapi import FastAPI, Request, HTTPException
import os
import asyncpg
import requests

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")

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
    # Normalize FX symbols: EURUSD -> EUR/USD
    if "/" not in symbol and len(symbol) == 6:
        symbol = symbol[:3] + "/" + symbol[3:]

    api_key = TWELVEDATA_API_KEY

    if not api_key:
        print("TWELVEDATA_API_KEY not set")
        return None, None, None

    # ---- GET PRICE ----
    price_url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={api_key}"
    price_response = requests.get(price_url).json()

    if "price" not in price_response:
        print("PRICE ERROR:", price_response)
        return None, None, None

    price = float(price_response["price"])

    # ---- GET ATR HISTORY (50 bars, 15min) ----
    atr_url = (
        f"https://api.twelvedata.com/atr?"
        f"symbol={symbol}&interval=15min&time_period=14&outputsize=50&apikey={api_key}"
    )
    atr_response = requests.get(atr_url).json()

    if "values" not in atr_response:
        print("ATR ERROR:", atr_response)
        return price, None, None

    atr_values = [float(x["atr"]) for x in atr_response["values"]]

    current_atr = atr_values[0]
    sorted_atr = sorted(atr_values)

    # Percentile rank
    percentile = sorted_atr.index(current_atr) / len(sorted_atr)

    # ---- REGIME CLASSIFICATION ----
    if percentile < 0.3:
        regime = "LOW"
    elif percentile < 0.7:
        regime = "NORMAL"
    else:
        regime = "HIGH"

    return price, current_atr, regime


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
    # REGIME-AWARE RISK ENGINE
    # ===============================
    if regime == "LOW":
        risk_multiplier = 0.9
        rr_ratio = 1.5
    elif regime == "NORMAL":
        risk_multiplier = 1.2
        rr_ratio = 1.8
    else:  # HIGH volatility
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
            INSERT INTO trade_queue (bot_id, symbol, direction, entry, stop_loss, take_profit)
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
        "regime": regime
    }
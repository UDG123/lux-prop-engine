from fastapi import FastAPI, Request, HTTPException
import os
import asyncpg
import requests

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")
pool = None

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    print("Database connected")

def get_current_price(symbol):
    url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={os.getenv('TWELVEDATA_API_KEY')}"
    response = requests.get(url)
    data = response.json()
    
    if "price" not in data:
        return None
    
    return float(data["price"])

@app.get("/")
async def root():
    return {"status": "Lux Prop Engine Running"}

@app.post("/webhook/lux")
async def lux_webhook(request: Request):
    data = await request.json()

    symbol = data.get("symbol")
    direction = data.get("direction")
    bot_name = data.get("bot")

    if not symbol or not direction or not bot_name:
        raise HTTPException(status_code=400, detail="Invalid payload")

    current_price = get_current_price(symbol)

    if not current_price:
        raise HTTPException(status_code=500, detail="Market data unavailable")

    # TEMP fixed risk distance (we replace with ATR next phase)
    risk_distance = 0.0020

    if direction.upper() == "BUY":
        stop_loss = current_price - risk_distance
        take_profit = current_price + (risk_distance * 1.8)
    else:
        stop_loss = current_price + risk_distance
        take_profit = current_price - (risk_distance * 1.8)

    async with pool.acquire() as conn:
        bot = await conn.fetchrow(
            "SELECT id FROM bots WHERE name = $1", bot_name
        )

        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")

        # Insert into trade_queue
        await conn.execute(
            """
            INSERT INTO trade_queue (bot_id, symbol, direction, entry, stop_loss, take_profit)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            bot["id"],
            symbol,
            direction,
            current_price,
            stop_loss,
            take_profit
        )

    return {
        "status": "Trade queued",
        "entry": current_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit
    }
        )

    return {"status": "Signal logged"}

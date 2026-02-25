from fastapi import FastAPI, Request, HTTPException
import os
import asyncpg

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")
pool = None

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    print("Database connected")

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

    async with pool.acquire() as conn:
        bot = await conn.fetchrow(
            "SELECT id FROM bots WHERE name = $1", bot_name
        )

        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")

        await conn.execute(
            """
            INSERT INTO system_events (bot_id, event_type, description)
            VALUES ($1, $2, $3)
            """,
            bot["id"],
            "Lux Signal Received",
            f"{symbol} {direction}"
        )

    return {"status": "Signal logged"}
import asyncpg


async def init_db(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_queue (
                id          SERIAL PRIMARY KEY,
                symbol      TEXT        NOT NULL,
                direction   TEXT        NOT NULL,
                entry       FLOAT       NOT NULL,
                stop_loss   FLOAT       NOT NULL,
                take_profit FLOAT       NOT NULL,
                regime      TEXT        NOT NULL,
                ai_confidence FLOAT     NOT NULL,
                ai_reason   TEXT        NOT NULL,
                created_at  TIMESTAMP   DEFAULT NOW()
            );
        """)


async def insert_trade(pool: asyncpg.Pool, trade: dict):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO trade_queue (
                symbol, direction, entry, stop_loss, take_profit,
                regime, ai_confidence, ai_reason
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
            trade["symbol"],
            trade["direction"],
            trade["entry"],
            trade["stop_loss"],
            trade["take_profit"],
            trade["regime"],
            trade["ai_confidence"],
            trade["ai_reason"],
        )

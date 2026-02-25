# 🚀 Lux Prop Engine

An institutional-grade trading signal engine built with FastAPI, PostgreSQL, TwelveData, and OpenAI.

---

## Stack

- **FastAPI** — async webhook API
- **PostgreSQL + asyncpg** — trade queue storage
- **TwelveData** — live price and ATR data
- **OpenAI (gpt-4o)** — AI risk confidence scoring

---

## Project Structure

```
lux_prop_engine/
├── main.py          # App entry point, lifespan, pool init
├── config.py        # Env vars via pydantic-settings
├── db.py            # Schema init + insert queries
├── market.py        # TwelveData price/ATR + regime logic
├── ai.py            # OpenAI risk engine
├── schemas.py       # Pydantic request/response models
├── routes.py        # FastAPI endpoints
├── requirements.txt # Dependencies
├── .env.example     # Environment variable template
└── .gitignore
```

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/your-repo/lux_prop_engine.git
cd lux_prop_engine
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in your `.env`:

```
DATABASE_URL=postgresql://user:password@host:5432/dbname
TWELVEDATA_API_KEY=your_twelvedata_key
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4o
```

### 3. Run

```bash
uvicorn main:app --reload
```

---

## Database

The `trade_queue` table is created automatically on startup. To create it manually in Supabase / TablePlus:

```sql
CREATE TABLE IF NOT EXISTS trade_queue (
    id            SERIAL PRIMARY KEY,
    symbol        TEXT      NOT NULL,
    direction     TEXT      NOT NULL,
    entry         FLOAT     NOT NULL,
    stop_loss     FLOAT     NOT NULL,
    take_profit   FLOAT     NOT NULL,
    regime        TEXT      NOT NULL,
    ai_confidence FLOAT     NOT NULL,
    ai_reason     TEXT      NOT NULL,
    created_at    TIMESTAMP DEFAULT NOW()
);
```

---

## API

### `POST /webhook/lux`

Receives a trading signal, fetches live market data, scores it with AI, and queues the trade.

**Request body:**
```json
{
  "symbol": "EURUSD",
  "direction": "BUY",
  "bot": "lux_v1"
}
```

**Response:**
```json
{
  "status": "Trade queued",
  "symbol": "EURUSD",
  "direction": "BUY",
  "entry": 1.0854,
  "stop_loss": 1.0832,
  "take_profit": 1.0898,
  "atr": 0.00111,
  "regime": "HIGH",
  "ai_confidence": 0.78,
  "ai_reason": "Strong momentum with acceptable volatility..."
}
```

### `GET /`

Health check.

---

## Market Regime Classification

| ATR Range | Regime |
|-----------|--------|
| < 0.0003  | LOW    |
| 0.0003 – 0.0006 | MEDIUM |
| > 0.0006  | HIGH   |

---

## Risk Levels

| Direction | Stop Loss | Take Profit |
|-----------|-----------|-------------|
| BUY       | Entry - 2×ATR | Entry + 4×ATR |
| SELL      | Entry + 2×ATR | Entry - 4×ATR |

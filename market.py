import httpx
from fastapi import HTTPException

from config import settings

BASE_URL = "https://api.twelvedata.com"


def _format_symbol(symbol: str) -> str:
    """Ensure forex pairs have a slash: EURUSD -> EUR/USD."""
    if "/" not in symbol and len(symbol) == 6:
        return f"{symbol[:3]}/{symbol[3:]}"
    return symbol


async def get_price(symbol: str) -> float:
    sym = _format_symbol(symbol)
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/price",
            params={"symbol": sym, "apikey": settings.TWELVEDATA_API_KEY},
        )
    data = r.json()
    if "price" not in data:
        raise HTTPException(status_code=400, detail=f"Price unavailable for {sym}: {data}")
    return float(data["price"])


async def get_atr(symbol: str, interval: str = "15min", period: int = 14) -> float:
    sym = _format_symbol(symbol)
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/atr",
            params={
                "symbol": sym,
                "interval": interval,
                "time_period": period,
                "apikey": settings.TWELVEDATA_API_KEY,
            },
        )
    data = r.json()
    if "values" not in data:
        raise HTTPException(status_code=400, detail=f"ATR unavailable for {sym}: {data}")
    return float(data["values"][0]["atr"])


def classify_regime(atr: float) -> str:
    if atr < 0.0003:
        return "LOW"
    elif atr < 0.0006:
        return "MEDIUM"
    return "HIGH"


def calculate_levels(direction: str, price: float, atr: float) -> tuple[float, float]:
    """Returns (stop_loss, take_profit)."""
    if direction.upper() == "BUY":
        return price - (atr * 2), price + (atr * 4)
    return price + (atr * 2), price - (atr * 4)

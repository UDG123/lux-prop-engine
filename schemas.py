from pydantic import BaseModel, field_validator


class LuxSignal(BaseModel):
    symbol: str
    direction: str
    bot: str

    @field_validator("direction")
    @classmethod
    def normalise_direction(cls, v: str) -> str:
        v = v.upper()
        if v not in ("BUY", "SELL"):
            raise ValueError("direction must be BUY or SELL")
        return v

    @field_validator("symbol")
    @classmethod
    def upper_symbol(cls, v: str) -> str:
        return v.upper()


class TradeResponse(BaseModel):
    status: str
    symbol: str
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    atr: float
    regime: str
    ai_confidence: float
    ai_reason: str

import json
import re

import httpx

from config import settings

_FALLBACK = {"confidence": 0.5, "reason": "Fallback - no AI response"}

_SYSTEM_PROMPT = "You are an institutional prop firm risk committee. You only respond in valid JSON."

_USER_PROMPT = """
Symbol: {symbol}
Direction: {direction}
Entry Price: {price}
ATR: {atr}
Market Regime: {regime}

Assess the risk of this trade. Return ONLY valid JSON:

{{
  "confidence": <number 0–1>,
  "reason": "<short professional explanation>"
}}
"""


async def consult_risk_engine(
    symbol: str,
    direction: str,
    price: float,
    atr: float,
    regime: str,
) -> dict:
    payload = {
        "model": settings.OPENAI_MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _USER_PROMPT.format(
                    symbol=symbol,
                    direction=direction,
                    price=price,
                    atr=atr,
                    regime=regime,
                ),
            },
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        raw = r.json()
        content = raw["choices"][0]["message"]["content"]

        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            print("⚠️ OpenAI JSON not found in response")
            return _FALLBACK

        parsed = json.loads(match.group())
        return {
            "confidence": float(parsed.get("confidence", 0.5)),
            "reason": parsed.get("reason", "No reason provided"),
        }

    except Exception as e:
        print(f"🚨 OpenAI error: {e}")
        return _FALLBACK

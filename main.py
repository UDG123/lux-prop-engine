import asyncpg
from contextlib import asynccontextmanager
from fastapi import FastAPI

from config import settings
from routes import router
from db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(settings.DATABASE_URL)
    await init_db(app.state.pool)
    print("✅ Database connected and schema ready")
    yield
    await app.state.pool.close()


app = FastAPI(
    title="Lux Prop Engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)

print("===================================")
print("🚀 LUX PROP ENGINE STARTING")
print(f"🔥 MODEL: {settings.OPENAI_MODEL}")
print("===================================")

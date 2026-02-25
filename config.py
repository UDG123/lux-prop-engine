from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    TWELVEDATA_API_KEY: str
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o"

    class Config:
        env_file = ".env"


settings = Settings()

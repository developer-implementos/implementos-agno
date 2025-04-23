import os
from dotenv import load_dotenv

class Config:
    load_dotenv()
    # AI
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    OPENAI_APIKEY = os.getenv("OPENAI_APIKEY")
    # MONGOS
    MONGO_IA = os.getenv("MONGO_IA")
    # CLICKHOUSE
    CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST")
    CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT"))
    CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER")
    CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD")
    CLICKHOUSE_DATABASE = os.getenv("CLICKHOUSE_DATABASE")
    CLICKHOUSE_SECURE = os.getenv("CLICKHOUSE_SECURE").lower() == "true"
    CLICKHOUSE_VERIFY = os.getenv("CLICKHOUSE_VERIFY").lower() == "true"
    CLICKHOUSE_CONNECT_TIMEOUT = int(os.getenv("CLICKHOUSE_CONNECT_TIMEOUT"))
    CLICKHOUSE_SEND_RECEIVE_TIMEOUT = int(os.getenv("CLICKHOUSE_SEND_RECEIVE_TIMEOUT"))
    # QDRANT
    QDRANT_URL = os.getenv("QDRANT_URL")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
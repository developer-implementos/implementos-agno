from agno.storage.mongodb import MongoDbStorage
from config.config import Config

MongoStorage = MongoDbStorage(
    collection_name="agent_sessions",
    db_name="ia",
    db_url=Config.MONGO_IA,
)
from uuid import uuid4

import pymongo
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

from config.config import Config
from etl.etl_log import log_message

BATCH_SIZE = 100

mongo_cliente = pymongo.MongoClient(Config.MONGO_NUBE)
qdrant_client = QdrantClient(Config.QDRANT_URL, api_key=Config.QDRANT_API_KEY)
openai_client = OpenAI(api_key=Config.OPENAI_API_KEY)

def generate_embedding(text: str) -> list[float]:
    """Genera embeddings para el texto usando la API de OpenAI"""
    response = openai_client.embeddings.create(
        model="text-embedding-ada-002",
        input=text
    )
    return response.data[0].embedding

def process_data() -> list:
    """Procesa la data para retornar 'qdrant_points'"""
    db = mongo_cliente.get_database("Implenet")
    clientes_collection = db.get_collection("clientes")

    query = clientes_collection.find({}, { "_id": 0, "rut": 1, "nombre": 1 })
    data = list(query)

    qdrant_points = []
    for item in data:
        texto_embedding = f"Nombre: {item['nombre']}, RUT: {item['rut']}"

        embedding = generate_embedding(texto_embedding)

        item_point = {
            "id": str(uuid4()),
            "vector": embedding,
            "payload": {
                "rut": item["rut"],
                "nombre": item["nombre"],
            }
        }

        qdrant_points.append(item_point)

    return qdrant_points

def etl_carga_clientes():
    collection_name = "clientes"

    log_message(f"> inicio carga {collection_name}")

    # Recrear la colección en Qdrant
    qdrant_client.delete_collection(collection_name=collection_name)
    qdrant_client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
    )

    # Procesar los datos de cartera objetivo
    qdrant_points = process_data()

    # Cargar datos en Qdrant en lotes
    total_points = len(qdrant_points)

    for i in range(0, total_points, BATCH_SIZE):
        batch = qdrant_points[i:i + BATCH_SIZE]
        qdrant_client.upsert(collection_name=collection_name, points=batch)
        log_message(f"Subidos {i + len(batch)}/{total_points} puntos a Qdrant")

    log_message(f"> fin carga {collection_name}")

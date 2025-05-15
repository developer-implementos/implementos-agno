from uuid import uuid4

import pymongo
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
import clickhouse_connect

from config.config import Config
from etl.etl_log import log_message
from databases.clickhouse_client import config

BATCH_SIZE = 100

mongo_cliente = pymongo.MongoClient(Config.MONGO_NUBE)
qdrant_client = QdrantClient(Config.QDRANT_URL, api_key=Config.QDRANT_API_KEY)
openai_client = OpenAI(api_key=Config.OPENAI_API_KEY)


def create_clickhouse_client():
    """Crea y devuelve un cliente de ClickHouse utilizando la configuración"""
    client_config = config.get_client_config()
    try:
        client = clickhouse_connect.get_client(**client_config)
        # Probar la conexión
        version = client.server_version
        return client
    except Exception as e:
        raise

def execute_query(query: str):
    """Ejecuta una consulta en ClickHouse y devuelve los resultados"""
    try:
        client = create_clickhouse_client()
        res = client.query(query, settings={"readonly": 1})
        column_names = res.column_names
        rows = []
        for row in res.result_rows:
            row_dict = {}
            for i, col_name in enumerate(column_names):
                row_dict[col_name] = row[i]
            rows.append(row_dict)
        return rows
    except Exception as err:
        return []

def generate_embedding(text: str) -> list[float]:
    """Genera embeddings para el texto usando la API de OpenAI"""
    response = openai_client.embeddings.create(
        model="text-embedding-ada-002",
        input=text
    )
    return response.data[0].embedding

def process_data() -> list:
    """Procesa la data para retornar 'qdrant_points'"""
    sql = f"SELECT codigo, descripcion FROM implementos.canal_venta"
    data = execute_query(sql)

    qdrant_points = []
    for item in data:
        texto_embedding = f"Descripción: {item['descripcion']}, Código: {item['codigo']}"

        embedding = generate_embedding(texto_embedding)

        item_point = {
            "id": str(uuid4()),
            "vector": embedding,
            "payload": {
                "codigo": item["codigo"],
                "descripcion": item["descripcion"],
            }
        }

        qdrant_points.append(item_point)

    return qdrant_points

def etl_carga_canales_venta():
    collection_name = "canales_venta"

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
        print(f"Subidos {i + len(batch)}/{total_points} puntos a Qdrant")

    log_message(f"> fin carga {collection_name}")

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
    data = [
        {"nombre": "ALTO HOSPICIO", "codigo": "ALT HOSPIC"},
        {"nombre": "ANTOFAGASTA", "codigo": "ANTOFGASTA"},
        {"nombre": "ARICA", "codigo": "ARICA"},
        {"nombre": "CALAMA", "codigo": "CALAMA"},
        {"nombre": "CASTRO", "codigo": "CASTRO"},
        {"nombre": "CHILLAN", "codigo": "CHILLAN"},
        {"nombre": "CON CON", "codigo": "CON CON"},
        {"nombre": "CONCEPCION", "codigo": "CONCEPCION"},
        {"nombre": "COPIAPO", "codigo": "COPIAPO"},
        {"nombre": "COQUIMBO", "codigo": "COQUIMBO"},
        {"nombre": "CORONEL", "codigo": "CORONEL"},
        {"nombre": "CURICO", "codigo": "CURICO"},
        {"nombre": "ESTACION CENTRAL", "codigo": "EST CNTRAL"},
        {"nombre": "IQUIQUE", "codigo": "IQUIQUE"},
        {"nombre": "LAMPA", "codigo": "LAMPA"},
        {"nombre": "LINARES", "codigo": "LINARES"},
        {"nombre": "LOS ANGELES", "codigo": "LS ANGELES"},
        {"nombre": "MELIPILLA", "codigo": "MELIPILLA"},
        {"nombre": "OSORNO", "codigo": "OSORNO"},
        {"nombre": "PUERTO MONTT", "codigo": "P MONTT2"},
        {"nombre": "PLACILLA", "codigo": "PLACILLA"},
        {"nombre": "PUNTA ARENAS", "codigo": "PTA ARENAS"},
        {"nombre": "RANCAGUA", "codigo": "RANCAGUA 2"},
        {"nombre": "SAN BERNARDO", "codigo": "SAN BRNRDO"},
        {"nombre": "SAN FERNANDO", "codigo": "SAN FERNAN"},
        {"nombre": "TALCA", "codigo": "TALCA"},
        {"nombre": "TEMUCO", "codigo": "TEMUCO"},
        {"nombre": "VALDIVIA", "codigo": "VALDIVIA"},
        {"nombre": "COLINA", "codigo": "COLINA"},
        {"nombre": "TALCAHUANO", "codigo": "TALCAHUANO"},
    ]

    qdrant_points = []
    for item in data:
        texto_embedding = f"Nombre: {item['nombre']} Código: {item['codigo']}"

        embedding = generate_embedding(texto_embedding)

        item_point = {
            "id": str(uuid4()),
            "vector": embedding,
            "payload": {
                "nombre": item["nombre"],
                "codigo": item["codigo"],
            }
        }

        qdrant_points.append(item_point)

    return qdrant_points

def etl_carga_sucursales():
    collection_name = "sucursales"

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

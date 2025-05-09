from datetime import datetime, timedelta, timezone

import pymongo
import jwt

from config.config import Config

def capitalizar_string(texto: str) -> str:
    """Capitaliza un string (primera letra de cada palabra en mayúscula)"""
    if not texto:
        return ""
    return " ".join(palabra.capitalize() for palabra in texto.split())

def obtener_token_omni_vendedor(cod_vendedor: int) -> str:
    mongo_cliente = pymongo.MongoClient(Config.MONGO_NUBE)

    db = mongo_cliente.get_database("Implenet")
    usuarios_ax_collection = db["usuariosAX"]

    usuario = usuarios_ax_collection.find_one({"codEmpleado": cod_vendedor})
    if usuario is None:
        raise ValueError(f"Usuario {cod_vendedor} no existe")

    payload = {
        "codUsuario": usuario["codUsuario"],
        "codEmpleado": usuario["codEmpleado"],
        "usuario": usuario["usuario"],
        "nombre": capitalizar_string(usuario["nombre"]),
        "codSucursal": usuario["codSucursal"],
        "rut": usuario["rut"],
        "codBodega": usuario["codBodega"],
        "codPerfil": usuario["codPerfil"],
        "nombreSucursal": usuario["codSucursal"],
        "email": usuario["email"],
        "movil": usuario["movil"],
        "bodegas": [usuario["codBodega"]] if usuario.get("codBodega") else [],
    }

    options = {
        "exp": datetime.now(timezone.utc) + timedelta(hours=48)
    }

    jwt_secret = Config.JWT_SECRET
    token = jwt.encode({ **payload, **options }, jwt_secret, algorithm="HS256")

    return token

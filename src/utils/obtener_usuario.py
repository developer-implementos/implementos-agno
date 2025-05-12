from datetime import datetime, timedelta, timezone

import pymongo

from config.config import Config
from models.usuario_model import UsuarioAX


def capitalizar_string(texto: str) -> str:
    """Capitaliza un string (primera letra de cada palabra en mayúscula)"""
    if not texto:
        return ""
    return " ".join(palabra.capitalize() for palabra in texto.split())

def obtener_usuario(cod_vendedor: int) -> UsuarioAX:
    mongo_cliente = pymongo.MongoClient(Config.MONGO_NUBE)

    db = mongo_cliente.get_database("Implenet")
    usuarios_ax_collection = db["usuariosAX"]

    usuario = usuarios_ax_collection.find_one({"codEmpleado": cod_vendedor})
    if usuario is None:
        raise ValueError(f"Usuario {cod_vendedor} no existe")

    usuario_ax = UsuarioAX(
        codUsuario=usuario["codUsuario"],
        codEmpleado=usuario["codEmpleado"],
        usuario=usuario["usuario"].lower(),
        nombre=capitalizar_string(usuario["nombre"]),
        codSucursal=usuario["codSucursal"],
        rut=usuario["rut"],
        codBodega=usuario["codBodega"],
        codPerfil=usuario["codPerfil"],
        nombreSucursal=usuario["codSucursal"],
        email=usuario["email"],
        movil=usuario["movil"],
        bodegas=[usuario["codBodega"]] if usuario.get("codBodega") else [],
        vendedorRecid=usuario["vendedorRecid"],
    )

    return usuario_ax

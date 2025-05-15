from typing import Optional

import pymongo
import json

from config.config import Config


def obtener_bodega_vendedor(cod_empleado: int, tienda: Optional[str] = None) -> dict[str, str]:
    """
    Obtiene la bodega asociada al vendedor

    Args:
        cod_empleado (int): Código del empleado
        tienda (Optional[str]): Tienda específica (opcional)

    Returns:
        Dict[str, str]: Información de la bodega
    """
    try:
        # Establecer conexión a MongoDB
        mongo_cliente = pymongo.MongoClient(Config.MONGO_NUBE)
        db = mongo_cliente.get_database("Implenet")  # Usar la base de datos configurada
        seguridad_sucursal_omni = db["seguridad_sucursales_omni"]

        cod_bodega = ""
        sucursal = ""

        # Por la tienda
        if tienda:
            query = {
                "$and": [
                    {"permisosUser": cod_empleado},
                    {"$or": [{"codigo": tienda}, {"nombre": tienda}]}
                ]
            }
            projection = {"codigo": 1, "nombre": 1, "_id": 0}

            item = seguridad_sucursal_omni.find_one(query, projection)

            if item:
                cod_bodega = item.get("codigo", "")
                sucursal = item.get("nombre", "")

        # Predeterminada
        if not cod_bodega:
            bodega_defecto = obtener_bodega_defecto_vendedor(cod_empleado)

            cod_bodega = bodega_defecto.get("codBodega", "")
            sucursal = bodega_defecto.get("sucursal", "")

        # La primera encontrada
        if not cod_bodega:
            query = {
                "$and": [
                    {"permisosUser": cod_empleado},
                    {"codigo": {"$ne": "CDD-CD1"}},
                    {"habilitado": True}
                ]
            }
            projection = {"codigo": 1, "nombre": 1, "_id": 0}

            item = seguridad_sucursal_omni.find_one(query, projection)

            if item:
                cod_bodega = item.get("codigo", "")
                sucursal = item.get("nombre", "")

        return {"codBodega": cod_bodega, "sucursal": sucursal}

    except Exception as e:
        return {"codBodega": "", "sucursal": ""}


def obtener_bodega_defecto_vendedor(cod_empleado: int) -> dict[str, str]:
    """
    Obtiene la bodega predeterminada para un vendedor

    Args:
        cod_empleado (int): Código del empleado

    Returns:
        Dict[str, str]: Información de la bodega predeterminada
    """
    try:
        # Establecer conexión a MongoDB
        mongo_cliente = pymongo.MongoClient(Config.MONGO_NUBE)
        db = mongo_cliente.get_database("Implenet")
        seguridad_sucursal_omni = db["seguridad_sucursales_omni"]

        # Buscar sucursal predeterminada para el empleado
        query = {
            "predeterminada": cod_empleado,
            "habilitado": True
        }
        projection = {"codigo": 1, "nombre": 1, "_id": 0}

        item = seguridad_sucursal_omni.find_one(query, projection)

        if item:
            return {"codBodega": item.get("codigo", ""), "sucursal": item.get("nombre", "")}

        return {"codBodega": "", "sucursal": ""}

    except Exception as e:
        return {"codBodega": "", "sucursal": ""}

import json
from datetime import datetime, timezone
from typing import Optional, List, Dict

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Query, Depends
import httpx
from pydantic import BaseModel, Field
from pymongo import MongoClient

from config.config import Config

_agents_cache = None
async def get_agents() -> List:
    global _agents_cache

    if _agents_cache is not None:
        return _agents_cache

    async with httpx.AsyncClient() as client:
        respuesta = await client.get("http://localhost:7777/v1/playground/agents")
    api_agent_data = respuesta.json()

    agent_data = [
        {
            "agent_id": item["agent_id"],
            "agent_name": item["name"],
            "agent_description": item["description"],
            "model_name": item["model"]["name"],
            "model_id": item["model"]["model"],
        } for item in api_agent_data
        if "cristian_sepulveda" not in item["agent_id"]
    ]

    _agents_cache = agent_data
    return agent_data

class DateAgentFilter(BaseModel):
    fecha_desde: Optional[datetime] = Field(None, description="Fecha inicial en formato ISO")
    fecha_hasta: Optional[datetime] = Field(None, description="Fecha final en formato ISO")
    agent_ids: Optional[List[str]] = Field(None, description="Lista de IDs de agentes")

async def get_filter_params(
    fecha_desde: Optional[str] = Query(None, description="Fecha inicial en formato ISO"),
    fecha_hasta: Optional[str] = Query(None, description="Fecha final en formato ISO"),
    agent_ids: Optional[List[str]] = Query(None, alias="agent_ids[]", description="Lista de IDs de agentes")
) -> DateAgentFilter:

    # Fecha por defecto
    now = datetime.now(timezone.utc)
    fecha_hasta_dt = datetime.fromisoformat(fecha_hasta) if fecha_hasta else now

    # Si no se especifica fecha_desde, usar 3 meses atrás
    if not fecha_desde:
        fecha_desde_dt = now - relativedelta(months=3)
    else:
        fecha_desde_dt = datetime.fromisoformat(fecha_desde)

    return DateAgentFilter(
        fecha_desde=fecha_desde_dt,
        fecha_hasta=fecha_hasta_dt,
        agent_ids=agent_ids
    )

def create_mongo_filter(param: DateAgentFilter):
    """ Crea el filtro de MongoDB"""
    filter_dict = {}

    # Filtro fechas
    if param.fecha_desde or param.fecha_hasta:
        date_filter = {}
        if param.fecha_desde:
            unix_timestamp_desde = int(param.fecha_desde.timestamp())
            date_filter["$gte"] = unix_timestamp_desde
        if param.fecha_hasta:
            unix_timestamp_hasta = int(param.fecha_hasta.timestamp())
            date_filter["$lte"] = unix_timestamp_hasta
        filter_dict["created_at"] = date_filter

    # Filtro de agentes
    if param.agent_ids:
        filter_dict["agent_id"] = {"$in": param.agent_ids}

    return filter_dict

def genera_rango_dias(fecha_desde: datetime, fecha_hasta: datetime) -> List[str]:
    """
        Genera un rango de dias de un periodo te tiempo
        Ejemplo: ["2025-01-01", "2025-02-01", ...]
    """
    all_dates = []
    current_date = fecha_desde
    while current_date <= fecha_hasta:
        all_dates.append(current_date.strftime("%Y-%m-%d"))
        current_date = current_date + relativedelta(days=1)

    return all_dates

def genera_rango_franjas_horarias() -> List[str]:
    """
    Genera un rango de franjas horarias de 30 minutos
    Ejemplo: ["00:00", "00:30", "01:00", "01:30", ...]
    """
    franjas = []
    for hora in range(24):
        for minuto in [0, 30]:
            franja = f"{hora:02d}:{minuto:02d}"
            franjas.append(franja)
    return franjas

def get_user_names_dict(user_ids: List[str]) -> Dict[str, str]:
    """
        Obtiene un diccionario con este formato: [user_id]: [user_name]
    """
    user_names_dict = {}

    client = MongoClient(Config.MONGO_NUBE)
    db = client.get_default_database()
    clientes_collection = db["clientes"]
    usuarios_ax_collection = db["usuariosAX"]

    ids_numericos = {user_id for user_id in user_ids if user_id is not None and user_id.isdigit()}

    ids_cortos = {int(id) for id in ids_numericos if len(id) < 5}
    ids_largos = {id for id in ids_numericos if len(id) >= 5}

    telefonos_con_mas = {f"+{id}" for id in ids_largos}

    usuarios = usuarios_ax_collection.find(
        { "codEmpleado": { "$in": list(ids_cortos) } },
        { "_id": 0, "rutEmp": 1, "nombre": 1, "codEmpleado": 1 }
    ).to_list(length=None)

    for usuario in usuarios:
        user_names_dict[str(usuario["codEmpleado"])] = usuario["nombre"].upper() + " (" + usuario["rutEmp"] + ")"

    clientes = clientes_collection.find(
        {"contactos.telefono": {"$in": list(telefonos_con_mas)}},
        { "_id": 0, "rut": 1, "nombre": 1, "contactos.telefono": 1 }
    ).sort("recid", -1).to_list(length=None)

    for cliente in clientes:
        # Extraer todos los teléfonos del cliente
        if "contactos" in cliente and isinstance(cliente["contactos"], list):
            for contacto in cliente["contactos"]:
                if "telefono" in contacto:
                    telefono = contacto["telefono"]
                    # Quitar el "+" para match con el user_id
                    user_id = telefono[1:] if telefono.startswith("+") else telefono
                    if user_id in ids_largos:
                        user_names_dict[user_id] = cliente["nombre"].upper() + " (" + cliente["rut"] + ")"

    return user_names_dict

report_router = APIRouter(prefix="/report", tags=["report"])

@report_router.get("/agents")
async def get_report_agents():
    agents = await get_agents()
    return agents

@report_router.get("/conversaciones-por-dia")
async def get_conversaciones_por_dia(params: DateAgentFilter = Depends(get_filter_params)):
    """
        Obtiene la cantidad de conversaciones al día (Total y por agente)
    """
    client = MongoClient(Config.MONGO_IA)
    db = client.get_default_database()
    agent_sessions_collection = db["agent_sessions"]

    agents = await get_agents()
    if params.agent_ids is None:
        params.agent_ids = [item["agent_id"] for item in agents]
    else:
        filtered_agents = [item for item in agents if item["agent_id"] in params.agent_ids]
        agents = filtered_agents

    # Mongo
    mongo_filter = create_mongo_filter(params)
    result = agent_sessions_collection.aggregate([
        { "$match": mongo_filter },
        {
            "$group": {
                "_id": {
                    "agent_id": "$agent_id",
                    "fecha": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": { "$toDate": { "$multiply": ["$created_at", 1000] } }
                        }
                    }
                },
                "agent_name": { "$first": "$agent_data.name" },
                "cantidad": { "$sum": 1 }
            }
        },
        {
            "$project": {
                "_id": 0,
                "agent_id": "$_id.agent_id",
                "fecha": "$_id.fecha",
                "agent_name": 1,
                "cantidad": 1
            }
        },
        {"$sort": {"agent_id": 1, "fecha": 1}}
    ]).to_list(length=None)

    # Formatea resultado
    all_dates = genera_rango_dias(params.fecha_desde, params.fecha_hasta)

    agent_names = {}
    data_by_agent = {}
    total_by_date = {date: 0 for date in all_dates}

    for item in result:
        agent_id = item["agent_id"]
        agent_name = item["agent_name"]
        fecha = item["fecha"]
        cantidad = item["cantidad"]

        agent_names[agent_id] = agent_name

        if agent_name not in data_by_agent:
            data_by_agent[agent_name] = {date: 0 for date in all_dates}

        data_by_agent[agent_name][fecha] = cantidad

        if fecha in total_by_date:
            total_by_date[fecha] += cantidad

    # Convertir el diccionario a la estructura requerida
    agentes = {}
    for agent_name, date_values in data_by_agent.items():
        valores = [date_values[date] for date in all_dates]
        agentes[agent_name] = valores

    # Añadir el total
    agentes["Total"] = [total_by_date[date] for date in all_dates]

    # Resultado final
    return {
        "fechas": all_dates,
        "agentes": agentes
    }

@report_router.get("/usuarios-activos-por-dia")
async def get_usuarios_activos_por_dia(params: DateAgentFilter = Depends(get_filter_params)):
    """
    Obtiene la cantidad de usuarios activos al día (Total y por agente)
    """
    client = MongoClient(Config.MONGO_IA)
    db = client.get_default_database()
    agent_sessions_collection = db["agent_sessions"]

    agents = await get_agents()
    if params.agent_ids is None:
        params.agent_ids = [item["agent_id"] for item in agents]
    else:
        filtered_agents = [item for item in agents if item["agent_id"] in params.agent_ids]
        agents = filtered_agents

    # Mongo query - contar usuarios ÚNICOS por día y por agente
    mongo_filter = create_mongo_filter(params)
    result = agent_sessions_collection.aggregate([
        {"$match": mongo_filter},
        {
            "$group": {
                "_id": {
                    "agent_id": "$agent_id",
                    "fecha": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": {"$toDate": {"$multiply": ["$created_at", 1000]}}
                        }
                    },
                    "user_id": "$user_id"  # Agrupamos también por user_id para contarlos después
                },
                "agent_name": {"$first": "$agent_data.name"}
            }
        },
        {
            # Segundo nivel de agrupación: solo por agente y fecha
            "$group": {
                "_id": {
                    "agent_id": "$_id.agent_id",
                    "fecha": "$_id.fecha"
                },
                "agent_name": {"$first": "$agent_name"},
                "cantidad_usuarios": {"$sum": 1}  # Cuenta usuarios únicos
            }
        },
        {
            "$project": {
                "_id": 0,
                "agent_id": "$_id.agent_id",
                "fecha": "$_id.fecha",
                "agent_name": 1,
                "cantidad": "$cantidad_usuarios"
            }
        },
        {"$sort": {"agent_id": 1, "fecha": 1}}
    ]).to_list(length=None)

    # Formatea resultado
    all_dates = genera_rango_dias(params.fecha_desde, params.fecha_hasta)

    agent_names = {}
    data_by_agent = {}
    total_by_date = {date: 0 for date in all_dates}

    for item in result:
        agent_id = item["agent_id"]
        agent_name = item["agent_name"]
        fecha = item["fecha"]
        cantidad = item["cantidad"]

        agent_names[agent_id] = agent_name

        if agent_name not in data_by_agent:
            data_by_agent[agent_name] = {date: 0 for date in all_dates}

        data_by_agent[agent_name][fecha] = cantidad

        if fecha in total_by_date:
            total_by_date[fecha] += cantidad

    # Convertir el diccionario a la estructura requerida
    agentes = {}
    for agent_name, date_values in data_by_agent.items():
        valores = [date_values[date] for date in all_dates]
        agentes[agent_name] = valores

    # Añadir el total
    agentes["Total"] = [total_by_date[date] for date in all_dates]

    # Resultado final
    return {
        "fechas": all_dates,
        "agentes": agentes
    }

@report_router.get("/mensajes-por-dia")
async def get_mensajes_por_dia(params: DateAgentFilter = Depends(get_filter_params)):
    """
    Obtiene la cantidad de mensajes al día (Total y por agente)
    """
    client = MongoClient(Config.MONGO_IA)
    db = client.get_default_database()
    agent_sessions_collection = db["agent_sessions"]

    agents = await get_agents()
    if params.agent_ids is None:
        params.agent_ids = [item["agent_id"] for item in agents]
    else:
        filtered_agents = [item for item in agents if item["agent_id"] in params.agent_ids]
        agents = filtered_agents

    # Mongo query - contar mensajes por día y por agente
    mongo_filter = create_mongo_filter(params)
    result = agent_sessions_collection.aggregate([
        {"$match": mongo_filter},
        {
            "$group": {
                "_id": {
                    "agent_id": "$agent_id",
                    "fecha": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": {"$toDate": {"$multiply": ["$created_at", 1000]}}
                        }
                    }
                },
                "agent_name": {"$first": "$agent_data.name"},
                "cantidad": {"$sum": {"$size": "$memory.runs"}}  # Sumar total de mensajes (asumiendo que runs contiene los mensajes)
            }
        },
        {
            "$project": {
                "_id": 0,
                "agent_id": "$_id.agent_id",
                "fecha": "$_id.fecha",
                "agent_name": 1,
                "cantidad": 1
            }
        },
        {"$sort": {"agent_id": 1, "fecha": 1}}
    ]).to_list(length=None)

    # Formatea resultado (mismo formato que conversaciones-por-dia)
    all_dates = genera_rango_dias(params.fecha_desde, params.fecha_hasta)

    agent_names = {}
    data_by_agent = {}
    total_by_date = {date: 0 for date in all_dates}

    for item in result:
        agent_id = item["agent_id"]
        agent_name = item["agent_name"]
        fecha = item["fecha"]
        cantidad = item["cantidad"]

        agent_names[agent_id] = agent_name

        if agent_name not in data_by_agent:
            data_by_agent[agent_name] = {date: 0 for date in all_dates}

        data_by_agent[agent_name][fecha] = cantidad

        if fecha in total_by_date:
            total_by_date[fecha] += cantidad

    # Convertir el diccionario a la estructura requerida
    agentes = {}
    for agent_name, date_values in data_by_agent.items():
        valores = [date_values[date] for date in all_dates]
        agentes[agent_name] = valores

    # Añadir el total
    agentes["Total"] = [total_by_date[date] for date in all_dates]

    # Resultado final
    return {
        "fechas": all_dates,
        "agentes": agentes
    }


@report_router.get("/resumen-uso-agente-usuario")
async def get_resumen_uso_agente_usuario(params: DateAgentFilter = Depends(get_filter_params)):
    """
    Resumen desglosado por tupla Agente-Usuario mostrando:
    - Cantidad de conversaciones
    - Cantidad de mensajes
    - Fecha primera conversación
    - Fecha última conversación
    - Promedio mensajes al día
    """
    client = MongoClient(Config.MONGO_IA)
    db = client.get_default_database()
    agent_sessions_collection = db["agent_sessions"]

    agents = await get_agents()
    if params.agent_ids is None:
        params.agent_ids = [item["agent_id"] for item in agents]
    else:
        filtered_agents = [item for item in agents if item["agent_id"] in params.agent_ids]
        agents = filtered_agents

    # Mongo query - agrupar por agente Y usuario
    mongo_filter = create_mongo_filter(params)
    result = agent_sessions_collection.aggregate([
        {"$match": mongo_filter},
        {
            "$group": {
                "_id": {
                    "agent_id": "$agent_id",
                    "user_id": "$user_id"
                },
                "agent_name": {"$first": "$agent_data.name"},
                "conversaciones": {"$sum": 1},
                "mensajes": {"$sum": {"$size": "$memory.runs"}},
                "primera_conversacion": {"$min": "$created_at"},
                "ultima_conversacion": {"$max": "$created_at"}
            }
        },
        {
            "$project": {
                "_id": 0,
                "agent_id": "$_id.agent_id",
                "agent_name": 1,
                "user_id": "$_id.user_id",
                "conversaciones": 1,
                "mensajes": 1,
                "primera_conversacion": {"$toDate": {"$multiply": ["$primera_conversacion", 1000]}},
                "ultima_conversacion": {"$toDate": {"$multiply": ["$ultima_conversacion", 1000]}},
                "dias_entre_conversacion": {
                    "$ceil": {
                        "$divide": [
                            {"$subtract": ["$ultima_conversacion", "$primera_conversacion"]},
                            86400  # Segundos en un día
                        ]
                    }
                }
            }
        },
        {
            "$addFields": {
                "promedio_mensajes_dia": {
                    "$cond": [
                        {"$gt": ["$dias_entre_conversacion", 0]},
                        {"$divide": ["$mensajes", "$dias_entre_conversacion"]},
                        "$mensajes"  # Si es el mismo día, el promedio son todos los mensajes
                    ]
                }
            }
        },
        {"$sort": {"agent_id": 1, "conversaciones": -1}}
    ]).to_list(length=None)

    # Formatear fechas a ISO UTC
    for item in result:
        item["primera_conversacion"] = item["primera_conversacion"].strftime("%Y-%m-%dT%H:%M:%SZ")
        item["ultima_conversacion"] = item["ultima_conversacion"].strftime("%Y-%m-%dT%H:%M:%SZ")
        # Redondear promedio a 2 decimales
        item["promedio_mensajes_dia"] = round(item["promedio_mensajes_dia"], 2)

    # Cálculo para totales agregados (por agente)
    totales_por_agente = {}
    for item in result:
        agent_id = item["agent_id"]
        if agent_id not in totales_por_agente:
            totales_por_agente[agent_id] = {
                "agent_id": agent_id,
                "agent_name": item["agent_name"],
                "user_id": "TOTAL",
                "conversaciones": 0,
                "mensajes": 0,
                "primera_conversacion": item["primera_conversacion"],
                "ultima_conversacion": item["ultima_conversacion"],
                "promedio_mensajes_dia": 0,
                "usuarios_atendidos": 0
            }

        totales_por_agente[agent_id]["conversaciones"] += item["conversaciones"]
        totales_por_agente[agent_id]["mensajes"] += item["mensajes"]
        totales_por_agente[agent_id]["usuarios_atendidos"] += 1

        # Actualizar primera conversación si es anterior
        if item["primera_conversacion"] < totales_por_agente[agent_id]["primera_conversacion"]:
            totales_por_agente[agent_id]["primera_conversacion"] = item["primera_conversacion"]

        # Actualizar última conversación si es posterior
        if item["ultima_conversacion"] > totales_por_agente[agent_id]["ultima_conversacion"]:
            totales_por_agente[agent_id]["ultima_conversacion"] = item["ultima_conversacion"]

    # Añadir totales por agente
    for agent_total in totales_por_agente.values():
        # Recalcular promedio para el total del agente
        dias_entre_conversacion = (datetime.fromisoformat(agent_total["ultima_conversacion"].replace("Z", "+00:00")) -
                         datetime.fromisoformat(agent_total["primera_conversacion"].replace("Z", "+00:00"))).days + 1
        if dias_entre_conversacion > 0:
            agent_total["promedio_mensajes_dia"] = round(agent_total["mensajes"] / dias_entre_conversacion, 2)
        else:
            agent_total["promedio_mensajes_dia"] = agent_total["mensajes"]

        result.append(agent_total)

    # Calcular gran total (todos los agentes)
    if result:
        gran_total = {
            "agent_id": "TOTAL",
            "agent_name": "TODOS LOS AGENTES",
            "user_id": "TOTAL",
            "conversaciones": sum(item["conversaciones"] for item in result if item["user_id"] != "TOTAL"),
            "mensajes": sum(item["mensajes"] for item in result if item["user_id"] != "TOTAL"),
            "usuarios_atendidos": len(set(item["user_id"] for item in result if item["user_id"] != "TOTAL"))
        }

        # Encontrar primera y última conversación global
        todas_primeras = [datetime.fromisoformat(item["primera_conversacion"].replace("Z", "+00:00"))
                         for item in result if item["user_id"] != "TOTAL"]
        todas_ultimas = [datetime.fromisoformat(item["ultima_conversacion"].replace("Z", "+00:00"))
                        for item in result if item["user_id"] != "TOTAL"]

        if todas_primeras and todas_ultimas:
            gran_total["primera_conversacion"] = min(todas_primeras).strftime("%Y-%m-%dT%H:%M:%SZ")
            gran_total["ultima_conversacion"] = max(todas_ultimas).strftime("%Y-%m-%dT%H:%M:%SZ")

            dias_entre_conversacion = (max(todas_ultimas) - min(todas_primeras)).days + 1
            if dias_entre_conversacion > 0:
                gran_total["promedio_mensajes_dia"] = round(gran_total["mensajes"] / dias_entre_conversacion, 2)
            else:
                gran_total["promedio_mensajes_dia"] = gran_total["mensajes"]

            result.append(gran_total)


    # Obtener diccionario de nombres de usuarios
    user_ids = [item["user_id"] for item in result if item["user_id"] != "TOTAL"]
    user_names = get_user_names_dict(user_ids)
    for item in result:
        if item["user_id"] != "TOTAL":
            item["user_name"] = user_names.get(item["user_id"], "Usuario Desconocido")
        else:
            item["user_name"] = "TOTAL"

    # Retornar tabla formateada
    return {
        "resumen": result,
        "periodo": {
            "fecha_desde": params.fecha_desde.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fecha_hasta": params.fecha_hasta.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
    }


@report_router.get("/listado-conversaciones")
async def get_listado_conversaciones(
    params: DateAgentFilter = Depends(get_filter_params),
    skip: int = Query(0, description="Número de registros a saltar (paginación)"),
    limit: int = Query(20, description="Número máximo de registros a retornar")
):
    """
    Listado de conversaciones: Título, Usuario, Cantidad mensajes, F. Creación, F. Última actividad
    """
    client = MongoClient(Config.MONGO_IA)
    db = client.get_default_database()
    agent_sessions_collection = db["agent_sessions"]

    agents = await get_agents()
    if params.agent_ids is None:
        params.agent_ids = [item["agent_id"] for item in agents]
    else:
        filtered_agents = [item for item in agents if item["agent_id"] in params.agent_ids]
        agents = filtered_agents

    # Mongo query - obtener listado de conversaciones
    mongo_filter = create_mongo_filter(params)

    # Primero obtener el total de registros que coinciden con el filtro
    total_count = agent_sessions_collection.count_documents(mongo_filter)

    # Obtener los registros con paginación
    conversaciones = agent_sessions_collection.aggregate([
        {"$match": mongo_filter},
        {"$sort": {"created_at": -1}},  # Ordenar por fecha de creación descendente
        {"$skip": skip},
        {"$limit": limit},
        {
            "$project": {
                "_id": 0,
                "session_id": 1,
                "agent_id": 1,
                "agent_name": "$agent_data.name",
                "user_id": 1,
                "titulo": {"$ifNull": ["$session_data.session_name", "Sin título"]},
                "cantidad_mensajes": {"$size": {"$ifNull": ["$memory.runs", []]}},
                "fecha_creacion": {"$toDate": {"$multiply": ["$created_at", 1000]}},
                "ultima_actividad": {"$toDate": {"$multiply": ["$updated_at", 1000]}},
            }
        }
    ]).to_list(length=None)

    # Formatear las fechas a formato ISO con Z
    for conv in conversaciones:
        # Convertir a formato ISO 8601 con Z para indicar UTC
        conv["fecha_creacion"] = conv["fecha_creacion"].strftime("%Y-%m-%dT%H:%M:%SZ")
        conv["ultima_actividad"] = conv["ultima_actividad"].strftime("%Y-%m-%dT%H:%M:%SZ")

    # Obtener diccionario de nombres de usuarios
    user_ids = [conv["user_id"] for conv in conversaciones]
    user_names = get_user_names_dict(user_ids)

    # Añadir nombre de usuario a cada conversación
    for conv in conversaciones:
        conv["user_name"] = user_names.get(conv["user_id"], "Usuario Desconocido")

    # Resultado final con metadatos de paginación
    return {
        "total": total_count,
        "pagina_actual": skip // limit + 1,
        "total_paginas": (total_count + limit - 1) // limit,
        "por_pagina": limit,
        "conversaciones": conversaciones,
        "periodo": {
            "fecha_desde": params.fecha_desde.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fecha_hasta": params.fecha_hasta.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
    }


@report_router.get("/conversaciones-por-franja-horaria")
async def get_conversaciones_por_franja_horaria(params: DateAgentFilter = Depends(get_filter_params)):
    """
    Obtiene la cantidad de conversaciones por franja horaria de 30 minutos (Total y por agente)
    """
    client = MongoClient(Config.MONGO_IA)
    db = client.get_default_database()
    agent_sessions_collection = db["agent_sessions"]

    agents = await get_agents()
    if params.agent_ids is None:
        params.agent_ids = [item["agent_id"] for item in agents]
    else:
        filtered_agents = [item for item in agents if item["agent_id"] in params.agent_ids]
        agents = filtered_agents

    # Mongo query - agrupar por franja horaria
    mongo_filter = create_mongo_filter(params)
    result = agent_sessions_collection.aggregate([
        {"$match": mongo_filter},
        {
            "$group": {
                "_id": {
                    "agent_id": "$agent_id",
                    "franja_horaria": {
                        "$let": {
                            "vars": {
                                "date_obj": {"$toDate": {"$multiply": ["$created_at", 1000]}},
                            },
                            "in": {
                                "$concat": [
                                    {"$toString": {"$hour": "$$date_obj"}},
                                    ":",
                                    {
                                        "$cond": [
                                            {"$lt": [{"$minute": "$$date_obj"}, 30]},
                                            "00",
                                            "30"
                                        ]
                                    }
                                ]
                            }
                        }
                    }
                },
                "agent_name": {"$first": "$agent_data.name"},
                "cantidad": {"$sum": 1}
            }
        },
        {
            "$project": {
                "_id": 0,
                "agent_id": "$_id.agent_id",
                "franja_horaria": "$_id.franja_horaria",
                "agent_name": 1,
                "cantidad": 1
            }
        },
        {"$sort": {"agent_id": 1, "franja_horaria": 1}}
    ]).to_list(length=None)

    # Formatear resultado
    all_franjas = genera_rango_franjas_horarias()

    agent_names = {}
    data_by_agent = {}
    total_by_franja = {franja: 0 for franja in all_franjas}

    for item in result:
        agent_id = item["agent_id"]
        agent_name = item["agent_name"]
        franja_horaria = item["franja_horaria"]
        cantidad = item["cantidad"]

        # Formatear franja horaria para que coincida con el formato esperado
        if len(franja_horaria.split(":")[0]) == 1:
            franja_horaria = "0" + franja_horaria

        agent_names[agent_id] = agent_name

        if agent_name not in data_by_agent:
            data_by_agent[agent_name] = {franja: 0 for franja in all_franjas}

        if franja_horaria in data_by_agent[agent_name]:
            data_by_agent[agent_name][franja_horaria] = cantidad

        if franja_horaria in total_by_franja:
            total_by_franja[franja_horaria] += cantidad

    # Convertir el diccionario a la estructura requerida
    agentes = {}
    for agent_name, franja_values in data_by_agent.items():
        valores = [franja_values[franja] for franja in all_franjas]
        agentes[agent_name] = valores

    # Añadir el total
    agentes["Total"] = [total_by_franja[franja] for franja in all_franjas]

    # Resultado final
    return {
        "franjas_horarias": all_franjas,
        "agentes": agentes
    }


@report_router.get("/usuarios-activos-por-franja-horaria")
async def get_usuarios_activos_por_franja_horaria(params: DateAgentFilter = Depends(get_filter_params)):
    """
    Obtiene la cantidad de usuarios activos por franja horaria de 30 minutos (Total y por agente)
    """
    client = MongoClient(Config.MONGO_IA)
    db = client.get_default_database()
    agent_sessions_collection = db["agent_sessions"]

    agents = await get_agents()
    if params.agent_ids is None:
        params.agent_ids = [item["agent_id"] for item in agents]
    else:
        filtered_agents = [item for item in agents if item["agent_id"] in params.agent_ids]
        agents = filtered_agents

    # Mongo query - contar usuarios ÚNICOS por franja horaria y por agente
    mongo_filter = create_mongo_filter(params)
    result = agent_sessions_collection.aggregate([
        {"$match": mongo_filter},
        {
            "$group": {
                "_id": {
                    "agent_id": "$agent_id",
                    "franja_horaria": {
                        "$let": {
                            "vars": {
                                "date_obj": {"$toDate": {"$multiply": ["$created_at", 1000]}},
                            },
                            "in": {
                                "$concat": [
                                    {"$toString": {"$hour": "$$date_obj"}},
                                    ":",
                                    {
                                        "$cond": [
                                            {"$lt": [{"$minute": "$$date_obj"}, 30]},
                                            "00",
                                            "30"
                                        ]
                                    }
                                ]
                            }
                        }
                    },
                    "user_id": "$user_id"  # Agrupamos también por user_id para contarlos después
                },
                "agent_name": {"$first": "$agent_data.name"}
            }
        },
        {
            # Segundo nivel de agrupación: solo por agente y franja horaria
            "$group": {
                "_id": {
                    "agent_id": "$_id.agent_id",
                    "franja_horaria": "$_id.franja_horaria"
                },
                "agent_name": {"$first": "$agent_name"},
                "cantidad_usuarios": {"$sum": 1}  # Cuenta usuarios únicos
            }
        },
        {
            "$project": {
                "_id": 0,
                "agent_id": "$_id.agent_id",
                "franja_horaria": "$_id.franja_horaria",
                "agent_name": 1,
                "cantidad": "$cantidad_usuarios"
            }
        },
        {"$sort": {"agent_id": 1, "franja_horaria": 1}}
    ]).to_list(length=None)

    # Formatear resultado
    all_franjas = genera_rango_franjas_horarias()

    agent_names = {}
    data_by_agent = {}
    total_by_franja = {franja: 0 for franja in all_franjas}

    for item in result:
        agent_id = item["agent_id"]
        agent_name = item["agent_name"]
        franja_horaria = item["franja_horaria"]
        cantidad = item["cantidad"]

        # Formatear franja horaria para que coincida con el formato esperado
        if len(franja_horaria.split(":")[0]) == 1:
            franja_horaria = "0" + franja_horaria

        agent_names[agent_id] = agent_name

        if agent_name not in data_by_agent:
            data_by_agent[agent_name] = {franja: 0 for franja in all_franjas}

        if franja_horaria in data_by_agent[agent_name]:
            data_by_agent[agent_name][franja_horaria] = cantidad

        if franja_horaria in total_by_franja:
            total_by_franja[franja_horaria] += cantidad

    # Convertir el diccionario a la estructura requerida
    agentes = {}
    for agent_name, franja_values in data_by_agent.items():
        valores = [franja_values[franja] for franja in all_franjas]
        agentes[agent_name] = valores

    # Añadir el total
    agentes["Total"] = [total_by_franja[franja] for franja in all_franjas]

    # Resultado final
    return {
        "franjas_horarias": all_franjas,
        "agentes": agentes
    }


@report_router.get("/mensajes-por-franja-horaria")
async def get_mensajes_por_franja_horaria(params: DateAgentFilter = Depends(get_filter_params)):
    """
    Obtiene la cantidad de mensajes por franja horaria de 30 minutos (Total y por agente)
    """
    client = MongoClient(Config.MONGO_IA)
    db = client.get_default_database()
    agent_sessions_collection = db["agent_sessions"]

    agents = await get_agents()
    if params.agent_ids is None:
        params.agent_ids = [item["agent_id"] for item in agents]
    else:
        filtered_agents = [item for item in agents if item["agent_id"] in params.agent_ids]
        agents = filtered_agents

    # Mongo query - contar mensajes por franja horaria y por agente
    mongo_filter = create_mongo_filter(params)
    result = agent_sessions_collection.aggregate([
        {"$match": mongo_filter},
        {
            "$group": {
                "_id": {
                    "agent_id": "$agent_id",
                    "franja_horaria": {
                        "$let": {
                            "vars": {
                                "date_obj": {"$toDate": {"$multiply": ["$created_at", 1000]}},
                            },
                            "in": {
                                "$concat": [
                                    {"$toString": {"$hour": "$$date_obj"}},
                                    ":",
                                    {
                                        "$cond": [
                                            {"$lt": [{"$minute": "$$date_obj"}, 30]},
                                            "00",
                                            "30"
                                        ]
                                    }
                                ]
                            }
                        }
                    }
                },
                "agent_name": {"$first": "$agent_data.name"},
                "cantidad": {"$sum": {"$size": "$memory.runs"}}  # Sumar total de mensajes
            }
        },
        {
            "$project": {
                "_id": 0,
                "agent_id": "$_id.agent_id",
                "franja_horaria": "$_id.franja_horaria",
                "agent_name": 1,
                "cantidad": 1
            }
        },
        {"$sort": {"agent_id": 1, "franja_horaria": 1}}
    ]).to_list(length=None)

    # Formatear resultado
    all_franjas = genera_rango_franjas_horarias()

    agent_names = {}
    data_by_agent = {}
    total_by_franja = {franja: 0 for franja in all_franjas}

    for item in result:
        agent_id = item["agent_id"]
        agent_name = item["agent_name"]
        franja_horaria = item["franja_horaria"]
        cantidad = item["cantidad"]

        # Formatear franja horaria para que coincida con el formato esperado
        if len(franja_horaria.split(":")[0]) == 1:
            franja_horaria = "0" + franja_horaria

        agent_names[agent_id] = agent_name

        if agent_name not in data_by_agent:
            data_by_agent[agent_name] = {franja: 0 for franja in all_franjas}

        if franja_horaria in data_by_agent[agent_name]:
            data_by_agent[agent_name][franja_horaria] = cantidad

        if franja_horaria in total_by_franja:
            total_by_franja[franja_horaria] += cantidad

    # Convertir el diccionario a la estructura requerida
    agentes = {}
    for agent_name, franja_values in data_by_agent.items():
        valores = [franja_values[franja] for franja in all_franjas]
        agentes[agent_name] = valores

    # Añadir el total
    agentes["Total"] = [total_by_franja[franja] for franja in all_franjas]

    # Resultado final
    return {
        "franjas_horarias": all_franjas,
        "agentes": agentes
    }

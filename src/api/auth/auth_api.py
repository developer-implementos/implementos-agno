from fastapi import APIRouter, HTTPException, Depends
import requests
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from pydantic import BaseModel
from config.config import Config
from agno.utils.log import logger
import jwt

# Modelo para la solicitud de login
class LoginRequest(BaseModel):
    usuario: str
    contrasenia: str

class TokenLoginRequest(BaseModel):
    token: str

def capitalizar_string(texto):
    if not texto:
        return ""
    return texto.title()

# Crear router para autenticación
auth_router = APIRouter(prefix="/auth", tags=["auth"])

@auth_router.post("/login")
async def login(login_data: LoginRequest):
    """
    Endpoint para autenticación en el sistema Omni

    Args:
        login_data: Datos de login (usuario y contraseña)

    Returns:
        dict: Información del usuario autenticado
    """
    try:
        # Llamar a la API de login de Omni
        response = requests.post(
            "https://replicacion.implementos.cl/ApiOmnichannel/api/seguridad/loginOmni",
            json={
                "usuario": login_data.usuario,
                "contrasenia": login_data.contrasenia
            }
        )

        # Verificar la respuesta
        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectas")

        user_data = response.json()

        # Verificar que la respuesta contenga los datos necesarios
        if not user_data or not user_data.get("codEmpleado"):
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectas")

        user_data["nombre"] = capitalizar_string(user_data.get("nombre"))

        # Preparar datos para guardar en MongoDB
        auth_info = {
            "codigo_empleado": user_data.get("codEmpleado"),
            "vendedor_recid": user_data.get("vendedorRecid"),
            "rut": user_data.get("rut"),
            "usuario": user_data.get("nombreUsuario", user_data.get("usuario", "")).lower(),
            "nombre": user_data.get("nombre"),
            "token": user_data.get("jwt"),
            "email": user_data.get("email"),
            "movil": user_data.get("movil"),
            "ultimo_ingreso": datetime.now()
        }

        # Guardar en MongoDB
        client = MongoClient(Config.MONGO_IA)
        db = client.get_default_database()

        # Actualizar o insertar registro
        db.agent_auth_info.update_one(
            {"codigo_empleado": auth_info["codigo_empleado"]},
            {"$set": auth_info},
            upsert=True
        )

        return user_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en login: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error en el proceso de login: {str(e)}")


@auth_router.get("/login-by-token")
async def login_by_token(login_data: TokenLoginRequest = Depends()):
    """
    Decodifica un token existente, reconstruye el payload y emite uno nuevo
    """
    try:
        if not login_data.token:
            raise HTTPException(status_code=400, detail="Debe enviar un token ?token=<token>")

        # Decodificar token existente
        try:
            usuario = jwt.decode(login_data.token, Config.JWT_SECRET, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expirado")
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"Token inválido: {str(e)}")

        # Limpiar propiedades no deseadas
        usuario.pop("iat", None)
        usuario.pop("exp", None)

        if "usuario" in usuario:
            usuario["nombreUsuario"] = usuario["usuario"].lower()
            usuario["usuario"] = usuario["usuario"].lower()

        if "bodegas" in usuario and isinstance(usuario["bodegas"], list):
            usuario["bodegas"] = [b for b in usuario["bodegas"] if b]

        # Construir payload nuevo
        payload = {
            **usuario,
            "nombre": capitalizar_string(usuario.get("nombre", "")),
            "exp": datetime.now(timezone.utc) + timedelta(hours=48)
        }

        # Generar nuevo token
        nuevo_token = jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")
        payload["jwt"] = nuevo_token

        return payload

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en login_by_token: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error procesando token: {str(e)}")

from datetime import datetime, timedelta, timezone

import jwt

from config.config import Config
from utils.obtener_usuario import obtener_usuario


def capitalizar_string(texto: str) -> str:
    """Capitaliza un string (primera letra de cada palabra en mayúscula)"""
    if not texto:
        return ""
    return " ".join(palabra.capitalize() for palabra in texto.split())

def obtener_token_omni_vendedor(cod_vendedor: int) -> str:
    usuario = obtener_usuario(cod_vendedor)

    payload = usuario.model_dump()

    options = {
        "exp": datetime.now(timezone.utc) + timedelta(hours=48)
    }

    jwt_secret = Config.JWT_SECRET
    token = jwt.encode({ **payload, **options }, jwt_secret, algorithm="HS256")

    return token

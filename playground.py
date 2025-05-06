import sys
import os

# Añade la carpeta 'libs' al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "libs", "agno")))
# Añade la carpeta 'src' al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

# Libreria
from agno.playground import Playground, serve_playground_app
from agno.playground.settings import PlaygroundSettings

# Src
from agent.agent_ventas import Agente_Ventas, Agente_Ventas_DeepSearch
from agent.agent_ventas_voice import Agente_Ventas_Voice
from agent.agent_articulos import Agente_Articulos
from agent.agent_cartera_vt import Agente_Cartera_Vt, Agente_Cartera_Vt_DeepSearch
from agent.agent_clientes_vt import Agente_Clientes_Vt
from agent.agent_clientes import Agente_Clientes
from agent.agent_documentos import Agente_Documentos
from agent.agent_ecommerce import Agente_Ecommerce
from agent.agent_maestro_mecanico import Agente_Maestro_Mecanico
from agent.agent_vt import Agente_VT
from config.config import Config

from api.auth.auth_api import auth_router

# Exporta las variables como variables de entorno
os.environ["OPENAI_API_KEY"] = Config.OPENAI_API_KEY
os.environ["ANTHROPIC_API_KEY"] = Config.ANTHROPIC_API_KEY

# Configura CORS personalizado
settings = PlaygroundSettings(
    cors_origin_list=["http://localhost:3000", "http://localhost:3001", "https://agentes.implementos.cl", "*"]
)

app = Playground(
    agents=[
        Agente_VT,
        Agente_Ventas, Agente_Ventas_DeepSearch,
        Agente_Ventas_Voice,
        Agente_Articulos,
        Agente_Cartera_Vt, Agente_Cartera_Vt_DeepSearch,
        Agente_Clientes_Vt,
        Agente_Clientes,
        Agente_Documentos,
        Agente_Ecommerce,
        Agente_Maestro_Mecanico,
    ],
    settings=settings
).get_app(use_async=True)

# Custom APIS
app.include_router(auth_router)

if __name__ == "__main__":
    serve_playground_app("playground:app",host="0.0.0.0", reload=True)

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
from agent.agent_ventas import Agente_Ventas
from agent.agent_ventas_voice import Agente_Ventas_Voice
from agent.agent_articulos import Agente_Articulos
from agent.agent_cartera_vt import Agente_Cartera_Vt, Agente_Cartera_Vt_DeepSearch
from agent.agent_clientes import Agente_Clientes
from agent.agent_documentos import Agente_Documentos
from agent.agent_ecommerce import Agente_Ecommerce
from agent.agent_maestro_mecanico import Agente_Maestro_Mecanico
from agent.agent_vt import Agente_VT, Agente_VT_Voz, Agente_VT_Cristian_Sepulveda, Agente_VT_Cristian_Sepulveda_Voz
from agent.agent_jefe_linea import Agente_Jefe_Linea, Agente_Jefe_Linea_DeepSearch
from agent.agent_reporte_uen import Agente_Reportes
from config.config import Config

from api.auth.auth_api import auth_router
from api.report.report_api import report_router

# Exporta las variables como variables de entorno
os.environ["OPENAI_API_KEY"] = Config.OPENAI_API_KEY
os.environ["ANTHROPIC_API_KEY"] = Config.ANTHROPIC_API_KEY

# Configura CORS personalizado
settings = PlaygroundSettings(
    cors_origin_list=["http://localhost:3000", "http://localhost:3001", "https://agentes.implementos.cl", "*"]
)

playground_instance = Playground(
    agents=[
        Agente_Reportes,
        Agente_Ventas, Agente_Ventas_Voice,
        Agente_Cartera_Vt, Agente_Cartera_Vt_DeepSearch,
        Agente_Jefe_Linea, Agente_Jefe_Linea_DeepSearch,
        Agente_VT, Agente_VT_Voz, Agente_VT_Cristian_Sepulveda, Agente_VT_Cristian_Sepulveda_Voz,
        Agente_Articulos,
        # Agente_Clientes,
        # Agente_Documentos,
        Agente_Ecommerce,
        # Agente_Maestro_Mecanico,
    ],
    settings=settings
)

app = playground_instance.get_app(use_async=True)

# Custom APIS
app.include_router(auth_router)
app.include_router(report_router)

if __name__ == "__main__":
    serve_playground_app("playground:app",host="0.0.0.0", reload=True)

import sys
import os

# Añade la carpeta 'libs' al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "libs", "agno")))
# Añade la carpeta 'src' al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

# Libreria
from agno.playground import Playground, serve_playground_app

# Src
from agent.agent_basic import Agente_Basico
from agent.agent_ventas import Agente_Ventas
from agent.agent_ventas_voice import Agente_Ventas_Voice
from agent.agent_articulos import Agente_Articulos
from agent.agent_cartera_vt import Agente_Cartera_Vt
from agent.agent_clientes_vt import Agente_Clientes_Vt
from agent.agent_clientes import Agente_Clientes
from agent.agent_documentos import Agente_Documentos
from agent.agent_ecommerce import Agente_Ecommerce
from agent.agent_maestro_mecanico import Agente_Maestro_Mecanico
from config.config import Config

# Exporta las variables como variables de entorno
os.environ["OPENAI_API_KEY"] = Config.OPENAI_API_KEY
os.environ["ANTHROPIC_API_KEY"] = Config.ANTHROPIC_API_KEY

app = Playground(
    agents=[
        Agente_Basico,
        Agente_Ventas,
        Agente_Ventas_Voice,
        Agente_Articulos,
        Agente_Cartera_Vt,
        Agente_Clientes_Vt,
        Agente_Clientes,
        Agente_Documentos,
        Agente_Ecommerce,
        Agente_Maestro_Mecanico,
    ]
).get_app(use_async=True)

if __name__ == "__main__":
    serve_playground_app("playground:app",host="0.0.0.0", reload=True)

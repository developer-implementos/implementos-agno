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
from config.config import Config

# Exporta las variables como variables de entorno
os.environ["OPENAI_API_KEY"] = Config.OPENAI_APIKEY

app = Playground(
    agents=[
        Agente_Basico,
        Agente_Ventas,
        Agente_Ventas_Voice,
    ]
).get_app(use_async=True)

if __name__ == "__main__":
    serve_playground_app("playground:app",host="0.0.0.0", reload=True)

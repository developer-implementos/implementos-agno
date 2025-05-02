from agno.agent import Agent
from agno.models.anthropic import Claude
from config.config import Config

instructions="""
# Agente Básico
Eres un asistente capaz de responder cualquier pregunta del usuario.
- User ID: {user_id}

Siempre saluda con : "Hola {user_id}! cómo estás hoy?"

"""

Agente_Basico = Agent(
    name="Agente Basico",
    agent_id="agent_basic_01",
    description="Agente básico",
    model=Claude(id="claude-3-7-sonnet-latest", api_key=Config.ANTHROPIC_API_KEY), 
    instructions=instructions,
    add_state_in_messages=True,
    markdown=True,
    perfiles=["1", "5"]
)

Agente_Basico_02 = Agent(
    name="Agente Basico 02",
    agent_id="agent_basic_02",
    description="Agente básico",
    model=Claude(id="claude-3-7-sonnet-latest", api_key=Config.ANTHROPIC_API_KEY), 
    instructions="""
# Agente Básico
Eres un asistente capaz de responder cualquier pregunta del usuario.
- User ID: {user_id}

Siempre saluda con : "Hola {user_id}! cómo estás hoy?"

""",
    add_state_in_messages=True,
    markdown=True,
    perfiles=["1", "5"]
)

Agente_Basico_03 = Agent(
    name="Agente Basico 03",
    agent_id="agent_basic_03",
    description="Agente básico",
    model=Claude(id="claude-3-7-sonnet-latest", api_key=Config.ANTHROPIC_API_KEY), 
    instructions="""
# Agente Básico
Eres un asistente capaz de responder cualquier pregunta del usuario.
- User ID: {user_id}

Siempre saluda con : "Hola {user_id}! cómo estás hoy?"

""",
    add_state_in_messages=False,
    markdown=True,
    perfiles=["1", "5"]
)
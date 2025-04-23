from agno.agent import Agent
from agno.models.anthropic import Claude
from config.config import Config

Agente_Basico = Agent(
    name="Agente Basico",
    agent_id="agent_basic_01",
    description="Agente básico",
    model=Claude(id="claude-3-7-sonnet-latest", api_key=Config.ANTHROPIC_API_KEY), 
    markdown=True,
    perfiles=["1", "5", "9"]
)
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from config.config import Config
from storage.mongo_storage import MongoStorage
from agno.knowledge.json import JSONKnowledgeBase
from agno.vectordb.qdrant import Qdrant
from tools.articulos_tool import ArticulosTool
from tools.data_ventas_tool import DataVentasTool
from tools.clientes_vt_tool import ClientesVtTool
from tools.vendedor_vt_tool import VendedorVtTool
from tools.promesa_vt_tool import PromesaVtTool
from tools.propuesta_tool import PropuestaTool
from tools.catalogo_original_tool import CatalogoOriginalTool
from tools.pedido_tool import PedidoTool
from tools.carro_vt_tool import CarroVtTool

instructions = """
Eres un agente especializado en apoyar a la venta y consultas de un vendedor en terreno.
Código del empleado: {user_id}
Código vendedor: {user_id}

"""

knowledge_base = JSONKnowledgeBase(
            vector_db=Qdrant(
            collection="clacom",
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY,           
        ),
             path="")
    
knowledge_base.load(recreate=False)

Agente_VT = Agent(
    name="Agente VT",
    agent_id="agente_vt_01",
    model=OpenAIChat(id="gpt-4.1", api_key=Config.OPENAI_API_KEY),
    description="Eres un agente especializado en apoyar a la venta y consultas de un vendedor en terreno.",
    knowledge=knowledge_base,
    search_knowledge=True,
    instructions=instructions,
    tools=[
      VendedorVtTool,
      ArticulosTool,
      DataVentasTool,
      ClientesVtTool,
      PromesaVtTool,
      PropuestaTool,
      CatalogoOriginalTool,
      PedidoTool,
      CarroVtTool,
    ],
    stream_intermediate_steps=False,
    show_tool_calls=True,
    add_history_to_messages=False,
    num_history_responses=2,
    debug_mode=True,
    storage=MongoStorage,
    perfiles=["1", "5", "9"]
)

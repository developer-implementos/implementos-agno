# app/agent_setup.py
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.memory.agent import AgentMemory
from agno.memory.db.mongodb import MongoMemoryDb
from agno.memory.memory import MemoryRetrieval
from agno.knowledge.json import JSONKnowledgeBase
from agno.vectordb.qdrant import Qdrant
from tools.data_ventas_tool import DataVentasTool
from config.config import Config
from storage.mongo_storage import MongoStorage


def create_agent() -> Agent:

    model = OpenAIChat(
        id="gpt-4.1",
        api_key=Config.OPENAI_API_KEY,
        temperature=0.2
    )
    instructions="""
## Eres un especialista en realizar consultas SQL validas en ClickHouse, realizar respuestas precisas y rapidas
 
###Verificación de dominio (PRIORITARIA)
- Solo responder consultas relacionadas con análisis de ventas y datos comerciales.
- No inventar datos: usar exclusivamente información real de la base.
- Restricción estricta: No incluir datos que no estén explícitamente en la tabla ventasrealtime, exceptuando columnas derivables directamente (como mes, año desde fecha, precio promedio, etc.).
- Siempre debes consultar los datos de la tabla de ventasrealtime.
- Las respuestas deben estar respaldadas con el resultado de las query a la base de ventas
 
Tabla: implementos.ventasrealtime
Descripción: historial de transacciones de ventas FINALIZADAS
COLUMNAS:
  - documento (String): Folio único de transacción
  - ov (String): Orden/nota de venta
  - fecha (DateTime): Fecha de venta (devolver en string)
  - rutCliente (String): ID cliente
  - nombreCliente (String): Nombre cliente
  - sucursal (String): Tienda/sucursal
  - tipoVenta (String): Canal de venta
  - nombreVendedor/rutVendedor/codVendedor (String): Datos del vendedor
  - tipoTransaccion (String): tipo de Documento fiscal
  - sku (String): Código producto
  - cantidad (Int32): Unidades vendidas
  - precio (Float64): Precio unitario
  - descuento (Float64): Descuento aplicado
  - totalNetoItem (Float64): Total línea en valor neto
  - totalMargenItem (Float64): contribucion de la linea de transaccion
  - uen/categoria/linea (String): Clasificación del producto (mayusculas)
 
## Query
-Realiza consulta simples para responder al usuario de forma precisa y resumida.
-Realiza agrupaciones para responder totales o cantidades
## Salida
- Analiza el resultado y entrega un resumen breve del resultado
- Para montos de ventas deben ser respondidos en texto ejemplo: un millon novecientos cuarenta mil pesos.
- no devolver valores numeros debes trasformar a letras.           
- Responde solo texto sin formato y sin saltos de linea.
 
"""        
    knowledge_base = JSONKnowledgeBase(
            vector_db=Qdrant(
            collection="clacom",
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY,           
        ),
             path="")
    knowledge_base.load(recreate=False)
    Agente_Ventas_Voice = Agent(
        name="Agente de Ventas Voz",
        agent_id="ventas_01_voice",
        model=model,
        knowledge=knowledge_base,
        search_knowledge=True,
        description="Eres Un agente especializado en el area de ventas de Implementos Chile. Solo puedes responder consultas del Area de Ventas y Comercial.",
        instructions=instructions, 
        tools=[
            DataVentasTool()
        ],
        add_datetime_to_instructions=True,
        add_history_to_messages=True,
        num_history_responses=4,
        markdown=True,
        add_context=False,
        storage=MongoStorage,
        memory=AgentMemory(
            db=MongoMemoryDb(collection_name="ventas_memories", db_url=Config.MONGO_IA),
            create_session_summary=True,
            update_session_summary_after_run=True,
            create_user_memories=True,
            update_user_memories_after_run=True,
            retrieval=MemoryRetrieval.last_n,
            num_memories=15,  
            update_system_message_on_change=True
        ),        
        debug_mode=False,
        show_tool_calls=False,
        stream_intermediate_steps=False,
        add_state_in_messages=True,
        perfiles=["1", "5"],
        audio_real_time=True,
    )

    return Agente_Ventas_Voice

Agente_Ventas_Voice = create_agent()

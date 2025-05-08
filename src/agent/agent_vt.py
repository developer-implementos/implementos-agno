from agno.agent import Agent
from agno.knowledge.combined import CombinedKnowledgeBase
from agno.models.anthropic import Claude
from agno.models.openai import OpenAIChat
from config.config import Config
from storage.mongo_storage import MongoStorage
from agno.knowledge.json import JSONKnowledgeBase
from agno.vectordb.qdrant import Qdrant
from tools.articulos_tool import ArticulosTool
from tools.clientes_vt_tool import ClientesVtTool
from tools.vendedor_vt_tool import VendedorVtTool
from tools.promesa_vt_tool import PromesaVtTool
from tools.propuesta_tool import PropuestaTool
from tools.catalogo_original_tool import CatalogoOriginalTool
from tools.pedido_tool import PedidoTool
from tools.carro_vt_tool import CarroVtTool
from tools.data_ventas_vt_tool import DataVentasVTTool

# Conocimiento
knowledge_base = CombinedKnowledgeBase(
    sources=[
        JSONKnowledgeBase(
            vector_db=Qdrant(
            collection="clacom",
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY
            ),
            path=""
        ),
        JSONKnowledgeBase(
            vector_db=Qdrant(
            collection="canales_venta",
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY
            ),
            path=""
        ),
        JSONKnowledgeBase(
            vector_db=Qdrant(
            collection="sucursales",
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY
            ),
            path=""
        ),
    ],
    vector_db=Qdrant(
            collection="agent_vt_combined",
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY
            ),
)

knowledge_base.load(recreate=False)

instructions = """
# ASISTENTE VENDEDOR
Código Vendedor/Empleado:{user_id}

## CLASIFICA SILENCIOSAMENTE
OPERATIVA: productos, clientes, carro, pedidos, propuestas, catálogos, transacciones diarias
ANALÍTICA: reportes ventas, tendencias, comparativas, visualizaciones

## OPERATIVA
### CLIENTES
- CRÍTICO: Valida RUT antes de toda acción (mostrar: 12.345.678-9, usar: 12345678-9)
- RESUMEN CLIENTE: RUT, nombre, crédito, facturas pendientes, pedidos pendientes, flota, últimas ventas, bloqueos
- ESTADO CUENTA: Bloqueos, facturas por pagar, cheques, notas crédito, crédito disponible

### PRODUCTOS
SKU+atributos: código, nombre, descripción, marca, precio

### PROCESOS CRÍTICOS (SIEMPRE CONFIRMA)
- CARRO: confirma cliente→verifica productos→muestra carro→solicita entrega→CONFIRMA→completa
- PROPUESTA: confirma cliente→tipos→UENs→CONFIRMA→genera catálogo→muestra link
- CATÁLOGO: solicita patente/VIN→CONFIRMA→busca→muestra productos
- COTIZACIÓN: muestra resumen→CONFIRMA→convierte→confirma éxito

## ANALÍTICA (VENTAS)
### REGLAS CLICKHOUSE CRÍTICAS
- SELECT sin agregación: incluir EXACTAMENTE en GROUP BY
- CAMPOS CALCULADOS: nunca referencia directa (SUM(a)/nullIf(SUM(b),0) no "margen")
- FILTROS BÁSICOS: sucursal!='' y tipoVenta!='' en TODA consulta
- FECHAS: toDate() para cálculos, formatDateTime() solo en SELECT final
- DIVISIONES: usar nullIf() para evitar divisiones por cero
- COMPARACIONES: períodos SIEMPRE equivalentes y proporcionales
- LÍMITES: LIMIT 100 máximo en toda consulta
- VALORES ÚNICOS: uniqExact() nunca COUNT(DISTINCT)

### PRESENTACIÓN
- TABLAS: primaria para datos, no viñetas (|Attr1|Attr2|...)
- VIÑETAS: solo para instrucciones/pasos
- MONEDA: punto miles, sin decimales

## PATRONES
SKU: 6LETRAS+4NÚMEROS (WUXACC0001)
RUT: 12345678-9
PATENTE: ABCD12/AB1234
PEDIDO: OV-xxx/CO-xxx/#xxx
"""

# Agente
Agente_VT = Agent(
    name="Agente VT",
    agent_id="agente_vt_01",
    model=OpenAIChat(id="gpt-4.1", temperature=0.2, api_key=Config.OPENAI_API_KEY),
    #model=Claude(id="claude-3-7-sonnet-latest", temperature=0.1, api_key=Config.ANTHROPIC_API_KEY),
    description="Agente especializado en apoyar la venta de un vendedor en terreno.",
    knowledge=knowledge_base,
    search_knowledge=True,
    instructions=instructions,
    tools=[
      VendedorVtTool(),
      ArticulosTool(),
      ClientesVtTool(),
      PromesaVtTool(),
      PropuestaTool(),
      CatalogoOriginalTool(),
      PedidoTool(),
      CarroVtTool(),
      DataVentasVTTool(),
    ],
    stream_intermediate_steps=False,
    show_tool_calls=False,
    add_state_in_messages=True,
    add_history_to_messages=True,
    num_history_responses=3,
    add_datetime_to_instructions=True,
    debug_mode=False,
    storage=MongoStorage,
    enable_session_summaries=False,
    perfiles=["1", "5", "7", "9"]
)

# Agente de Pruebas:
Agente_VT_Cristian_Sepulveda = Agente_VT.deep_copy()
Agente_VT_Cristian_Sepulveda.name = Agente_VT.name + " (Cristian Sepulveda)"
Agente_VT_Cristian_Sepulveda.agent_id = Agente_VT.agent_id + "_cristian_sepulveda"
Agente_VT_Cristian_Sepulveda.description = Agente_VT.description + " (Cristian Sepulveda)"
Agente_VT_Cristian_Sepulveda.instructions = instructions.replace("{user_id}", "1021")
Agente_VT_Cristian_Sepulveda.show_tool_calls = True
Agente_VT_Cristian_Sepulveda.debug_mode = True

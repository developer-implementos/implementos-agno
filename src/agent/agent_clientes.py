import json
import requests
from agno.agent import Agent
from agno.models.anthropic import Claude
from agno.tools.pandas import PandasTools
from storage.mongo_storage import MongoStorage
from agent.agent_articulos import Agente_Articulos
from tools.clientes_tool import ClientesTool
from tools.data_ventas_tool import DataVentasTool

def estado_ov(ov: str):
    """
    Buscar informacion logistica de una OV solo de OV facturadas 
    Args:
        ov (str): OV a buscar OV-1234567.                
    Returns:
        str: Resultado de la consulta en formato JSON.
    """
    try:
        # URL de la API de precios
        api_url = "https://b2b-api.implementos.cl/ecommerce/api/v1/oms/order/tracking/"+ov
       
        
        # Configurar los headers
        headers = {
            "Content-Type": "application/json",
            "Authorization":"Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
        }
        
        # Realizar la solicitud POST
        response = requests.get(api_url, headers=headers)
         # Verificar si la solicitud fue exitosa
        if response.status_code == 200:
                # Convertir la respuesta a JSON
                result = response.json()
                              
                formatted_result = json.dumps(result, ensure_ascii=False, indent=2)
                return formatted_result
        else:
                return f"Error en la solicitud: {response.status_code} - {response.text}"
      
    except Exception as e:
      print(f"Error al consultar : {str(e)}")
    return None    


Agente_Clientes = Agent(
     name="Especialista Clientes",
     agent_id="clientes_01",
     model=Claude(id="claude-3-7-sonnet-20250219"),
     team=[Agente_Articulos],
     description="Eres Un agente especializado en informacion de clientes.",
     instructions=[
       """Tu objetivo es entregar informacion de clientes especificas o general. Debes obtener el rut para buscar la informacion
        *tools:
          list_schema antes de run_select_query para no crear query erroneas 
             - el campo rut es rutCliente
             - el campo tipoTransaccion indica si es FEL:facturas , BEL: boletas , NCE y NCI: notas de credito
             - solo querys validas para CLICKHOUSE
             - en caso de fallo reintenta y analiza el schemma
             - fecha de la venta usar toString(fecha) para salidas
             - evitar salidad mayores a 100 registros LIMIT 100
        Operaciones que puedes hacer     
         - Informacion del cliente
         - Analisis de compras tendencias
         - Historial de compra
         - Recomendaciones y proyecciones de ventas
         - Informe completo
         - Flota de Vehiculos
         - Todo lo relacionado con el historial de ventas
         - buscar informacion de una OV y su estado
        ### Importante:
          - NUNCA incluir respuestas con datos: query SQL, datos de tablas, mensajes de errores, información técnica de ClickHouse, No indiques que tuvistes alguna problema en el proceso. 
         ##EVITA ERRORES: 
        - prefiere querys con agrupacion y siempre limita los resutados con LIMIT 100, en la salida al usuario no deben existir listados grandes
        - Ante preguntas ambiguas solicita al usuario mas datos como ejemplo: periodos, uen , categoria , linea, sucursal, clientes, mensual, comparaciones , etc. 
         ##SALIDA: prefiere usar tablas antes que listas, solo listas en caso necesario
         """
    ],
     tools=[ClientesTool(),estado_ov,DataVentasTool(),PandasTools()],
     show_tool_calls=True,
     add_datetime_to_instructions=True,
     add_history_to_messages=True,
     num_history_responses=4,
     storage=MongoStorage,
     debug_mode=True,
     perfiles=["1", "5"]
    )

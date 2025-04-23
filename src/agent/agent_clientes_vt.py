import json
import requests
from pymongo import MongoClient
from agno.agent import Agent
from agno.models.anthropic import Claude
from agno.embedder.openai import OpenAIEmbedder
from qdrant_client import QdrantClient
from config.config import Config
from storage.mongo_storage import MongoStorage
from tools.clientes_tool import ClientesTool
from tools.data_ventas_tool import DataVentasTool
from tools.carro_tool import CarroTool

embedder = OpenAIEmbedder(id="text-embedding-ada-002")

def buscar_cartera(texto_vendedor: str):
    """Búsqueda de clientes asignados a un vendedor
    
    Args:
        texto_vendedor (str): texto para buscar vendedor (nombre o código)
    Returns:
        str: Resultados JSON con los documentos más relevantes encontrados
    """
    try:
        qdrant_client = QdrantClient(
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY
        )
        
        # Obtener el embedding del texto de búsqueda
        query_embedding = embedder.get_embedding(texto_vendedor)
        
        # Buscar en Qdrant
        results = qdrant_client.search(
            collection_name="carteraObjetivo",
            query_vector=query_embedding,
            limit=1,
        )
        
        # Si no hay resultados, devolver un objeto vacío
        if not results:
            return json.dumps({
                "codigoVendedor": None,
                "nombreVendedor": None,
                "rutClientes": []
            }, ensure_ascii=False, indent=2)
        
        # Extraer la información relevante del primer resultado
        vendedor_data = results[0].payload
        resultado_simplificado = {
            "codigoVendedor": vendedor_data.get("codigoEmpleado"),
            "nombreVendedor": vendedor_data.get("nombreEmpleado"),
            "sucursal": vendedor_data.get("sucursal"),
            "zona": vendedor_data.get("zona"),
            "rutClientes": [cliente.get("rutCliente") for cliente in vendedor_data.get("clientes", [])],
            "total_clientes": vendedor_data.get("total_clientes", 0)
        }
                
        # Convertir a JSON con formato adecuado para caracteres especiales
        json_result = json.dumps(resultado_simplificado, ensure_ascii=False, indent=2)
        return json_result
    
    except Exception as e:
        print(f"Error durante la búsqueda en la base de datos vectorial: {str(e)}")
        return None

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

def validar_vendedor(clave: str,codVendedor: str):
    """
    valida un vendedor con su codVendedor y clave
    Args:
        clave (str): clave de vendedor.
        codVendedor (str): codigo de vendedor a validar
            
    Returns:
        str: Resultado de lvalidacion
    """
    try:
        client = MongoClient(Config.MONGO_NUBE)
        db = client.Implenet
        data = db.usuariosAX
        # Campos a recuperar de la base de datos
        campos = {
            "usuario": 1,
            "_id": 0  # Excluir el campo _id
        }

        try:
            codigo_vendedor_int = int(codVendedor)
        except ValueError:
            return "Error: El código de vendedor debe ser un número entero válido"
        # Buscar clientes por RUT que cumplan la condición de estado distinto a "NO"
        resultado = data.find(
            {
                   "codEmpleado": codigo_vendedor_int,
                   "clave":clave
            },
            projection=campos
        )

        formatted_result = json.dumps(resultado, ensure_ascii=False, indent=2)
        return formatted_result
   
    except Exception as e:
      print(f"Error al consultar : {str(e)}")
    return None    


Agente_Clientes_Vt = Agent(
    name="Agente VT Clientes",
    agent_id="clientes_vt_01",
    model=Claude(id="claude-3-7-sonnet-20250219",temperature=0.1, api_key=Config.ANTHROPIC_API_KEY),
    description="Eres un agente especializado en el área de clientes y ventas de Implementos Chile. Enfocado en realizar análisis detallado de la cartera de un vendedor especifico.",
    instructions=[
    """Tu objetivo es entregar informacion de los clientes cartera de un vendedor.
        Datos del Vendedor Identificado: codigoVendedor: {user_id}      
        ##PASOS DE ANÁLISIS OBLIGATORIOS
        - Buscar Vendedor usando tools:buscar_cartera usando su codigoVendedor
        - Si el codigoVendedor no es igual no respondas preguntas y solo indica que no Tienen Autorizacion para responder.
        - Si esta identificado y el codigoVendedor esta dentro de los resultados de validacion sigue con los pasos
        - Saluda al Vendedor Amablemente y ofrece opciones de preguntas.
        - obtener el listado de rutCliente y sucursal del vendedor validos del vendedor resultado de la tools:buscar_cartera
        - Realiza la solicitud que necesita el vendedor usando las tools disponibles
        
        ##INTRUCCIONES CORE:
        - Analizar solo los clientes del vendedor
        - Realiza las consultas que sean necesarias y orientadas a resumen de datos
        - Realiza respuestas precisas con datos solicitado y relevantes
        - Realiza analisis mas profundo en caso de que el cliente necesita mas informacion
        - determina el objetivo del usuario para que no des informacion innecesaria
        - filtra las ventas segun el codVendedor
        - los pedidos o ordenes de ventas con carros procesados
        - carro es distinto a pedido
        - carro es la etapa inicial y pedido es una etapa donde se finaliza el carro para pasar a la venta
        - en la tabla venta solo existe pedigos pagados
        - las query solo deben ser enfocadas a los rut de cliente validos en el listado del vendedor
        - Realiza querys de agrupacion y evita salidas grandes enfocate en resumenes (LIMIT 200)  
        - Reintenta query con problemas 

    ##CONSULTAS DE VENTA
        Tabla: implementos.ventasrealtime
        Descripción: historial de transacciones de ventas FINALIZADAS 

        COLUMNAS:
        - documento (String): Folio único de transacción 
        - ov (String): Orden/nota de venta
        - fecha (DateTime): Fecha de venta
        - rutCliente (String): ID cliente
        - nombreCliente (String): Nombre cliente
        - sucursal (String): Tienda/sucursal
        - tipoVenta (String): Canal de venta
        - nombreVendedor/rutVendedor/codVendedor (String): Datos del vendedor
        - tipoTransaccion (String): FEL=facturas, BEL=boletas, NCE/NCI=notas crédito
        - sku (String): Código producto
        - cantidad (Int32): Unidades vendidas
        - precio (Float64): Precio unitario
        - descuento (Float64): Descuento aplicado
        - totalNetoItem (Float64): Total línea (precio×cantidad)
        - uen/categoria/linea (String): Clasificación del producto (mayusculas)

        ÍNDICE: (rutCliente, documento, tipoTransaccion, fecha)
        ORDENADO POR: (fecha, rutCliente, sku, uen, categoria, linea, codVendedor, sucursal)
        ENGINE: MergeTree

        Tool: run_select_query : tools disponible para consultas sobre ventas de los clientes especificos 
            - el campo rut es rutCliente
            - el campo tipoTransaccion indica si es FEL:facturas , BEL: boletas , NCE y NCI: notas de credito
            - solo querys validas para CLICKHOUSE
            - filtra las ventas segun el codVendedor
            - en caso de fallo reintenta y analiza el schemma
            - fecha de la venta usar toString(fecha) para salidas
            - no uses caracteres en nombres como ñ tildes etc en nombre de campos.
            - prefiere salidad con agrupaciones y limitar salidas a 200.

    ##CARRO DE COMPRAS: uso la sucursal del vendedor para la gestion del carro, indica las salidas y acciones siguiente para que el vendedor siga agregando o modificando el carro 
        ###acciones del carro:
        - listar carro 
        - agregar carro
            - crear carro agregando un producto ( enviar list de productos [ sku,cantidad])
            - editar carro enviando nuevos productos o enviadon productos no nuevas cantidad ( enviar list de productos [ sku,cantidad])
            - eliminar todos los productos enviando productos con una lista vacia 
        - Finalizacion del proceso 
            - solicitar metodo de entrega 
            - retiro en tienda : basadas en retiro en tiendas 
            - despacho a domicilio : solo para casos de calculo en base a las direcciones registradas del cliente
                - si solicita despacho lista las direcciones de tipo despacho (tools buscar_direcciones_cliente)
                - confirma la comuna seleccionada para despacho
                - envia fechas disponible para comuna
            - confirmar fecha de entrega segun metodo
        - Creacion de Orden de venta 
            - Orden con metodo Retiro : tools Generar_retiro_tienda
            - Orden con metodo Despacho 
                
    ###IMPORTANTE GESTION DE CARRO
        - solo consultar por la sucursal del vendedor usando el codigo y no el nombre
        - listar carro solo se puede usar con la sucursal del vendedor 
        
    ### Operaciones que puedes hacer     
        - Informacion del cliente
        - Analisis de compras tendencias
        - Historial de compra
        - Recomendaciones y proyecciones de ventas
        - Flota de Vehiculos
        - Todo lo relacionado con el historial de ventas
        - buscar informacion de una OV y su estado logistico
        - Cotizaciones pendientes o abiertas

    ### Importante:
        - NUNCA incluir respuestas con datos: query SQL, datos de tablas, mensajes de errores, información técnica de ClickHouse, No indiques que tuvistes alguna problema en el proceso. 

    ##EVITA ERRORES: 
    - prefiere querys con agrupacion y siempre limita los resutados con LIMIT 100, en la salida al usuario no deben existir listados grandes
    - Ante preguntas ambiguas solicita al usuario mas datos como ejemplo: periodos, uen , categoria , linea, sucursal, clientes, mensual, comparaciones , etc. 
    ##EXTRA conversion de sucursal a codigo valido:
            ALTO HOSPICIO = ALT HOSPIC
            ANTOFAGASTA = ANTOFGASTA
            ARICA = ARICA
            CALAMA = CALAMA
            CASTRO = CASTRO
            CHILLAN = CHILLAN
            CON CON = CON CON
            CONCEPCION = CONCEPCION
            COPIAPO = COPIAPO
            COQUIMBO = COQUIMBO
            CORONEL = CORONEL
            CURICO = CURICO
            LAMPA = EP EQUIPOS
            ESTACION CENTRAL = EST CNTRAL
            HUECHURABA = HUECHURABA
            IQUIQUE = IQUIQUE
            LAMPA = LAMPA
            LINARES = LINARES
            LOS ANGELES = LS ANGELES
            MELIPILLA = MELIPILLA
            OSORNO = OSORNO
            PUERTO MONTT = P MONTT2
            PLACILLA = PLACILLA
            PUNTA ARENAS = PTA ARENAS
            RANCAGUA = RANCAGUA
            SAN BERNARDO = SAN BRNRDO 
            SAN FERNANDO = SAN FERNAN
            SUB DISTRIBUCION = SUBDISTRIB
            TALCA = TALCA
            TEMUCO = TEMUCO
            VALDIVIA = VALDIVIA
            COLINA = COLINA
            CDD-CD1 = CDD-CD1
            RANCAGUA = RANCAGUA 2
            TALCAHUANO = TALCAHUANO
    ##SALIDA
    - Usar tablas antes que listas, solo listas en caso necesario
    ##PROCESO steps 
    - cuando envies informacion de tu proceso usa este  esquema de markdown
        ####Mensaje adecuado de inicio de tarea####
        + mensaje paso 1  
        + mensaje paso 2 
        + mensaje paso 3 
        + mensaje n 
        * mensaje adecuado para espera del usuario *
        ####mensaje adecuado nueva etapa####
        + mensaje paso 1  
        + mensaje paso 2 
        + mensaje paso 3 
        + mensaje n 
        *mensaje adecuado para espera del usuario*      
    
        """
],
    tools=[
    buscar_cartera,
    ClientesTool(),
    estado_ov,
    DataVentasTool(),
    validar_vendedor,
    CarroTool()
    ],
    show_tool_calls=True,
    reasoning_max_steps=3,
    add_datetime_to_instructions=True,
    add_history_to_messages=True,
    stream=True,
    stream_intermediate_steps=True,
    num_history_responses=6,
    storage=MongoStorage,
    debug_mode=True,
    add_state_in_messages=True,
    perfiles=["1", "5", "9"]
    )

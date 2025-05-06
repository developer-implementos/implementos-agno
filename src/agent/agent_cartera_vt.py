import os
import json
from io import BytesIO
from markdown_pdf import MarkdownPdf
from markdown_pdf import Section
from google.cloud import storage
from agno.agent import Agent
from agno.models.anthropic import Claude
from agno.models.openai import OpenAIChat
from agno.embedder.openai import OpenAIEmbedder
from qdrant_client import QdrantClient
from config.config import Config
from storage.mongo_storage import MongoStorage
from tools.clientes_tool import ClientesTool
from tools.data_ventas_tool import DataVentasTool

embedder = OpenAIEmbedder(id="text-embedding-ada-002")

def buscar_clacom(text: str):
    """Búsqueda de jerarquía de producto: uen, categoria, linea

    Args:
        text (str): texto para buscar jerarquía. Indicar si se busca uen, categoria o linea
    Returns:
        str: Resultados JSON con los documentos más relevantes encontrados
    """
    try:
        qdrant_client = QdrantClient(
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY
        )

        # Obtener el embedding del texto de búsqueda
        query_embedding = embedder.get_embedding(text)

        # Buscar en Qdrant
        results = qdrant_client.search(
            collection_name="clacom",
            query_vector=query_embedding,
            limit=10,
        )

        # Formatear los resultados como lista de diccionarios
        resultsData = [
            {
                "score": hit.score,
                "payload": hit.payload
            } for hit in results
        ]

        if not resultsData:
            return json.dumps([], ensure_ascii=False, indent=2)

        # Convertir a JSON con formato adecuado para caracteres especiales
        json_result = json.dumps(resultsData, ensure_ascii=False, indent=2)
        return json_result

    except Exception as e:
        print(f"Error durante la búsqueda en la base de datos vectorial: {str(e)}")
        return None

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

def upload_to_gcs(pdf_buffer, file_name):
    """
    Sube un archivo PDF a Google Cloud Storage.

    Args:
        pdf_buffer (bytes): Contenido del PDF en bytes
        file_name (str): Nombre del archivo a guardar en GCS

    Returns:
        str: URL pública del archivo subido
    """
    try:
        # Configurar el cliente de almacenamiento
        storage_client = storage.Client.from_service_account_json(
            os.path.join(os.path.dirname(__file__), 'key-storage.json')
        )

        # Definir el nombre del bucket
        bucket_name = 'imagenes_catalogo_publico'

        # Obtener el bucket
        bucket = storage_client.bucket(bucket_name)

        # Crear el objeto blob (archivo) en el bucket
        blob = bucket.blob(file_name)

        # Configurar metadatos del archivo
        blob.content_type = 'application/pdf'
        blob.cache_control = 'no-cache'

        # Subir el contenido del archivo
        blob.upload_from_string(
            pdf_buffer,
            content_type='application/pdf'
        )

        # Generar URL pública
        public_url = f"https://storage.googleapis.com/{bucket_name}/{file_name}"
        return public_url

    except Exception as e:
        print(f"Error al subir el archivo: {str(e)}")
        raise e

def markdown_pdf(
    markdown_content: str,
    title: str = "Informe",
    filename: str = None,
    upload_to_cloud: bool = True
) -> str:
    """
    Convierte datos markdown a PDF y opcionalmente lo sube a Google Cloud Storage

    Args:
        markdown_content (str): datos completos en markdown
        title (str): título del documento PDF
        filename (str, optional): nombre del archivo PDF. Si es None, se genera automáticamente.
        upload_to_cloud (bool): Si es True, sube el archivo a GCS en lugar de guardarlo localmente

    Returns:
        str: URL pública del PDF en GCS o ruta local del archivo PDF
    """
    try:
        print("csdfsadfasfdsfdsfdsfsdfds")
        # Generar nombre de archivo si no se proporciona
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_title = title.replace(' ', '_').replace('/', '-')
            filename = f"{safe_title}_{timestamp}.pdf"
        elif not filename.endswith('.pdf'):
            filename += '.pdf'


        custom_css = """
    @page {
        size: A4 landscape; /* Formato apaisado para mayor ancho */
        margin: 1.5cm; /* Márgenes uniformes */
    }

    body {
        font-family: 'Helvetica', 'Arial', sans-serif;
        font-size: 11pt; /* Tamaño de letra ligeramente reducido para mejor ajuste */
        line-height: 1.4;
        color: #333;
    }

    /* Estilos para títulos */
    h1, h2, h3, h4, h5, h6 {
        page-break-after: avoid; /* Evita saltos de página después de títulos */
        page-break-inside: avoid; /* Evita que un título se divida entre páginas */
    }

    h1 {
        font-size: 20pt;
        color: #1a5276;
        margin-top: 15pt;
        margin-bottom: 10pt;
    }

    h2 {
        font-size: 16pt;
        color: #2874a6;
        margin-top: 12pt;
        margin-bottom: 8pt;
    }

    /* Estilos para tablas optimizados */
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 10pt 0;
        page-break-inside: avoid; /* Intenta evitar que las tablas se corten entre páginas */
        font-size: 10pt; /* Texto más pequeño en tablas para mejor ajuste */
    }

    th {
        background-color: #f2f2f2;
        font-weight: bold;
        text-align: left;
        padding: 6pt;
        border: 1pt solid #ddd;
    }

    td {
        padding: 6pt;
        border: 1pt solid #ddd;
        word-wrap: break-word; /* Permite que el texto se ajuste dentro de las celdas */
        max-width: 250pt; /* Limita el ancho máximo de las celdas */
    }

    tr:nth-child(even) {
        background-color: #f9f9f9;
    }

    /* Otros elementos */
    p {
        margin-bottom: 8pt;
    }

    ul, ol {
        margin-left: 15pt;
        margin-bottom: 8pt;
        page-break-inside: avoid; /* Evita que las listas se corten entre páginas */
    }

    li {
        margin-bottom: 4pt;
    }

    a {
        color: #3498db;
        text-decoration: underline;
    }

    /* Evitar que las imágenes se corten */
    img {
        max-width: 100%;
        page-break-inside: avoid;
    }

    /* Ajuste para códigos y bloques de texto */
    pre, code {
        white-space: pre-wrap; /* Permite que el código se ajuste */
        word-wrap: break-word;
        font-size: 9pt;
    }

    /* Estilos para separadores horizontales */
    hr {
        border: none;
        height: 1pt;
        background-color: #ddd;
        margin: 10pt 0;
        page-break-after: avoid;
    }
    """

    # Crear el documento PDF
        pdf = MarkdownPdf(toc_level=2)

        # Configurar metadatos del documento
        pdf.meta["title"] = title

        # Crear una sección con configuración personalizada
        section = Section(
            text=markdown_content,
            toc=True,
            paper_size="A4",  # Tamaño del papel
            borders=(50, 50, -50, -50)  # Márgenes más amplios para mejor legibilidad
        )

        # Añadir la sección al PDF con el CSS personalizado
        pdf.add_section(section, user_css=custom_css)
            # Añadir la sección con contenido markdown


        if upload_to_cloud:
            # Crear un buffer en memoria para el PDF
            pdf_buffer = BytesIO()
            pdf.save(pdf_buffer)
            pdf_buffer.seek(0)

            # Subir el PDF a Google Cloud Storage
            public_url = upload_to_gcs(pdf_buffer.getvalue(), filename)
            return public_url
        else:
            # Guardar el PDF localmente
            save_path = "./static/pdfs"
            os.makedirs(save_path, exist_ok=True)
            file_path = os.path.join(save_path, filename)
            pdf.save(file_path)
            return str(file_path)

    except Exception as e:
        print(f"Error al generar o subir el PDF: {str(e)}")
        return f"Error: {str(e)}"

instructions = [
        """
Tu trabajo es Analizar exhaustivamente la cartera de clientes de un vendedor específico. Analizar el historial de compra de su cartera utilizando la base de datos implementos y la tabla ventasrealtime en ClickHouse, puedes analizar schemas y realizar querys no uses caracteres en nombres como ñ tildes etc.

### Clasificación y Optimización de Respuestas:
    - PRIMERO: Clasifica cada consulta como SIMPLE o COMPLEJA para optimizar el tiempo de respuesta
        + SIMPLE: Consultas sobre métricas básicas de un vendedor, listados simples, o datos puntuales
        + COMPLEJA: Análisis detallado de cartera, comparaciones, tendencias, segmentaciones avanzadas

    - Para consultas SIMPLES:
        + Ejecuta SOLO las queries necesarias básicas
        + Omite análisis multidimensionales y segmentaciones avanzadas
        + Responde directamente con los datos solicitados en formato tabla
        + Limita los pasos de procesamiento al mínimo necesario
        + Ofrece al final la posibilidad de profundizar: "¿Deseas un análisis más detallado de esta cartera?"

    - Para consultas COMPLEJAS:
        + Realiza el análisis integral y detallado completo

### PASOS DE ANÁLISIS OBLIGATORIOS
    - Buscar Vendedor usando tools:buscar_cartera
    - Obtener el listado de rutCliente válidos del vendedor resultado de la tools:buscar_cartera
    - Definir rango de periodos de análisis exactos (siempre usar periodos comparables)
    - Validar esquema de tabla y realizar las query para el proceso de obtención de información

### INSTRUCCIONES CORE:
    - SIMPLE: Enfócate solo en datos clave solicitados (ventas totales, principales clientes)
    - COMPLEJA: Analiza todos los clientes con enfoque multidimensional y segmentación avanzada
    - Limitar queries solo a los rut de cliente válidos en el listado del vendedor
    - Utilizar queries de agrupación y evitar salidas grandes (LIMIT 200)

### COMPARACIONES TEMPORALES (CRÍTICO):
    - Las comparaciones SIEMPRE deben ser entre períodos equivalentes y proporcionales:
        + Para comparaciones de año actual: Utilizar exactamente el mismo rango de fechas del año anterior
        + Para comparaciones mensuales: Si el mes actual está incompleto, comparar con los mismos días del mes anterior
        + Para comparaciones contra mismo período del año anterior: Usar exactamente las mismas fechas
        + Para comparaciones semanales: Usar los mismos días de ambas semanas
    - NUNCA COMPARAR:
        + Un período parcial contra un período completo
        + Año parcial actual contra todo el año anterior completo
        + Mes parcial actual contra mes anterior completo
        + Cualquier comparación que no mantenga la misma proporción temporal
    - Siempre aclarar en los resultados el período exacto que se está comparando

### Análisis integral de cartera (SOLO para consultas COMPLEJAS):
    - Volumen total de ventas y margen de la cartera (actual vs. periodos anteriores)
    - Distribución de ventas por cliente (concentración de cartera)
    - Frecuencia de compra de los clientes (patrones y regularidad)
    - Evolución temporal de la cartera (crecimiento o decrecimiento con análisis de causas)
    - Top 5 mejores clientes (con análisis de características comunes)
    - Top 5 peores clientes (con diagnóstico de problemas específicos)
    - Clientes con baja venta y posible riesgo de fuga
    - Análisis de estacionalidad en el comportamiento de compra

### Segmentación avanzada de clientes (SOLO para consultas COMPLEJAS):
    - Clientes de alta venta: Identifica el top 20% que genera el 80% de la venta (análisis Pareto)
    - Clientes inactivos: Sin compras en los últimos 3 meses
    - Clientes nuevos: Primera compra en los últimos 6 meses
    - Clientes en riesgo: Disminución de compras >20% respecto al mismo periodo anterior

### Análisis de productos y categorías (SOLO para consultas COMPLEJAS):
    - Concentración de ventas por UEN, Categoría y Línea
    - SKU más vendidos por el vendedor vs. promedio de la empresa
    - Oportunidades de venta cruzada
    - Top 5 productos más vendidos con UEN

### Métricas de desempeño:
    - SIMPLE: Solo las métricas básicas solicitadas
    - COMPLEJA: Análisis completo de métricas avanzadas (margen, ticket promedio, retención, etc.)

### Reglas críticas para consultas ClickHouse:
    - No uses en campos de salida Ñ o tildes en nombres
    - FUNDAMENTAL: Toda columna en SELECT sin función de agregación DEBE estar exactamente igual en GROUP BY
    - CAMPOS CALCULADOS: Nunca referenciar directamente campos calculados que no existan físicamente en la tabla
        + CORRECTO: SUM(totalMargenItem) / nullIf(SUM(totalNetoItem), 0) * 100 AS margen_porcentual
        + INCORRECTO: SELECT sku, margen_porcentual FROM tabla GROUP BY sku

    - DICCIONARIO DE CAMPOS CALCULADOS:
        + margen: "totalMargenItem"
        + margenPorcentual: "((totalMargenItem) / nullIf(totalNetoItem, 0)) * 100"
        + descuentoPorcentual: "(descuento / nullIf(totalNetoItem + descuento, 0)) * 100"
        + monto: "totalNetoItem"
        + cantidad_ventas: "uniqExact(documento)"
        + cantidad_vendida: "sum(cantidad)"

    - TRANSFORMACIONES DE FECHAS: No aplicar funciones de transformación directamente en GROUP BY
    - FILTROS BÁSICOS: Aplicar siempre sucursal != '' y tipoVenta != '' en todas las consultas
    - VALORES ÚNICOS: Usar siempre uniqExact() en lugar de COUNT(DISTINCT)
    - ERRORES DE DIVISIÓN: Usar nullIf() para evitar divisiones por cero
    - SUBCONSULTAS: Para reutilizar campos calculados, hacerlo mediante subconsulta o CTE, nunca directamente

### Manejo de fechas en ClickHouse:
    - ERROR CRÍTICO: Las fechas deben convertirse a string antes de devolverse para evitar errores de serialización JSON
        + SIEMPRE usar toString() para cualquier campo de tipo fecha en el SELECT final
        + CORRECTO: SELECT toString(toDate(fecha)) AS fecha_venta, SUM(totalNetoItem) AS venta
        + INCORRECTO: SELECT toDate(fecha) AS fecha_venta, SUM(totalNetoItem) AS venta

    - Para agrupaciones por períodos, convertir a string solo en el SELECT final:
        + Por mes: toString(toStartOfMonth(fecha)) AS mes
        + Por trimestre: toString(toStartOfQuarter(fecha)) AS trimestre
        + Por año: toString(toYear(fecha)) AS anio

### Formato de presentación:
    - SIEMPRE muestra listados de datos en formato de tablas
    - Incluye Totales y usa punto como separador de miles
    - Utiliza títulos claros y directos relacionados con la consulta específica
    - Muestra los periodos de análisis inicio - fin

### Proceso y comunicación:
- Todo proceso interno de consulta debe ser invisible para el usuario
- Errores en el proceso de uso de tools no deben ser informados al usuario
- No indique la clasificacion al usuario de su pregunta (SIMPLES-COMPLEJAS) en cambio puedes indicar
    - te dare la informacion precisa que necesitas. O similares a este ejemplo
    - realizare un analisis para entregar un mejor respuestas. O similares a este ejemplo

### Evita errores:
    - Prefiere querys con agrupación y LIMIT 200
    - Limita queries solo a los rut de cliente válidos del vendedor
    - Ante ambigüedades solicita datos específicos (períodos, vendedor específico)
    - ERROR CRÍTICO: Nunca compares períodos completos con parciales
"""
    ]

Agente_Cartera_Vt = Agent(
    name="Especialista Carteras VT",
    agent_id="vendedores_terreno_01",
    model=OpenAIChat(id="gpt-4.1",api_key=Config.OPENAI_API_KEY,temperature=0.2),
    description="Eres un agente especializado en el área de ventas de Implementos Chile. Enfocado en realizar análisis detallados de carteras de vendedores, proporcionando información útil y estratégica para jefaturas de Venta.",
    instructions=instructions,
    tools=[DataVentasTool(),ClientesTool(),buscar_cartera,markdown_pdf,buscar_clacom],
    add_datetime_to_instructions=True,
    add_history_to_messages=True,
    num_history_responses=6,
    markdown=True,
    stream=True,
    debug_mode=False,
    storage=MongoStorage,
    perfiles=["1", "3", "5", "9"]
)

Agente_Cartera_Vt_DeepSearch = Agent(
    name="Especialista Carteras VT",
    agent_id="vendedores_terreno_01_deepsearch",
    model=Claude(id="claude-3-7-sonnet-20250219",temperature=0.2,api_key=Config.ANTHROPIC_API_KEY),
    description="Eres un agente especializado en el área de ventas de Implementos Chile. Enfocado en realizar análisis detallados de carteras de vendedores, proporcionando información útil y estratégica para jefaturas de Venta.",
    instructions=instructions,
    tools=[DataVentasTool(),ClientesTool(),buscar_cartera,markdown_pdf,buscar_clacom],
    add_datetime_to_instructions=True,
    add_history_to_messages=True,
    num_history_responses=6,
    markdown=True,
    stream=True,
    debug_mode=False,
    storage=MongoStorage,
    perfiles=[]
)



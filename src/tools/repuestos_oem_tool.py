import json
import requests
import time
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
from openai import OpenAI
import concurrent.futures
from duckduckgo_search import DDGS
from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger
import clickhouse_connect
from databases.clickhouse_client import config

class RepuestosOemTool(Toolkit):
    def __init__(self):
        super().__init__(name="repuestos_oem_tool")
        # Registrar las funciones en el toolkit para que sean accesibles dinámicamente
        self.register(self.find_by_vin)
        self.register(self.find_categories)
        self.register(self.find_detail_categorie)
        self.register(self.buscar_y_extraer_info_repuestos)
        self.register(self.run_select_query)
        self.register(self.search_crossference_oem)
        self.cliente = OpenAI()
        self._cache = {}
        self._cache_ttl = {}  # Time-to-live para cada elemento en caché
        self._default_ttl = 3600  # 1 hora por defecto
        
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Obtiene un valor de la caché si existe y no ha expirado"""
        if key in self._cache and key in self._cache_ttl:
            if self._cache_ttl[key] > time.time():
                log_debug(f"Cache hit: {key}")
                return self._cache[key]
            else:
                # Eliminar entrada expirada
                del self._cache[key]
                del self._cache_ttl[key]
        return ""
        
    def _save_to_cache(self, key: str, value: Any, ttl: int = None) -> None:
        """Guarda un valor en la caché con un tiempo de expiración"""
        ttl = ttl or self._default_ttl
        self._cache[key] = value
        self._cache_ttl[key] = time.time() + ttl
        log_debug(f"Saved to cache: {key}")
    def create_clickhouse_client(self):
        """Crea y devuelve un cliente de ClickHouse utilizando la configuración"""
        client_config = config.get_client_config()
        try:
            client = clickhouse_connect.get_client(**client_config)
            # Probar la conexión
            version = client.server_version
            return client
        except Exception as e:
            print(f"Error al conectar a ClickHouse: {e}")
            raise

    def find_by_vin(self, vin: str):
        """
        Función para buscar un catálogo original de un VIN de vehículo.
        
        Args:
            vin (str): alfanumérico de 17 caracteres 
            
        Returns:
            str: Resultado de la consulta con los datos principales (Ssd, Catalog, VehicleId, Kind).
        """
        try:
            # Validar formato de VIN
            if not vin or len(vin) != 17 or not vin.isalnum():
                return json.dumps({"error": "VIN inválido. Debe ser alfanumérico de 17 caracteres."}, ensure_ascii=False)
                
            # Verificar en caché
            cache_key = f"vin_{vin}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                return cached_result
            
            # URL de la API de precios
            api_url = f"https://www.etsp.by/Details/OriginalCatalog.ashx?action=FindVehicleByVIN&vin={vin}"
            log_debug(f"Consultando VIN: {api_url}")
            
            # Configurar los headers
            headers = {
                "x-requested-with": "XMLHttpRequest",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            # Realizar la solicitud GET con timeout
            response = requests.get(api_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                # Convertir la respuesta a JSON
                result = response.json()
                formatted_result = json.dumps(result, ensure_ascii=False, indent=2)
                
                # Guardar en caché por 24 horas (los VIN no cambian)
                self._save_to_cache(cache_key, formatted_result, ttl=86400)
                
                return formatted_result
            else:
                error_msg = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_msg)
                return json.dumps({"error": error_msg}, ensure_ascii=False)
        except requests.exceptions.Timeout:
            error_msg = f"Timeout al consultar VIN: {vin}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)
        except requests.exceptions.RequestException as e:
            error_msg = f"Error de conexión al consultar VIN: {str(e)}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)
        except Exception as e:
            error_msg = f"Error al consultar VIN: {str(e)}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)
    
    def find_categories(self, Catalog: str, Ssd: str, VehicleId: str, Kind: str):
        """
        Analiza el árbol de categorías de un catálogo y busca lo que es más compatible con la búsqueda.
        
        Args:
            Catalog (str): Catalog del vin 
            Ssd (str): Ssd del vin 
            VehicleId (str): vehiculoId del vehiculo 
            Kind (str): kind validador
            
        Returns:
            str: categorías más relevantes según la consulta.
        """
        try:
            # Verificar parámetros
            if not all([Catalog, Ssd, VehicleId, Kind]):
                return json.dumps({"error": "Parámetros incompletos. Se requieren: Catalog, Ssd, VehicleId y Kind."}, ensure_ascii=False)
                
            # Verificar en caché
            cache_key = f"categories_{Catalog}_{Ssd}_{VehicleId}_{Kind}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                return cached_result
                
            api_url = f"https://www.etsp.by/Details/OriginalCatalog.ashx?action=GetQuickGroups&code={Catalog}&vehicleId={VehicleId}&ssd={Ssd}&kind={Kind}"
            log_debug(f"Consultando categorías: {api_url}")   
            
            # Configurar los headers
            headers = {
                "x-requested-with": "XMLHttpRequest",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            # Realizar la solicitud GET con timeout y reintentos
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    response = requests.get(api_url, headers=headers, timeout=15)
                    
                    if response.status_code == 200:
                        result = response.json()
                        linked_categories = self.extract_linked_categories(result["data"])
                        formatted_result = json.dumps(linked_categories, ensure_ascii=False, indent=2)
                        
                        # Guardar en caché por 12 horas (categorías son relativamente estables)
                        self._save_to_cache(cache_key, formatted_result, ttl=43200)
                        
                        return formatted_result
                    elif response.status_code == 429:  # Too Many Requests
                        retry_count += 1
                        wait_time = 2 ** retry_count  # Backoff exponencial
                        time.sleep(wait_time)
                    else:
                        return json.dumps({"error": f"Error en la solicitud: {response.status_code} - {response.text}"}, ensure_ascii=False)
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                    retry_count += 1
                    wait_time = 2 ** retry_count
                    time.sleep(wait_time)
                    
            return json.dumps({"error": "Error después de múltiples reintentos"}, ensure_ascii=False)
        except Exception as e:
            error_msg = f"Error al buscar categorías: {str(e)}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)

    def find_detail(self, Catalog: str, Ssd: str, quickGroupId: str, VehicleId: str, Kind: str):
        """
        Muestra el detalle de una unidad y sus piezas OEM basados en una búsqueda de repuesto o problemas mecanicos.
        
        Args:
            busqueda (str): Objetivo de la búsqueda 
            Catalog (str): Catalog del vin
            Ssd (str): Ssd del vin
            quickGroupId (str): id de la categoría
            VehicleId (str): VehicleId del vehiculo
            Kind (str): kind validador
            
        Returns:
            str: Resultado de la consulta con los datos de la unidad y sus items según la consulta.
        """
        try:
            # URL de la API de precios
            api_url = f"https://www.etsp.by/Details/OriginalCatalog.ashx?action=GetQuickDetails&code={Catalog}&vehicleId={VehicleId}&ssd={Ssd}&quickGroupId={quickGroupId}&kind={Kind}"
            print(api_url)
            # Configurar los headers
            headers = {
                "x-requested-with": "XMLHttpRequest"
            }
            
            # Realizar la solicitud GET
            response = requests.get(api_url, headers=headers)
            
            if response.status_code == 200:
                # Convertir la respuesta a JSON
                result = response.json()
                # Crear el nuevo formato de datos
                parsed_data = {"data": []}
                
                if result.get("status") == "success" and "data" in result:
                    for category in result["data"]:
                        new_category = {
                            "name": category.get("Name", ""),
                            "Units": []
                        }
                        
                        for unit in category.get("Units", []):
                            new_unit = {
                                "ImageUrl": unit.get("LargeImageUrl", ""),
                                "Name": unit.get("Name", ""),
                                "Parts": ""  # Inicializamos como string vacío en lugar de lista
                            }
                            
                            parts_info = []  # Lista temporal para almacenar información concatenada
                            
                            for detail in unit.get("Details", []):
                                # Concatenamos la información relevante
                                part_text = f"{detail.get('Name', '')}: OEM {detail.get('OEM', '')}, Cant. {detail.get('Amount', '')}, Pos. {detail.get('CodeOnImage', '')}"
                                
                                # Añadimos la nota si existe
                                if detail.get("Note"):
                                    part_text += f", Nota: {detail.get('Note', '')}"
                                
                                parts_info.append(part_text)
                            
                            # Unimos toda la información con separadores
                            new_unit["Parts"] = " | ".join(parts_info)
                            
                            new_category["Units"].append(new_unit)
                            
                        parsed_data["data"].append(new_category)
                formatted_result = json.dumps(parsed_data, ensure_ascii=False, indent=2)                       
                return formatted_result
            else:
                return f"Error en la solicitud: {response.status_code} - {response.text}"
                
        except Exception as e:
            error_msg = f"Error al buscar detalles de categoría: {str(e)}"
            logger.error(error_msg)
            return error_msg

    def find_detail_categorie(self, Catalog: str, Ssd: str, VehicleId: str, Kind: str, quickGroups: List[dict]):
        """
        Muestra el detalle de una unidad y sus piezas OEM de un listado de grupos de categorias.
        
        Args:
            Catalog (str): Catalog del vin
            Ssd (str): Ssd del vin
            VehicleId (str): VehicleId del vehiculo
            Kind (str): kind validador
            quickGroups (List): listado de grupos de categoria con [{"quickGroupId": "", "name": ""},{"quickGroupId": "", "name": ""},{"quickGroupId": "", "name": ""},....]
            
        Returns:
            str: Resultado de la consulta con los datos piezas del catalogo.
        """
        try:
            # Verificar parámetros
            if not all([Catalog, Ssd, VehicleId, Kind]) or not quickGroups:
                return json.dumps({"error": "Parámetros incompletos o inválidos."}, ensure_ascii=False)
                
            # Limitar la cantidad de categorías a procesar para evitar sobrecarga
            max_categories = 10
            if len(quickGroups) > max_categories:
                log_info(f"Limitando búsqueda a {max_categories} categorías más relevantes de {len(quickGroups)} totales")
                quickGroups = quickGroups[:max_categories]
                
            # Inicializamos la lista para almacenar los detalles
            detalles_categorias = []
            
            # Lista para almacenar categorías que necesitan procesamiento (no están en caché)
            categorias_a_procesar = []
            
            # Primero verificamos qué categorías están en caché
            for categoria in quickGroups:
                quickGroupId = categoria.get("quickGroupId")
                nombre_categoria = categoria.get("name", "")
                cache_key = f"detail_{Catalog}_{Ssd}_{quickGroupId}_{VehicleId}_{Kind}"
                detalle_cacheado = self._get_from_cache(cache_key)
                
                if detalle_cacheado:
                    detalles_categorias.append({
                        "categoria": nombre_categoria,
                        "quickGroupId": quickGroupId,
                        "detalle": detalle_cacheado
                    })
                else:
                    categorias_a_procesar.append(categoria)
            
            # Si hay categorías para procesar, las procesamos en paralelo
            if categorias_a_procesar:
                # Función para procesar una categoría y obtener sus detalles
                def procesar_categoria(categoria):
                    quickGroupId = categoria.get("quickGroupId")
                    nombre_categoria = categoria.get("name", "")
                    cache_key = f"detail_{Catalog}_{Ssd}_{quickGroupId}_{VehicleId}_{Kind}"
                    
                    try:
                        # Obtener detalle con timeout
                        detalle = self.find_detail(Catalog, Ssd, quickGroupId, VehicleId, Kind)
                        # Guardar en caché
                        self._save_to_cache(cache_key, detalle, ttl=43200)  # 12 horas
                        
                        return {
                            "categoria": nombre_categoria,
                            "quickGroupId": quickGroupId,
                            "detalle": detalle,
                            "status": "success"
                        }
                    except Exception as e:
                        return {
                            "categoria": nombre_categoria,
                            "quickGroupId": quickGroupId,
                            "detalle": json.dumps({"error": f"Error: {str(e)}"}, ensure_ascii=False),
                            "status": "error"
                        }
                
                # Usamos ThreadPoolExecutor con más workers y mejor manejo de errores
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(categorias_a_procesar))) as executor:
                    # Creamos un futuro para cada categoría
                    futuros = {executor.submit(procesar_categoria, categoria): categoria for categoria in categorias_a_procesar}
                    
                    # Manejamos los timeouts para cada futuro
                    for futuro in concurrent.futures.as_completed(futuros, timeout=30):
                        try:
                            resultado = futuro.result()
                            detalles_categorias.append(resultado)
                        except concurrent.futures.TimeoutError:
                            categoria = futuros[futuro]
                            detalles_categorias.append({
                                "categoria": categoria.get("name", ""),
                                "quickGroupId": categoria.get("quickGroupId"),
                                "detalle": json.dumps({"error": "Timeout al procesar la categoría"}, ensure_ascii=False),
                                "status": "timeout"
                            })
                        except Exception as e:
                            categoria = futuros[futuro]
                            detalles_categorias.append({
                                "categoria": categoria.get("name", ""),
                                "quickGroupId": categoria.get("quickGroupId"),
                                "detalle": json.dumps({"error": f"Error inesperado: {str(e)}"}, ensure_ascii=False),
                                "status": "error"
                            })
            
            # Ordenar resultados por categoría para mantener consistencia
            detalles_categorias.sort(key=lambda x: x.get("categoria", ""))
            
            resultados_formateados = json.dumps(detalles_categorias, ensure_ascii=False, indent=2)
            return resultados_formateados
            
        except Exception as e:
            error_msg = f"Error al procesar búsqueda paralela: {str(e)}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)
    
    def extract_linked_categories(self, categories, parent_names=None):
        """
        Función recursiva para extraer categorías con link=true y añadir información estructurada.
        
        Args:
            categories (list): Lista de categorías para procesar
            parent_names (list): Lista de nombres de categorías padre
            
        Returns:
            list: Lista plana de categorías enlazadas con información estructurada
        """
        if parent_names is None:
            parent_names = []
        
        result = []
        
        for category in categories:
            # Crear copia de la lista de padres para este nivel
            current_parents = parent_names.copy()
            
            # Si la categoría tiene link=true, agregarla al resultado
            if category.get('Link') == True:
                result.append({
                    'QuickGroupId': category['QuickGroupId'],
                    'Name': category['Name'],
                    'FullPath': ' > '.join(current_parents + [category['Name']])
                })
            
            # Agregar esta categoría a la lista de padres para sus hijos
            new_parents = current_parents + [category['Name']]
            
            # Procesar recursivamente los hijos si existen
            if category.get('Childs') and isinstance(category['Childs'], list):
                child_results = self.extract_linked_categories(category['Childs'], new_parents)
                result.extend(child_results)
        
        return result

    def clean_response_data(self, data):
        """
        Elimina los campos QuickGroupId y categoryId de la estructura de datos.
        
        Args:
            data (dict): Datos a limpiar
            
        Returns:
            dict: Datos limpios
        """
        if "Categories" in data:
            for category in data["Categories"]:
                # Eliminamos QuickGroupId de la categoría
                if "QuickGroupId" in category:
                    del category["QuickGroupId"]
                
                # Procesamos Details si existen
                if "Details" in category:
                    for detail in category["Details"]:
                        # Eliminamos categoryId de los detalles
                        if "categoryId" in detail:
                            del detail["categoryId"]
        return data

    def buscar_y_extraer_info_repuestos(self, query: str, busqueda_detalle: str = ""):
        """
        Busca repuestos o información de problemas mecánicos o casos similares a la pregunta del usuario
        
        Args:
            query (str): La consulta para la búsqueda inicial
            busqueda_detalle (str, opcional): Detalle específico a extraer de cada página. 
                                              Si es None, usará la consulta original.
        
        Returns:
            dict: Un diccionario con la consulta original, las URLs y la información extraída
        """
        try:
            # Si no se especifica el detalle de búsqueda, usar la consulta original
            if not busqueda_detalle:
                busqueda_detalle = f"Información sobre {query} en el contexto de repuestos o mecánica automotriz"
            
            # 1. Obtener las 3 URLs más relevantes
            urls = self._search_web_repuestos(query)
            
            if isinstance(urls, str):
                # Procesar la respuesta en texto para extraer solo las URLs
                urls_list = []
                for line in urls.strip().split('\n'):
                    if line.startswith('http'):
                        urls_list.append(line.strip())
                    
                if not urls_list and 'http' in urls:
                    # Intenta extraer URLs si están en un formato diferente
                    import re
                    urls_list = re.findall(r'https?://[^\s]+', urls)
            else:
                # Si ya es una lista (aunque esto no debería ocurrir según la función original)
                urls_list = urls
                
            # 2. Extraer información de cada URL en paralelo
            resultados = self._extraer_info_paralelo(urls_list, busqueda_detalle)
            
            # 3. Generar un resumen consolidado
            resumen = self._generar_resumen(query, resultados,urls_list)
            resultados_formateados = json.dumps(resumen, ensure_ascii=False, indent=2)
            return resultados_formateados
            
        except Exception as e:
            error_msg = f"Error al procesar la solicitud completa: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "resultados": []}
    
    def _search_web_repuestos2(self, query: str):
        """
        Realiza una búsqueda en internet sobre un tema específico de repuestos o problemas mecánicos.
        
        Args:
            query (str): La consulta de búsqueda
            
        Returns:
            str: Listado de URL relevantes para la búsqueda.
        """
        try:    
            # Construir la consulta
            query_with_exclusions = query
                
            # Inicializar el cliente de DuckDuckGo
            with DDGS() as ddgs:
                # Realizar la búsqueda
                resultados = list(ddgs.text(query_with_exclusions, region="cl", max_results=10))
                
                # Obtener URLs y metadatos relevantes
                processed_results = []
                for resultado in resultados:
                    if resultado.get("href"):
                        # Extraer el dominio para categorización
                        url = resultado.get("href", "")
                        domain = url.split("//")[-1].split("/")[0]
                        
                        processed_results.append({
                            "url": url,
                            "title": resultado.get("title", ""),
                            "snippet": resultado.get("body", ""),
                            "domain": domain
                        })
                
                # Agrupar por dominio para análisis más estructurado
                domains_found = {}
                for item in processed_results:
                    domain = item["domain"]
                    if domain not in domains_found:
                        domains_found[domain] = []
                    domains_found[domain].append(item)
                
                # Estructura final de resultados
                final_result = {
                    "query": query,
                    "results": processed_results,
                    "domains_summary": {domain: len(items) for domain, items in domains_found.items()},
                    "total_results": len(processed_results)
                }
                prompt = f"""
                        selecciona solo las  principales url del listado segun la solicitud                
                        basado en esta informacion : {query}
                        {final_result} 

                        responde claramente solo la lista de las url realmente relevantes para analisis.
                        """
                respuesta = self.cliente.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=[
                        {"role": "system", "content": "Eres un asistente especializado en extraer información específica."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1
                )
                return respuesta.choices[0].message.content
                    
        except Exception as e:
            error_msg = f"Error al realizar la búsqueda: {str(e)}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg, "results": []})
    def _search_web_repuestos(self, query: str):
        """
        Realiza una búsqueda en internet sobre un tema específico de repuestos o problemas mecánicos.
        
        Args:
            query (str): La consulta de búsqueda
            
        Returns:
            str: Listado de URL relevantes para la búsqueda.
        """
        try:    
            # Construir la consulta
                
            prompt = f"""
                        {query} dame solo las url
                        """
            respuesta = self.cliente.responses.create(
                    model="gpt-4.1",
                    input=[
                        {
                        "role": "system",
                        "content": [
                            {
                            "type": "input_text",
                            "text": "responde en json \n{\nurl:[\"listado de urls\"]\n}\n"
                            }
                        ]
                        },
                        {
                        "role": "user",
                        "content": [
                            {
                            "type": "input_text",
                            "text": prompt
                            }
                        ]
                        }],
                                            text={
                            "format": {
                            "type": "text"
                            }
                        },
                    tools=[
                        {
                        "type": "web_search_preview",
                        "user_location": {
                            "type": "approximate",
                            "country": "CL"
                        },
                        "search_context_size": "medium"
                        }
                    ],
                    temperature=0.1
                )
            print(respuesta)
            return respuesta.output[1].content[0].text
                    
        except Exception as e:
            error_msg = f"Error al realizar la búsqueda: {str(e)}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg, "results": []})
    
    def _extraer_texto_web_repuestos(self, url: str, busqueda: str):
        """
        Extrae información específica de una página web basada en una búsqueda
        usando Beautiful Soup para analizar solo el body y eliminar scripts.
        
        Args:
            url (str): URL para extraer información
            busqueda (str): Requerimiento específico de información a extraer
        
        Returns:
            str: Información extraída y procesada por IA.
        """
        try:
            # Obtener el contenido de la URL
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            
            if not response.ok:
                return f"No se pudo acceder a la URL {url}. Código de estado: {response.status_code}"
            
            # Usar Beautiful Soup para analizar el HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Eliminar todos los scripts
            for script in soup.find_all('script'):
                script.decompose()
                
            # Eliminar todos los estilos CSS
            for style in soup.find_all('style'):
                style.decompose()
                
            # Obtener solo el contenido del body
            body = soup.body
            
            if not body:
                return f"No se pudo encontrar el elemento body en la página web: {url}"
            
            # Extraer el texto limpio
            texto_extraido = body.get_text(separator=' ', strip=True)
            
            # Limitar el texto a un tamaño razonable para la API
            max_texto = 15000  # Ajusta según necesidad y límites de la API
            if len(texto_extraido) > max_texto:
                texto_extraido = texto_extraido[:max_texto] + "..."
                
            # Crear un prompt para GPT-4.1 mini
            prompt = f"""
            Estoy analizando una página web y necesito extraer información específica.
            
            Contenido de la página web ({url}):
            {texto_extraido} 
            
            Por favor, extrae la siguiente información:
            {busqueda}
            
            Devuelve solo la información solicitada de manera concisa y estructurada.
            No menciones limitaciones en el texto o que solo estás analizando una parte.
            
            inicia con la url analizada
            Salida: sin mensajes adicionales 
                url:"",
                informacion:""
            """
            
            # Realizar la consulta a GPT-4.1 mini
            respuesta = self.cliente.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "Eres un asistente especializado en extraer información específica del área de repuestos de vehículos."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            
            # Devolver la respuesta generada con información de la fuente
            return  respuesta.choices[0].message.content
 
        except Exception as e:
            error_msg = f"Error al procesar la URL {url}: {str(e)}"
            logger.error(error_msg)
            return {"url": url, "error": error_msg}
    
    def _extraer_info_paralelo(self, urls, busqueda_detalle):
        """
        Extrae información de múltiples URLs en paralelo usando ThreadPoolExecutor
        
        Args:
            urls (list): Lista de URLs a analizar
            busqueda_detalle (str): Detalle de la información a extraer
            
        Returns:
            list: Lista con los resultados de cada URL
        """
        resultados = []
        
        # Usar ThreadPoolExecutor para el procesamiento en paralelo
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # Crear un futuro para cada URL
            future_to_url = {
                executor.submit(self._extraer_texto_web_repuestos, url, busqueda_detalle): url 
                for url in urls
            }
            
            # Recolectar resultados a medida que se completan
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    resultado = future.result()
                    resultados.append(resultado)
                except Exception as e:
                    logger.error(f"Error procesando {url}: {str(e)}")
                    resultados.append({
                        "url": url,
                        "error": f"Error durante el procesamiento: {str(e)}"
                    })
        
        return resultados
    
    def _generar_resumen(self, query, resultados, urls):
        """
        Genera un resumen consolidado basado en la información extraída de múltiples fuentes
        
        Args:
            query (str): La consulta original
            resultados (list): Lista de resultados de la extracción
            urls (list): Lista de URLs a analizadas
        Returns:
            str: Resumen consolidado
        """
        try:
            # Preparar la información para el resumen
            informacion_consolidada = resultados
                    
            # Crear un prompt para generar el resumen
            prompt = f"""
            He recopilado información de varias fuentes sobre la consulta: "{query}"
            
            Información de las fuentes:
            {informacion_consolidada}
            
            Por favor, genera un resumen consolidado que integre la información más relevante y precisa.
            El resumen debe ser completo pero conciso (máximo 500 palabras), organizado y fácil de entender.
            Menciona las fuentes usadas en el resumen {urls}
            """
            
            # Generar el resumen con IA
            respuesta = self.cliente.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "Eres un asistente especializado en sintetizar información técnica del área automotriz y repuestos."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            
            return respuesta.choices[0].message.content
            
        except Exception as e:
            error_msg = f"Error al generar el resumen: {str(e)}"
            logger.error(error_msg)
            return f"No se pudo generar el resumen: {error_msg}"

    def execute_query(self, query: str):
        try:
            client = self.create_clickhouse_client()
            res = client.query(query, settings={"readonly": 1})
            column_names = res.column_names
            rows = []
            for row in res.result_rows:
                row_dict = {}
                for i, col_name in enumerate(column_names):
                    row_dict[col_name] = row[i]
                rows.append(row_dict)
            return rows
        except Exception as err:
            return f"error running query: {err}"
    def search_crossference_oem(self, oem: str) -> str:
        """
        Información de códigos compatibles de un número OEM en marcas crossreference
        
        Args:
            oem (str): OEM de ítem repuesto
            
        Returns:
            str: Resultado de la consulta con solo articleNumber, mfrName y genericArticleDescription.
        """
        try:
            # URL de la API de precios
            api_url = "https://b2b-api.implementos.cl/api/pim/tecdoc/consultaReferencia"
            
            # Preparar los datos para la solicitud POST
            body = {
                "text": oem
            }
            
            # Configurar los headers
            headers = {
                "Content-Type": "application/json",
                "authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            # Realizar la solicitud POST
            response = requests.post(api_url, headers=headers, json=body)
            
            # Verificar si la solicitud fue exitosa
            if response.status_code == 200:
                # Convertir la respuesta a JSON
                result = response.json()
                
                # Extraer solo los campos requeridos
                simplified_data = []
                for item in result.get('data', []):
                    generic_desc = ""
                    if item.get('genericArticles') and len(item['genericArticles']) > 0:
                        generic_desc = item['genericArticles'][0].get('genericArticleDescription', "")
                    
                    simplified_data.append({
                        "articleNumber": item.get('articleNumber', ""),
                        "mfrName": item.get('mfrName', ""),
                        "genericArticleDescription": generic_desc
                    })
                
                formatted_result = json.dumps(simplified_data, ensure_ascii=False, indent=2)
                log_debug(f"Referencias cruzadas para OEM {oem} consultadas correctamente: {formatted_result}")
                return formatted_result
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_message)
                return error_message
        
        except Exception as e:
            logger.warning(f"Error al consultar referencias cruzadas para OEM {oem}: {e}")
            return f"Error: {e}"
    def run_select_query(self, query: str):
        """Use Run a SELECT query in a ClickHouse database

        Args:
            query (srt): query sql para click house sin texto, sin saltos de linea ni textoadicional solo query.

        Returns:
            str: JSON data result.
        """
        try:
            result = self.execute_query(query)
            json_result = json.dumps(result, ensure_ascii=False, indent=2)
            return json_result
        
        except Exception as err:
            return f"Queries taking longer currently not supported."
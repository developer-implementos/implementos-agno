import requests
import json
from typing import List
from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger
from qdrant_client import QdrantClient
from agno.embedder.openai import OpenAIEmbedder
from openai import OpenAI
from pymongo import MongoClient
from config.config import Config

class EcommerceTool(Toolkit):
    def __init__(self):
        super().__init__(name="ecommerce_tool")
        # Registrar las funciones en el toolkit para que sean accesibles dinámicamente.
        self.register(self.search_matriz_sku)
        self.register(self.search_relacionados_sku)
        self.register(self.search_sku)
        self.register(self.buscar_productos_patente)
        self.register(self.buscar_producto)
        self.register(self.search_crossference_oem)
        self.register(self.buscar_crossreference_oem)
        self.register(self.informacion_tiendas)
        self.register(self.informacion_implementos)

    def buscar_producto(self, text: str, codigoTienda: str = "SAN BRNRDO") -> str:
        """
        Búsqueda de productos por un texto determinado, búsqueda semántica
        
        Args:
            text (str): texto para buscar producto
            codigoTienda (str, optional): Sucursal para la consulta de precios.
            
        Returns:
            str: Resultado de la consulta en formato JSON.
        """
        try:
            embedder = OpenAIEmbedder(id="text-embedding-ada-002")
            qdrant_client = QdrantClient(
                url=Config.QDRANT_URL,
                api_key=Config.QDRANT_API_KEY
            )
            
            query_embedding = embedder.get_embedding(text)
            results = qdrant_client.search(
                collection_name="productos",
                query_vector=query_embedding,
                limit=10,
                score_threshold=0.75
            )
            
            resultsData = [
                {
                    "score": hit.score,
                    "payload": hit.payload
                } for hit in results
            ]
            
            skus = [product["payload"]["sku"] for product in resultsData]
            if not skus:
                empty_result = json.dumps([], ensure_ascii=False, indent=2)
                log_debug(f"No se encontraron productos para la búsqueda: {text}")
                return empty_result
            
            price_data_json = self.prices(skus, codigoTienda)
            price_data = json.loads(price_data_json)
            price_dict = {item["sku"]: item for item in price_data}
            
            # Lista para almacenar los resultados combinados
            combined_results = []
            for product in resultsData:
                sku = product["payload"]["sku"]
                product_info = {
                    "sku": sku,
                    "nombre": product["payload"]["cleaned_text"],
                    "marca": product["payload"]["marca"],
                    "descripcion": product["payload"]["descripcion"],
                    "categoria": product["payload"]["categoria"],
                    "imagen": "https://images.implementos.cl/img/450/"+sku+"-1.jpg",
                    "score": product["score"]
                }
                
                # Verificar si tenemos información de precios para este SKU
                if sku in price_dict:
                    price_info = price_dict[sku]
                    product_info.update({
                        "precio": price_info["precioCliente"]
                    })
                else:
                    # Si no hay información de precio, establecer valores predeterminados
                    product_info.update({
                        "precio": "No disponible"
                    })
                
                combined_results.append(product_info)
            
            json_result = json.dumps(combined_results, ensure_ascii=False, indent=2)
            log_debug(f"Búsqueda de productos para '{text}' completada correctamente: {json_result}")
            return json_result
        
        except Exception as e:
            error_message = f"Error durante la búsqueda en la base de datos vectorial: {str(e)}"
            logger.warning(error_message)
            return f"Error: {e}"
   
    def search_matriz_sku(self, sku: str) -> str:
        """
        Información de Productos equivalentes/similares o matriz de un SKU específico.
        
        Args:
            sku (str): SKU de producto para buscar sus equivalentes o matriz.
            
        Returns:
            str: Resultado de la consulta en formato JSON.
        """
        try:
            api_url = "https://b2b-api.implementos.cl/api/catalogo/matrizproducto"
            
            params = {
                "sku": sku
            }
            
            headers = {
                "Content-Type": "application/json",
                "authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            response = requests.get(api_url, headers=headers, params=params)
            
            if response.status_code == 200:
                result = response.json()
                formatted_result = json.dumps(result, ensure_ascii=False, indent=2)
                log_debug(f"Matriz de productos consultada correctamente para SKU {sku}: {formatted_result}")
                return formatted_result
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_message)
                return error_message
        except Exception as e:
            logger.warning(f"Error al consultar matriz de productos para SKU {sku}: {e}")
            return f"Error: {e}"
    def search_relacionados_sku(self, sku: str) -> str:
        """
        Información de Productos relacionados o comprados en conjunto de un SKU específico.
        
        Args:
            sku (str): SKU de producto.
            
        Returns:
            str: Resultado de la consulta en formato JSON.
        """
        try:
            api_url = "https://b2b-api.implementos.cl/api/catalogo/relacionadoproducto"
            
            params = {
                "sku": sku
            }
            
            headers = {
                "Content-Type": "application/json",
                "authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            response = requests.get(api_url, headers=headers, params=params)
            
            if response.status_code == 200:
                result = response.json()
                formatted_result = json.dumps(result, ensure_ascii=False, indent=2)
                log_debug(f"Productos relacionados consultados correctamente para SKU {sku}: {formatted_result}")
                return formatted_result
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_message)
                return error_message
        except Exception as e:
            logger.warning(f"Error al consultar productos relacionados para SKU {sku}: {e}")
            return f"Error: {e}"
    def buscar_crossreference_oem(self, oem: str) -> str:
        """
        Busca SKUs compatibles con el código OEM
        
        Args:
            oem (str): OEM de ítem repuesto
            
        Returns:
            str: Resultado de la consulta en formato JSON
        """
        try:
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            clientes = db.ImplementosFiltrosCross
            campos = {
                "sku": 1,
                "_id": 0 
            }
                
            # Buscar cliente por RUT incluyendo solo los campos especificados
            resultados = clientes.find(
                {
                    "CODIGO": oem,
                    "sku": {"$ne": "", "$exists": True}  # sku debe existir y no ser vacío
                }, 
            projection=campos)
            
            skus_extraidos = {'data': []}
            if resultados:
                # Extraer los SKUs de los resultados
                skus_extraidos['data'] = [item['sku'] for item in resultados]
            
            # Procesar cada SKU para obtener detalles
            productos_detallados = []
            for sku in skus_extraidos.get('data', []):
                log_debug(f"Procesando SKU: {sku}")  # Para depuración
                producto_info = self.search_sku(sku)
                if producto_info:
                    productos_detallados.append(producto_info)
                    
            client.close() 
            
            if productos_detallados:
                formatted_result = json.dumps(productos_detallados, ensure_ascii=False, indent=2)
                log_debug(f"Productos compatibles con OEM {oem} encontrados: {formatted_result}")
                return formatted_result
                
            log_debug(f"No se encontraron productos compatibles con OEM {oem}")
            return json.dumps([], ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al buscar productos compatibles con OEM {oem}: {e}"
            logger.warning(error_message)
            return f"Error: {e}"     
    def prices(self, skus: List[str], codigoTienda: str = "SAN BRNRDO"):
        try:
            # URL de la API de precios
            api_url = "http://apiprecios.implementos.cl/precios/api/precios/precios"
            
            # Preparar los datos para la solicitud POST
            payload = {
                "sucursal": codigoTienda,
                "skus": skus
            }
            
            # Configurar los headers
            headers = {
                "Content-Type": "application/json"
            }
            
            # Realizar la solicitud POST
            response = requests.post(api_url, headers=headers, json=payload)
            
            # Verificar si la solicitud fue exitosa
            if response.status_code == 200:
                # Convertir la respuesta a JSON
                result = response.json()
                
                # Formatear el resultado para devolverlo
                formatted_result = json.dumps(result, ensure_ascii=False, indent=2)
                log_debug(f"Precios consultados correctamente para SKUs {skus}: {formatted_result}")
                return formatted_result
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_message)
                return error_message
                
        except Exception as e:
            logger.warning(f"Error al consultar los precios para SKUs {skus}: {e}")
            return f"Error: {e}"    
    def buscar_productos_patente(self, patente: str) -> str:
        """
        Productos compatibles con una patente o matricula
        
        Args:
            patente (str): patente chilena formato AAAA11 0 AA1111
            
        Returns:
            str: Resultado de la consulta en formato JSON.
        """
        try:
            # URL de la API de precios
            api_url = "https://b2b-api.implementos.cl/api/catalogo/catalogoOriginal"
            params = {
                "patente": patente
            }
            # Configurar los headers
            headers = {
                "Content-Type": "application/json",
                "authorization":"Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            api_url_vehiculo = "https://b2b-api.implementos.cl/api/catalogo/vehiculofilter"
            params = {
                "patente": patente
            }
            # Realizar la solicitud POST
            response = requests.get(api_url, headers=headers, params=params)
            response_vehiculo = requests.get(api_url_vehiculo, headers=headers, params=params)
            
            # Verificar si la solicitud fue exitosa
            if response.status_code == 200 and response_vehiculo.status_code == 200:
                
                # Convertir las respuestas a JSON
                result = response.json()
                result_vehiculo = response_vehiculo.json()
                
                # Obtener los SKUs usando la función
                skus_extraidos = self.obtener_skus(result.get('data', []))
                
                # Obtener información detallada de cada SKU
                productos_detallados = []
                for sku in skus_extraidos.get('data', []):
                    producto_info = self.search_sku(sku)
                    if producto_info:
                        productos_detallados.append(producto_info)
                
                # Extraer la información del vehículo sin el campo _id
                info_vehiculo = None
                if result_vehiculo and 'data' in result_vehiculo and 'vehiculo' in result_vehiculo['data']:
                    vehiculo = result_vehiculo['data']['vehiculo']
                    if '_id' in vehiculo:
                        del vehiculo['_id']
                    info_vehiculo = vehiculo
                
                # Crear el resultado final con la información del vehículo y los productos
                resultado_final = {
                    "vehiculo": info_vehiculo,
                    "productos": productos_detallados
                }
                
                formatted_result = json.dumps(resultado_final, ensure_ascii=False, indent=2)
                log_debug(f"Productos para patente {patente} consultados correctamente: {formatted_result}")
                return formatted_result
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_message)
                return error_message
        
        except Exception as e:
            logger.warning(f"Error al consultar productos para patente {patente}: {e}")
            return f"Error: {e}"        
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
    def search_sku(self, sku: str, codigoTienda: str = "SAN BRNRDO") -> str:
        """
        Información de SKU específico
        
        Args:
            sku (str): SKU de producto.
            codigoTienda (str, optional): Código sucursal.
            
        Returns:
            str: Resultado de la consulta en formato JSON.
        """
        try:
            # URL de la API de precios
            api_url = f"https://b2b-api.implementos.cl/ecommerce/api/v1/article/{sku}/data-sheet"
           
            # Preparar los datos para la solicitud POST
            params = {
                "documentId": 0,
                "branchCode": codigoTienda
            }
            
            # Configurar los headers
            headers = {
                "Content-Type": "application/json",
                "authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            # Realizar la solicitud POST
            response = requests.get(api_url, headers=headers, params=params)
            
            # Verificar si la solicitud fue exitosa
            if response.status_code == 200:
                # Convertir la respuesta a JSON
                result = response.json()
                
                # Filtrar solo los campos requeridos
                filtered_data = {}
                
                if "sku" in result:
                    filtered_data["sku"] = result["sku"]
                
                if "name" in result:
                    filtered_data["nombre"] = result["name"]
                if "brand" in result:
                    filtered_data["marca"] = result["brand"]
                if "description" in result:
                    filtered_data["descripcion"] = result["description"]
                if "partNumber" in result:
                    filtered_data["partNumber"] = result["partNumber"]    
                
                # Extraer la categoría UEN (categoría principal)
                if "categories" in result and result["categories"] and len(result["categories"]) > 0:
                    for cat in result["categories"]:
                        if cat.get("level") == 1:
                            filtered_data["categoria_uen"] = cat.get("name", "")
                            break
                
                # Extraer la línea (subcategoría)
                if "categories" in result and result["categories"] and len(result["categories"]) > 0:
                    for cat in result["categories"]:
                        if cat.get("level") == 2:
                            filtered_data["linea"] = cat.get("name", "")
                            break
                
                # Extraer el precio
                if "priceInfo" in result:
                    if "price" in result["priceInfo"]:
                        filtered_data["precio"] = result["priceInfo"]["price"]
                    
                    # Extraer información de precios por escala
                    if "hasScalePrice" in result["priceInfo"] and result["priceInfo"]["hasScalePrice"] and "scalePrice" in result["priceInfo"]:
                        filtered_data["precios_escala"] = []
                        for scale in result["priceInfo"]["scalePrice"]:
                            scale_info = {
                                "desde": scale.get("fromQuantity"),
                                "hasta": scale.get("toQuantity"),
                                "precio": scale.get("price")
                            }
                            filtered_data["precios_escala"].append(scale_info)
         
                
                # Extraer la imagen de 250px
                if "images" in result and "450" in result["images"] and len(result["images"]["450"]) > 0:
                    filtered_data["imagen_450"] = result["images"]["450"]
                
                # Extraer los atributos
                if "attributes" in result:
                    filtered_data["atributos"] = {attr["name"]: attr["value"] for attr in result["attributes"]}
                               
                # Formatear el resultado para devolverlo
                formatted_result = json.dumps(filtered_data, ensure_ascii=False, indent=2)
                log_debug(f"Información del SKU {sku} consultada correctamente: {formatted_result}")
                return formatted_result
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_message)
                return error_message
        
        except Exception as e:
            logger.warning(f"Error al consultar información para SKU {sku}: {e}")
            return f"Error: {e}"
    def obtener_skus(self, data):
        all_skus = []
        
        def process_data(items):
            if isinstance(items, list):
                for item in items:
                    # Procesar los SKUs si existen
                    if isinstance(item, dict):
                        if 'skus' in item and isinstance(item['skus'], list):
                            for sku in item['skus']:
                                if sku and isinstance(sku, dict) and 'sku' in sku:
                                    all_skus.append({'sku': sku['sku']})
                        
                        # Continuar procesando las estructuras anidadas
                        if 'subcategorias' in item:
                            process_data(item['subcategorias'])
                        if 'unidades' in item:
                            process_data(item['unidades'])
                        if 'detalle' in item:
                            process_data(item['detalle'])
        
        # Llamamos a la función recursiva con los datos iniciales
        process_data(data)
        
        # Obtener SKUs únicos (equivalente a [...new Set()] en JavaScript)
        unique_skus = list({item['sku'] for item in all_skus})
        
        return {'data': unique_skus}
    def informacion_tiendas(self, busqueda: str)-> str:
        """
        Búsqueda de información de tienda    
        Args:
            busqueda (str): Requerimiento específico de información de tienda a buscar
        Returns:
            str: Resultado de la consulta 
        """
        try:
            texto_extraido = [
                {"id": "5641663681",
                "code": "ANTOFGASTA",
                "name": "ANTOFAGASTA",
                "zone": "Antofagasta",
                "zoneGroup": "ZONA NORTE",
                "address": "Av. Pedro Aguirre Cerda 6919",
                "phone": "800330088",
                "mapUrl": "https://maps.app.goo.gl/qDCUNiCFQb7ZG81g9",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -23.606815,
                "lng": -70.388762,
                "city": "ANTOFAGASTA"
            },
            {
                "id": "5637149089",
                "code": "CON CON",
                "name": "CON CON",
                "zone": "Concón",
                "zoneGroup": "ZONA CENTRO",
                "address": "Camino Internacional N° 5100, Parcela 226.",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/y7LqPHd9C1PJJYx48",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -32.9625942,
                "lng": -71.5073647,
                "city": "CON CON"
            },
            {
                "id": "5637149110",
                "code": "LAMPA",
                "name": "LAMPA",
                "zone": "Lampa",
                "zoneGroup": "ZONA CENTRO",
                "address": "Av. La Montaña N° 820, Lampa",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/Pad7QcG6ZyEovzfs7",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -33.317304,
                "lng": -70.7337968,
                "city": "LAMPA"
            },
            {
                "id": "5642169633",
                "code": "PLACILLA",
                "name": "PLACILLA",
                "zone": "Placilla",
                "zoneGroup": "ZONA CENTRO",
                "address": "Calle de Servicio Ruta 68, N° 850.",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/t1PxDMUrsD6NfccE6",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -33.114554,
                "lng": -71.561112,
                "city": "PLACILLA"
            },
            {
                "id": "5637148335",
                "code": "ALT HOSPIC",
                "name": "ALTO HOSPICIO",
                "zone": "Alto Hospicio",
                "zoneGroup": "ZONA NORTE",
                "address": "Santa Rosa del Molle 4019-A.",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/KXBBs51tfiVRBho57",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -20.271331,
                "lng": -70.088958,
                "city": "ALTO HOSPICIO"
            },
            {
                "id": "5640587083",
                "code": "MELIPILLA",
                "name": "MELIPILLA",
                "zone": "Melipilla",
                "zoneGroup": "ZONA CENTRO",
                "address": "José Massoud Sarquis 275",
                "phone":  "800330088",
                "mapUrl": "https://goo.gl/maps/8DFdgdAnnuynKSSQA",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -33.6756420534018,
                "lng": -71.21687653325705,
                "city": "MELIPILLA"
            },
            {
                "id": "5637344973",
                "code": "EST CNTRAL",
                "name": "ESTACION CENTRAL",
                "zone": "Estación Central",
                "zoneGroup": "ZONA CENTRO",
                "address": "Av. Ecuador N° 4498.",
                "phone": "800330088",
                "email": "paulina.castro@implementos.cl",
                "mapUrl": "https://goo.gl/maps/BSedHKnM8AjG55ne8",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -33.45301,
                "lng": -70.6999417,
                "city": "ESTACION CENTRAL"
            },
            {
                "id": "5638288415",
                "code": "COLINA",
                "name": "COLINA",
                "zone": "Colina",
                "zoneGroup": "ZONA CENTRO",
                "address": "Carretera Norte Sur KM 21,5 Salida Lo Pinto",
                "phone": "800330088",
                "mapUrl": "https://g.page/implementos-colina?share",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -33.2744732,
                "lng": -70.7428091,
                "city": "COLINA"
            },
            {
                "id": "5637344976",
                "code": "SAN BRNRDO",
                "name": "SAN BERNARDO",
                "zone": "San Bernardo",
                "zoneGroup": "ZONA CENTRO",
                "address": "Av. General Velásquez N° 10701",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/S11MvEQynCzwthRk6",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -33.54844603188486,
                "lng": -70.70981,
                "city": "SAN BERNARDO"
            },
            {
                "id": "5637149093",
                "code": "COPIAPO",
                "name": "TIENDA COPIAPO",
                "zone": "Copiapo",
                "zoneGroup": "ZONA NORTE",
                "address": "Panamericana Norte Km 813,5 (Megacentro)",
                "phone":  "800330088",
                "mapUrl": "https://goo.gl/maps/4rSSPpQ3CbM3Azti9",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -27.3360482,
                "lng": -70.3782442,
                "city": "COPIAPO"
            },
            {
                "id": "5637149134",
                "code": "SAN FERNAN",
                "name": "SAN FERNANDO",
                "zone": "San Fernando",
                "zoneGroup": "ZONA SUR",
                "address": "Av. O´Higgins 054",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/e6vSiiQ7CDfz9YY96",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -34.5965986,
                "lng": -70.9900742
            },
            {
                "id": "5637149095",
                "code": "COQUIMBO",
                "name": "COQUIMBO",
                "zone": "Coquimbo",
                "zoneGroup": "ZONA CENTRO",
                "address": "Calle 5 N° 1251, Edificio 4, Bodegas 2 y 3 Barrio industrial",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/WFP912pE3VomB1GGA",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -29.9690033,
                "lng": -71.267944,
                "city": "COQUIMBO"
            },
            {
                "id": "5637147577",
                "code": "ARICA",
                "name": "ARICA",
                "zone": "Arica",
                "zoneGroup": "ZONA NORTE",
                "address": "Av. Alejandro Azolas 2765",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/FtKkbpZyXPZ1eH3V7",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -18.465565,
                "lng": -70.292699,
                "city": "ARICA"
            },
            {
                "id": "5637148340",
                "code": "CALAMA",
                "name": "CALAMA",
                "zone": "Calama",
                "zoneGroup": "ZONA NORTE",
                "address": "Camino Chiu-Chiu Sitio 3, Puerto Seco",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/k2oJdsURvGuTZ37c7",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -22.4421736,
                "lng": -68.8972794,
                "city": "CALAMA"
            },
            {
                "id": "5638253834",
                "code": "CURICO",
                "name": "CURICO",
                "zone": "Curicó",
                "zoneGroup": "ZONA SUR",
                "address": "Longitudinal Sur km.186, Modulo 7, Esquina Los Vidales",
                "phone":  "800330088",
                "mapUrl": "https://goo.gl/maps/MQNcRsavHPnKEkrt5",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -34.9672418,
                "lng": -71.1989569,
                "city": "CURICO"
            },
            {
                "id": "5637149087",
                "code": "CHILLAN",
                "name": "CHILLAN",
                "zone": "Chillán",
                "zoneGroup": "ZONA SUR",
                "address": "Av. Bernardo O’higgins 3301",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/uaXbBv3k9DpqvtUHA",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -36.6232288,
                "lng": -72.1437491,
                "city": "CHILLAN"
            },
            {
                "id": "5637149112",
                "code": "LINARES",
                "name": "LINARES",
                "zone": "Linares",
                "zoneGroup": "ZONA SUR",
                "address": "Avda. León Bustos 01320, Linares.",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/SdLxsaGNRTnxvonN9",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -35.8410211,
                "lng": -71.6261459,
                "city": "LINARES"
            },
            {
                "id": "5637149828",
                "code": "TALCA",
                "name": "TALCA",
                "zone": "Talca",
                "zoneGroup": "ZONA SUR",
                "address": "Avenida Circunvalación Norte 2680 Talca Barrio Parque Industrial",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/NRHUCt6XdyAHqsgG9",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -35.41942556318356,
                "lng": -71.63294075259194,
                "city": "TALCA"
            },
            {
                "id": "5637149097",
                "code": "CORONEL",
                "name": "CORONEL",
                "zone": "Coronel",
                "zoneGroup": "ZONA SUR",
                "address": "Camino a Coronel 7553 Km. 12,5. San Pedro de la Paz",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/Ejk6zV3aKyrYSVWQ8",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -36.8906594,
                "lng": -73.1431837,
                "city": "CORONEL"
            },
            {
                "id": "5638120333",
                "code": "P MONTT2",
                "name": "PUERTO MONTT",
                "zone": "Puerto Montt",
                "zoneGroup": "ZONA SUR",
                "address": "Av. Cardonal  N° 2000.",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/LA3RLKbBYMQvURAu8",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -41.4689053,
                "lng": -72.9719792,
                "city": "PUERTO MONTT"
            },
            {
                "id": "5637149091",
                "code": "CONCEPCION",
                "name": "CONCEPCION",
                "zone": "Concepción",
                "zoneGroup": "ZONA SUR",
                "address": "Av. Paicaví 2767",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/NmEhtjLY7Z1JGgrM7",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -36.8013432,
                "lng": -73.0591685,
                "city": "CONCEPCION"
            },
            {
                "id": "5637149830",
                "code": "TEMUCO",
                "name": "TEMUCO",
                "zone": "Temuco",
                "zoneGroup": "ZONA SUR",
                "address": "Av. Panamericana Sur N° 2205. Padre Las Casas",
                "phone":  "800330088",
                "mapUrl": "https://goo.gl/maps/i1RQNQmQSwQVuk6SA",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -38.7657052,
                "lng": -72.6120231,
                "city": "TEMUCO"
            },
            {
                "id": "5637148342",
                "code": "CASTRO",
                "name": "CASTRO",
                "zone": "Castro",
                "zoneGroup": "ZONA SUR",
                "address": "Av. Panamericana Norte, sector Ten Ten, esquina Carpe Diem",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/34xfkQV76ttfCama7",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -42.452294,
                "lng": -73.774879,
                "city": "CASTRO",
                "regionCode": "10"
            },
            {
                "id": "5637149115",
                "code": "LS ANGELES",
                "name": "LOS ANGELES",
                "zone": "Los Ángeles",
                "zoneGroup": "ZONA SUR",
                "address": "Av. Las Industrias N° 8075",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/iaPZsmgG8NnaMS7N8",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -37.4543635,
                "lng": -72.3289866,
                "city": "LOS ANGELES",
                "regionCode": "8"
            },
            {
                "id": "5637465223",
                "code": "PTA ARENAS",
                "name": "PUNTA ARENAS",
                "zone": "Punta Arenas",
                "zoneGroup": "ZONA SUR",
                "address": "Av. Camino Viejo a Río Seco, Km. 3.5 Rancho Las Cabras, Lote 1B manzana B",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/X58gUJuZpPQcWqSAA",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -53.1079635,
                "lng": -70.8841561,
                "city": "PUNTA ARENAS",
                "regionCode": "12"
            },
            {
                "id": "5637149832",
                "code": "VALDIVIA",
                "name": "VALDIVIA",
                "zone": "Valdivia",
                "zoneGroup": "ZONA SUR",
                "address": "Av. Ramón Picarte N° 2325",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/eggmLeK82ofqVKqdA",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -39.8299737,
                "lng": -73.2221166,
                "city": "VALDIVIA"
            },
            {
                "id": "5637149119",
                "code": "OSORNO",
                "name": "OSORNO",
                "zone": "Osorno",
                "zoneGroup": "ZONA SUR",
                "address": "Av. Regidor Gustavo Binder N° 1147",
                "phone":  "800330088",
                "mapUrl": "https://goo.gl/maps/2HhF1UScoCSKkX4s9",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -40.5944719,
                "lng": -73.1025043,
                "city": "OSORNO"
            },
            {
                "id": "5637149108",
                "code": "IQUIQUE",
                "name": "IQUIQUE",
                "zone": "Iquique",
                "zoneGroup": "ZONA NORTE",
                "address": "Av. Circunvalación 730",
                "phone": "800330088",
                "mapUrl": "https://goo.gl/maps/AXAorbKi32bCNqPX9",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -20.2175217,
                "lng": -70.133878,
                "city": "IQUIQUE"
            },
            {
                "id": "5642454711",
                "code": "RANCAGUA 2",
                "name": "RANCAGUA",
                "zoneGroup": "ZONA CENTRO",
                "address": "Longitudinal Sur Km 1040, Local A,",
                "phone": "800330088",
                "mapUrl": "https://maps.app.goo.gl/wgcbxe695WZSpKfi7",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "lat": -34.151758,
                "lng": -70.7281625,
                "city": "RANCAGUA"
            },
            {
                "id": "5643773099",
                "code": "TALCAHUANO",
                "name": "TALCAHUANO",
                "zone": "Talcahuano",
                "zoneGroup": "ZONA SUR",
                "address": "Av. Gran Bretaña 4733",
                "phone": "800330088",
                "mapUrl": "https://maps.app.goo.gl/MfLeVqJLFA8eKxz17",
                "schedule": "Lu-Vie: 9:00 a 18:30 | Sab: 9:00 a 13:00 hrs.",
                "order": 25,
                "lat": -36.7674489,
                "lng": -73.1154097,
                "city": "TALCAHUANO"
            }]
            
            # Mejora: procesamiento directo sin usar OpenAI
            busqueda = busqueda.strip().upper()
            resultados = []
            
            # Búsqueda flexible por nombre, ciudad, código o zona
            for tienda in texto_extraido:
                nombre = tienda.get("name", "").upper()
                ciudad = tienda.get("city", "").upper()
                codigo = tienda.get("code", "").upper()
                zona = tienda.get("zone", "").upper()
                zona_grupo = tienda.get("zoneGroup", "").upper()
                
                # Verificar si la búsqueda coincide con algún campo
                if (busqueda in nombre or busqueda in ciudad or 
                    busqueda in codigo or busqueda in zona or 
                    busqueda in zona_grupo):
                    resultados.append(tienda)
                
            # Si no se encontraron coincidencias exactas, buscar coincidencias parciales
            if not resultados:
                for tienda in texto_extraido:
                    nombre = tienda.get("name", "").upper()
                    ciudad = tienda.get("city", "").upper()
                    zona = tienda.get("zone", "").upper()
                    
                    palabras_busqueda = busqueda.split()
                    for palabra in palabras_busqueda:
                        if (palabra in nombre or palabra in ciudad or 
                            palabra in zona and tienda not in resultados):
                            resultados.append(tienda)
            
            # Formatear respuesta
            if resultados:
                respuesta = "Información de tiendas encontradas:\n\n"
                for tienda in resultados:
                    respuesta += f"Nombre: {tienda.get('name')}\n"
                    respuesta += f"Ciudad: {tienda.get('city', 'No especificada')}\n"
                    respuesta += f"Dirección: {tienda.get('address')}\n"
                    respuesta += f"Teléfono: {tienda.get('phone')}\n"
                    respuesta += f"Horario: {tienda.get('schedule')}\n"
                    respuesta += f"Mapa: {tienda.get('mapUrl')}\n\n"
                json_result = json.dumps(respuesta, ensure_ascii=False, indent=2)
                return json_result    
            else:
                json_result = json.dumps(texto_extraido, ensure_ascii=False, indent=2)
                return json_result    
            
        except Exception as e:
            return f"Error al procesar la solicitud: {str(e)}"
  
    def informacion_implementos(self, busqueda: str)-> str:
        """
        Imformacion de Implementos como empresa, terminos y condiciones de ecommerce, politicas de privacidad de datos
        
        Args:
            busqueda (str): Requerimiento específico de información 
        
        Returns:
            str: Resultado de la consulta 
        """
        try:
            # Inicializar el cliente de OpenAI
            cliente = OpenAI()
            
            # Crear un prompt para GPT-4o mini
            prompt = f"""
                 ## INFORMACIÓN CORPORATIVA 📋

                    ### Sobre Implementos Chile
                    - Líder en repuestos y accesorios para transporte pesado 
                    - Casa Matriz: Av. Gral. Velásquez N° 10701, San Bernardo, Santiago

                    ### Formas de Contacto 📞
                    - Teléfono gratuito: 800 330 088
                    - WhatsApp: +56 9 3263 3571
                    - Sitio web: www.implementos.cl
                    - Email: ventas@implementos.cl

                    ### Métodos de Pago Disponibles 💳
                    - Efectivo en tiendas
                    - Tarjetas de débito y crédito
                    - WebPay
                    - Mercado Pago
                    - Khipu
                    - Transferencias bancarias

                    ### Opciones de Envío y Retiro 🚚
                    - **Despacho a Domicilio**: Cobertura nacional. GRATIS en compras sobre $60.000
                    - **Retiro en Tienda**: Sin costo adicional en cualquiera de las 30 tiendas

                ##IMPLEMENTOS##
                ¿Quiénes Somos?
                Somos una empresa con más de 27 años en el rubro del Transporte, comercializando partes, piezas y accesorios para el transporte de camiones, buses y remolques.
                Nuestra organización nace en Chile, a partir del Grupo Epysa, con casi medio siglo de experiencia en el rubro de vehículos pesados.
                Desde nuestros orígenes contamos con la representación exclusiva de dos grandes marcas de Brasil. Randon fabricante de carrocerías, remolques y semirremolques más grande de Sudamérica, y Marcopolo, fabricante más grande de carrocerías para autobuses del mundo.
                En nuestra esencia, reside un enfoque dedicado al cliente, rigiéndolo como la pieza central de todo lo que hacemos. Esto se materializa a través de un modelo de servicio que se basa en tres canales de venta: Tienda, Terreno y Digital, ofreciendo envíos a domicilio o retiro en tienda, para dar un servicio de venta omnicanal tanto a pequeños como grandes transportistas.
                En el epicentro de nuestra oferta, residen las tiendas del transporte, donde la premisa fundamental es ofrecer la mayor variedad de productos de la mejor calidad y disponibilidad, siempre empeñados en ofrecer un servicio al cliente que se distinga por su excelencia.
                Creamos con nuestras tiendas como un lugar donde el transportista podrá encontrar todo lo que necesite en su parada tanto para él, como para su emprendimiento, empresa, o para su preciado vehículo, enfocándonos en ofrecer el mejor precio del mercado en cada categoría.
                Actualmente somos una empresa líder en Chile y Perú, en la venta de repuestos, insumos y accesorios para el transporte de carga, pasajeros, maquinaria agrícola y vehículos livianos. Es por esto que, en el año 2022 dimos un salto audaz al aterrizar en España, abriendo tiendas en Fuenlabrada, Seseña y Azuqueca.
                Nuestra red se compone de 30 tiendas que abarcan desde Arica hasta Punta Arenas, con opciones de venta telefónica al 800 330 088, y comunicación a través de WhatsApp al +569 32633571. Además, nuestra página web, www.implementos.cl.
                Con 13 tiendas operando en Perú y próximamente 4 en España, nuestra presencia sigue creciendo llevando nuestra visión de servicio y calidad a nuevos horizontes.

                Visión
                Ser la compañía más querida, admirada y preferida por nuestros clientes, colaboradores y proveedores, ayudando que la industria del transporte esté siempre en movimiento.

                Misión
                Satisfacer las expectativas de nuestros clientes con soluciones oportunas a sus requerimientos, brindándoles, a un precio justo, cobertura en todos los canales, respaldo, financiamiento, disponibilidad y una gran experiencia de compra.
              
                ##TERMINO Y CONDICIONES ECOMMERCE##
                El acceso y uso de este sitio web se rige por los términos y condiciones descritos a continuación, así como por la legislación que se aplique en la República de Chile. En consecuencia, todas las visitas y todos los contratos y transacciones que se realicen en este sitio, como asimismo sus efectos jurídicos, quedarán regidos por estas reglas y sometidas a esa legislación. Asimismo se señala que estos términos y condiciones no podrán variar sino en virtud de una nueva protocolización de nuevos términos y condiciones, que regirán a partir de la fecha de la respectiva protocolización. Los términos y condiciones contenidos en este instrumento se aplicarán y se entenderán formar parte de todos los actos y contratos que se ejecuten o celebren mediante los sistemas de oferta y comercialización comprendidos en este sitio web entre los usuarios de este sitio e IMPLEMENTOS S.A. y por cualquiera de las otras sociedades o empresas que sean filiales o coligadas con ellas, y que hagan uso de este sitio a las cuales se les denominará en adelante también en forma indistinta como “las empresas”, o bien “la empresa oferente”, “el proveedor” o “la empresa proveedora”, según convenga al sentido del texto. En caso que las empresas hubieran fijado sus propios términos y condiciones para los actos y contratos que realicen en este sitio, ellas aparecerán en esta página señaladas con un link y prevalecerán sobre éstas. A continuación se exponen dichas condiciones:
                Definiciones
                1.	REGISTRO DEL USUARIO O CLIENTE — Será requisito necesario para la adquisición de productos y servicios ofrecidos en este sitio, la aceptación de las presentes condiciones y el registro por parte del usuario, con definición de una clave de acceso. Se entenderán conocidos y aceptados estos Términos y Condiciones por el solo hecho del registro. El registro de cada usuario se verificará completando y suscribiendo el formulario que al efecto se contiene en el sitio y su posterior envío, el cual se realiza automáticamente mediante un “click” en el elemento respectivo.
                2.	CLAVE SECRETA — El usuario dispondrá, una vez registrado, de un nombre y contraseña o clave definitiva que le permitirá el acceso personalizado, confidencial y seguro. El usuario tendrá la posibilidad de cambiar la clave de acceso, para lo cual deberá sujetarse al procedimiento establecido en el sitio respectivo. El usuario asume totalmente la responsabilidad por el mantenimiento de la confidencialidad de su clave secreta registrada en este sitio web, la cual le permite efectuar compras, solicitar servicios y obtener información. Dicha clave es de uso personal y su entrega a terceros, no involucra responsabilidad de IMPLEMENTOS S.A. o de las empresas en caso de mala utilización.
                3.	DERECHOS DEL USUARIO DE ESTE SITIO — El usuario gozará de todos los derechos que le reconoce la legislación sobre protección al consumidor vigente en el territorio de Chile, y además los que se le otorgan en estos términos y condiciones. El usuario dispondrá en todo momento de los derechos de información, rectificación y cancelación de los datos personales conforme a la Ley Nº19.628 sobre protección de datos de carácter personal. La sola visita de este sitio en el cual se ofrecen determinados bienes y el acceso a determinados servicios, no impone al consumidor obligación alguna, a menos que haya aceptado en forma inequívoca las condiciones ofrecidas por el proveedor, en la forma indicada en estos términos y condiciones.

                CAMBIOS Y DEVOLUCIONES 
                Si el producto que compraste no tuviera las características técnicas informadas, te llegó dañado o incompleto, no te preocupes, puedes cambiarlo de inmediato. Si presentara fallas o defectos dentro de los 6 meses siguientes a la fecha en que fue recibido, puedes optar entre su reparación gratuita, o previa restitución, su cambio o su devolución de la cantidad pagada, siempre que el producto no se hubiera deteriorado por un hecho imputable al consumidor. Puedes entregarlo en cualquier tienda Implementos de Chile. Si tu producto cuenta con una garantía del fabricante, se aplicará el plazo de esa garantía, si dicho plazo fuera mayor. Todos estos plazos se suspenderán por el tiempo en que el bien esté siendo reparado en ejercicio de su garantía, y hasta que se complete su reparación.
                Se considerará que hay una falla o defecto:
                1.	Si los productos sujetos a normas de seguridad o calidad de cumplimiento obligatorio no cumplan las especificaciones correspondientes.
                2.	Si los materiales, partes, piezas, o elementos que constituyan o integren los productos no correspondan a las especificaciones que ostenten.
                3.	Si cualquier producto, por deficiencias de fabricación, elaboración, materiales, partes, piezas, elementos, estructura o calidad, no sea enteramente apto para el uso al que está destinado o al que el proveedor hubiese señalado en su publicidad.
                4.	Si después de la primera vez de haberse hecho efectiva la garantía y prestado el servicio técnico correspondiente, subsistieren las deficiencias que hagan al bien inapto para el uso a que se refiere la letra/c. Este derecho subsistirá para el evento de presentarse una deficiencia distinta a la que fue objeto del servicio técnico, o volviere a presentarse la misma, dentro de los plazos a que se refiere el artículo siguiente.
                5.	Si la cosa objeto del contrato tenga defectos o vicios ocultos que imposibiliten el uso a que habitualmente se destine.
                POLITICA DE CAMBIO Y DEVOLUCIONES 

                Si el producto que compraste no tiene las características técnicas ofrecidas o lo recibiste dañado o incompleto, puedes cambiarlo o devolverlo, dentro de los 30 días siguientes a la fecha en que lo hayas recibido, en cualquier tienda implementos o, si fue despachado, te ofrecemos Ir a retirarlo al mismo lugar sin ningún costo adicional.
                1.	Si prefieres cambiarlo o devolverlo en una tienda, dirígete al Mesón de Ventas, donde, además, atenderán todas tus consultas.
                2.	Si el producto fue despachado a tu dirección y prefieres que lo retiremos, comunícate con el Servicio de Atención al Cliente al 800 330 088 opción 3.
                3.	El producto debe ser cambiado o devuelto sin uso, con todos sus embalajes originales y en perfectas condiciones, con los accesorios y regalos promocionales que estuvieron asociados a la compra.
                4.	Deberás presentar tu factura o boleta.
                5.	Nuestros técnicos autorizados podrán revisar que el producto no presenta fallas o daños imputables al consumidor.
                6.	Los productos exceptuados, tienen condiciones de cambio o devolución especiales.
                7.	Nuestros técnicos autorizados podrán revisar que el producto no presenta fallas o daños imputables al consumidor.

                PRODUCTOS EXEPTUADOS 
                Productos usados, abiertos, de segunda selección o con alguna deficiencia: Implementos está autorizada para comercializar productos usados, abiertos, de segunda selección o con alguna deficiencia, a precios rebajados. Esto se indicará claramente al consumidor en los propios artículos, en sus envoltorios, o en avisos o carteles visibles al público. En estos casos no procederá el cambio ni la devolución del producto.

                ##Política de privacidad de IMPLEMENTOS S.A.##
                    Última actualización: 24 de diciembre de 2024
                    1. Introducción
                    En IMPLEMENTOS S.A. reconocemos la importancia de la protección de datos personales y nos comprometemos a respetar la privacidad de todos nuestros clientes, colaboradores y cualquier persona que interactúe con nuestra empresa. Esta Política de Protección de Datos describe cómo recopilamos, utilizamos, almacenamos, comunicamos y protegemos sus datos personales, de acuerdo con la Ley 19.628 sobre Protección de la Vida Privada, sus modificaciones, incluyendo la Ley 21.719.

                    2. Definiciones
                    ● Dato personal:

                    Cualquier información relacionada con una persona física identificada o identificable. Esto incluye, entre otros, nombre, número de identificación (RUT, Pasaporte), datos de contacto, información financiera, etc.

                    ● Dato personal sensible:
                    Es aquel que revela información privada o íntima de una persona, como su origen étnico, opiniones políticas, creencias religiosas, salud, orientación sexual, etc.

                    ● Tratamiento de datos:
                    Cualquier operación o conjunto de operaciones que se realicen sobre datos personales, ya sea de forma automatizada o manual. Ejemplos: recolección, almacenamiento, uso, comunicación, transferencia o eliminación.

                    ● Responsable de datos:
                    Persona natural o jurídica, que decide acerca de los fines y medios del tratamiento de datos personales.

                    ● Encargado de datos:
                    Persona natural o Jurídica que trata los datos personales a nombre del responsable de datos, conforme a las instrucciones que imparta el responsable.

                    3. Principios
                    En IMPLEMENTOS S.A. nos adherimos a los siguientes principios rectores en el tratamiento de datos personales:

                    ● Licitud, lealtad y transparencia:
                    Tratamos los datos personales de forma legal, transparente y justa, con el debido respeto a los derechos de los titulares.

                    ● Limitación de la finalidad:
                    Recopilamos datos personales con fines específicos, explícitos y legítimos, y no los utilizamos para fines distintos sin tu consentimiento o una base legal que lo justifique.

                    ● Minimización de datos:
                    Limitamos la recopilación de datos personales a lo necesario y relevante para los fines del tratamiento.

                    ● Exactitud:
                    Nos aseguramos de que los datos personales sean exactos, completos, actuales y pertinentes.

                    ● Limitación del plazo de conservación:
                    Conservamos los datos personales solo durante el tiempo necesario para los fines del tratamiento.

                    ● Integridad y confidencialidad:
                    Garantizamos la confidencialidad, integridad y disponibilidad de tus datos personales mediante medidas de seguridad adecuadas.

                    ● Responsabilidad proactiva:
                    Asumimos la responsabilidad del cumplimiento de la normativa de protección de datos.

                    4. Base legal para el tratamiento de los datos
                    Realizamos el tratamiento de tus datos de manera legítima, en base a alguna de las siguientes razones:

                    ● Consentimiento:
                    Cuando nos das tu consentimiento explícito para tratar tus datos para un fin específico. Por ejemplo, cuando te suscribes a nuestras promociones y/o newsletter.

                    ● Relación contractual:
                    Cuando el tratamiento es necesario para la ejecución de un contrato del que eres parte. Por ejemplo, para procesar tus pedidos o gestionar tu cuenta de cliente.

                    ● Cumplimiento de una obligación legal:
                    Cuando estamos obligados por ley a tratar tus datos. Por ejemplo, para cumplir con obligaciones fiscales o laborales.

                    ● Interés legítimo:
                    Cuando el tratamiento es necesario para los intereses legítimos de IMPLEMENTOS S.A. o de un tercero, siempre que no prevalezcan tus intereses o derechos fundamentales.
                    Ejemplo: Utilizamos datos de navegación en nuestro sitio web para analizar las preferencias de los usuarios y mejorar la experiencia de navegación. Esto nos permite ofrecer un servicio más personalizado y relevante.
                    Ejemplo: Analizamos el historial de compras de nuestros clientes para prevenir el fraude y proteger sus cuentas.
                    5. Destinatarios de tus datos
                    En general, tus datos no serán comunicados a terceros, salvo que sea necesario para cumplir con las finalidades del tratamiento o exista una obligación legal. En los casos en que necesitemos comunicar tus datos a terceros, te proporcionaremos información clara y transparente sobre la identidad de los destinatarios y la finalidad de la comunicación.
                    Ejemplos de destinatarios:

                    ● Proveedores de servicios:
                    Podemos compartir tus datos con proveedores que nos ayudan a prestar nuestros servicios, como empresas de transporte, procesamiento de pagos o marketing. En estos casos, nos aseguraremos de que los proveedores cumplan con la normativa de protección de datos.

                    ● Autoridades públicas:
                    Podemos comunicar tus datos a las autoridades públicas cuando estemos obligados por ley.

                    6. Derechos de los titulares
                    Como titular de datos personales, tienes los siguientes derechos:

                    ● Derecho de acceso:
                    Puedes solicitar información sobre si estamos tratando tus datos personales y acceder a ellos.

                    ● Derecho de rectificación:
                    Puedes solicitar la corrección de tus datos si son inexactos o incompletos.

                    ● Derecho de supresión:
                    Puedes solicitar la eliminación de tus datos en determinadas circunstancias, como cuando ya no sean necesarios para los fines para los que fueron recogidos o cuando retires tu consentimiento.

                    ● Derecho de oposición:
                    Puedes oponerte al tratamiento de tus datos por motivos relacionados con tu situación particular.

                    ● Derecho a la limitación del tratamiento:
                    Puedes solicitar que limitemos el tratamiento de tus datos en ciertos casos, como cuando impugnes su exactitud o te opongas a su tratamiento.

                    ● Derecho a la portabilidad:
                    Puedes solicitar una copia de tus datos en un formato electrónico estructurado y común.

                    ● Derecho a no ser objeto de decisiones individuales automatizadas:
                    Tienes derecho a no ser objeto de una decisión basada únicamente en el tratamiento automatizado, incluida la elaboración de perfiles, que produzca efectos jurídicos sobre ti o te afecte significativamente de modo similar.

                    7. Medidas de seguridad
                    Implementamos medidas de seguridad físicas, técnicas y organizativas apropiadas para proteger tus datos personales, incluyendo:

                    ● Control de acceso a la información:
                    Solo el personal autorizado puede acceder a tus datos.

                    ● Capacitación del personal:
                    Nuestro personal está capacitado en la importancia de la protección de datos.

                    ● Seguridad de sistemas informáticos:
                    Utilizamos contraseñas seguras, firewalls, software antivirus y otras medidas para proteger nuestros sistemas.

                    ● Protección de servidores:
                    Nuestros servidores están protegidos con medidas de seguridad, como acceso restringido y sistemas de respaldo.

                    ● Cifrado de datos:
                    Utilizamos técnicas de cifrado para proteger tus datos, especialmente durante su transmisión y almacenamiento.

                    ● Protocolos de seguridad:
                    Implementamos protocolos de seguridad como HTTPS para proteger la información transmitida entre tu navegador y nuestro sitio web.

                    ● Auditorías de seguridad:
                    Realizamos auditorías de seguridad periódicas para evaluar la eficacia de nuestras medidas de protección de datos.

                    ● Plan de respuesta a incidentes:
                    Contamos con un plan de respuesta a incidentes de seguridad para actuar de forma rápida y eficiente en caso de cualquier incidente que pueda comprometer la seguridad de tus datos.

                    8. Transferencias internacionales de datos
                    Nos aseguramos de que las transferencias internacionales de datos a Chile desde España y Perú, mediante acceso a bases de datos en la nube, cumplan con las medidas de seguridad adecuadas. Esto incluye el uso de proveedores de servicios en la nube que ofrezcan garantías suficientes de protección de datos, como la implementación de cláusulas contractuales tipo aprobadas por la Comisión Europea. Además, implementamos medidas adicionales de seguridad, como el cifrado de datos, para proteger tus datos personales durante la transferencia y el almacenamiento.

                    9. Menores de edad
                    Protegemos la privacidad de los menores de edad. Si eres menor de 14 años, necesitamos el consentimiento de tus padres o tutores para tratar tus datos. En el caso de adolescentes mayores de 14 años, pero menores de 18, evaluaremos cuidadosamente la necesidad de obtener el consentimiento paterno.

                    10. Datos sensibles
                    No solicitamos datos sensibles a nuestros clientes. En caso de que necesitemos tratar datos sensibles de nuestros colaboradores, como datos de salud, lo haremos únicamente con su consentimiento explícito y tomaremos medidas de seguridad adicionales para proteger esta información.

                    11. Información adicional
                    ● El delegado de protección de datos es D. Paul Bravo Jounard, quien puede ser contactado en paul.bravo@implementos.cl para cualquier consulta o solicitud relacionada con tus datos personales.
                    ● Puedes ejercer tus derechos contactando a IMPLEMENTOS S.A. a través del correo electrónico contacto@implementos.cl o por teléfono al 800 330 088 (Opción 3).
                    ● Esta Política de Protección de Datos puede ser modificada para adaptarse a la normativa vigente. Te recomendamos revisarla periódicamente en nuestro sitio web.

                    12. Cumplimiento de la Ley 19.628
                    Esta política se ha elaborado tomando en cuenta las disposiciones de la Ley 19.628 sobre Protección de la Vida Privada, incluyendo sus modificaciones, y las siguientes leyes y recomendaciones:

                    ● El Artículo 19 N°4 de la Constitución Política de la República.
                    ● La Ley 20.575 que establece el principio de finalidad en el Tratamiento de Datos Personales.
                    ● La Ley 21.430 sobre Garantías y Protección Integral de los Derechos de la Niñez y Adolescencia.
                    ● Las recomendaciones del Consejo para la Transparencia sobre la Protección de Datos Personales.

                    13. Declaración de compromiso
                    En IMPLEMENTOS S.A. nos comprometemos a proteger la privacidad de tus datos personales y a tratarlos de forma responsable y ética, cumpliendo con la legislación vigente y los más altos estándares de seguridad.

                    14. Contacto
                    Si tienes alguna pregunta o inquietud sobre nuestra Política de privacidad, no dudes en contactarnos:

                    ● Correo electrónico: contacto@implementos.cl
                    ● Teléfono: 800 330 088 (Opción 3)
                    ● Dirección: Av. General Velásquez 10701, San Bernardo, Región Metropolitana de Santiago - CP 8060047
            """
            
            # Realizar la consulta a GPT-4o mini
            respuesta = cliente.chat.completions.create(
                model="gpt-4o-mini",  # Asegúrate de que este es el nombre correcto del modelo
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Se requiere informacion de : "+busqueda}
                ],
                temperature=0.2  # Temperatura baja para respuestas más precisas
            )
            
            # Devolver la respuesta generada
            return respuesta.choices[0].message.content
            
        except Exception as e:
            return f"Error al procesar la solicitud: {str(e)}"


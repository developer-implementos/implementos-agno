import requests
import json
from typing import List
from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger
from qdrant_client import QdrantClient
from agno.embedder.openai import OpenAIEmbedder
from pymongo import MongoClient
from config.config import Config

class ArticulosTool(Toolkit):
    def __init__(self):
        super().__init__(name="articulos_tool")
        # Registrar las funciones en el toolkit para que sean accesibles dinámicamente.
        self.register(self.stock_sku)
        self.register(self.reservas_sku)
        self.register(self.transitos_internos_sku)
        self.register(self.transitos_externos_sku)
        self.register(self.search_matriz_sku)
        self.register(self.search_relacionados_sku)
        self.register(self.product_prices)
        self.register(self.search_sku)
        self.register(self.buscar_productos_patente)
        self.register(self.buscar_producto)
        self.register(self.search_crossference_oem)
        self.register(self.buscar_crossreference_oem)
    def stock_sku(self, sku: str) -> str:
        """
        Información de stock en tiendas para un SKU específico.

        Args:
            sku (str): SKU de producto.

        Returns:
            str: Resultado de la consulta en formato JSON.
        """
        try:
            # URL de la API de precios
            api_url = "https://b2b-api.implementos.cl/api/carro/stockOmni"
           
            # Preparar los datos para la solicitud POST
            params = {
                "sku": sku
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
                formatted_result = json.dumps(result, ensure_ascii=False, indent=2)
                log_debug(f"Stock consultado correctamente para SKU {sku}: {formatted_result}")
                return formatted_result
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_message)
                return error_message
        except Exception as e:
            logger.warning(f"Error al consultar stock para SKU {sku}: {e}")
            return f"Error: {e}"
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
                    "imagen": "https://images.implementos.cl/img/250/"+sku+"-1.jpg",
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
    def reservas_sku(self, sku: str) -> str:
        """
        Información de reservas de stock de un SKU específico.

        Args:
            sku (str): SKU de producto.

        Returns:
            str: Resultado de la consulta en formato JSON.
        """
        try:
            # Construir la URL de la API agregando el SKU a la ruta
            api_url = "https://b2b-api.implementos.cl/api/logistica/reservas-stock/" + sku
            headers = {
                "Content-Type": "application/json",
                "authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            response = requests.get(api_url, headers=headers)
            if response.status_code == 200:
                result = response.json()
                formatted_result = json.dumps(result, ensure_ascii=False, indent=2)
                log_debug(f"Reservas consultadas correctamente para SKU {sku}: {formatted_result}")
                return formatted_result
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_message)
                return error_message
        except Exception as e:
            logger.warning(f"Error al consultar reservas para SKU {sku}: {e}")
            return f"Error: {e}"
    def transitos_internos_sku(self, sku: str) -> str:
        """
        Información de tránsitos internos de stock de un SKU específico hacia tiendas.

        Args:
            sku (str): SKU de producto.

        Returns:
            str: Resultado de la consulta en formato JSON.
        """
        try:
            # Nota: Se está utilizando la misma URL que en reservas_sku. Verifica si el endpoint es correcto.
            api_url = "https://b2b-api.implementos.cl/api/logistica/reservas-stock/" + sku
            headers = {
                "Content-Type": "application/json",
                "authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            response = requests.get(api_url, headers=headers)
            if response.status_code == 200:
                result = response.json()
                formatted_result = json.dumps(result, ensure_ascii=False, indent=2)
                log_debug(f"Tránsitos internos consultados correctamente para SKU {sku}: {formatted_result}")
                return formatted_result
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_message)
                return error_message
        except Exception as e:
            logger.warning(f"Error al consultar tránsitos internos para SKU {sku}: {e}")
            return f"Error: {e}"
    def transitos_externos_sku(self, sku: str) -> str:
        """
        Información de tránsitos de stock internacionales de SKU específico.
        
        Args:
            sku (str): SKU de producto.
            
        Returns:
            str: Resultado de la consulta en formato JSON.
        """
        try:
            api_url = "https://b2b-api.implementos.cl/api/logistica/transitos-compras/" + sku
            
            headers = {
                "Content-Type": "application/json",
                "authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            response = requests.get(api_url, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                formatted_result = json.dumps(result, ensure_ascii=False, indent=2)
                log_debug(f"Tránsitos externos consultados correctamente para SKU {sku}: {formatted_result}")
                return formatted_result
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_message)
                return error_message
        except Exception as e:
            logger.warning(f"Error al consultar tránsitos externos para SKU {sku}: {e}")
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
    def product_prices(self, skus: List[str], codigoTienda: str = "SAN BRNRDO") -> str:
        """
        Consulta los precios de productos a través de la API de precios de Implementos Chile.

        Args:
            skus (List[str]): Lista de SKUs de productos para consultar precios. Cada SKU se debe especificar como una cadena.
            codigoTienda (str, optional): Sucursal para la consulta de precios. El valor por defecto es "SAN BRNRDO".

        Returns:
            str: Resultado de la consulta en formato JSON.
        """
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
                result = response.json()
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
    
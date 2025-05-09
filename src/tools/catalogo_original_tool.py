import json
import requests
from typing import List, Dict, Any, Optional
from agno.tools import Toolkit
from agno.utils.log import log_debug, logger
from config.config import Config
from databases.clickhouse_client import config
import clickhouse_connect
from pymongo import MongoClient

class CatalogoOriginalTool(Toolkit):
    def __init__(self):
        super().__init__(name="catalogo_original_tool")
        # Registrar las funciones en el toolkit
        self.register(self.obtener_catalogo_original)
        self.BASIC_AUTH = "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"

    def create_clickhouse_client(self):
        """Crea y devuelve un cliente de ClickHouse utilizando la configuración"""
        client_config = config.get_client_config()
        try:
            client = clickhouse_connect.get_client(**client_config)
            # Probar la conexión
            version = client.server_version
            return client
        except Exception as e:
            logger.error(f"Error al conectar a ClickHouse: {e}")
            raise

    def execute_query(self, query: str):
        """Ejecuta una consulta en ClickHouse y devuelve los resultados"""
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
            logger.error(f"Error ejecutando consulta: {err}")
            return []

    def obtener_catalogo_original(self, patente: Optional[str] = None, vin: Optional[str] = None, uens: Optional[List[str]] = None) -> str:
        """
        Obtiene el catálogo original de productos para un vehículo mediante su patente o VIN

        Args:
            patente (Optional[str]): Patente del vehículo
            vin (Optional[str]): VIN del vehículo
            uens (Optional[List[str]]): Lista de UENs para filtrar los productos. Por defecto 'TODAS'.

        Returns:
            str: Catálogo de productos en formato JSON
        """
        try:
            # Validar que se haya proporcionado patente o VIN
            if not patente and not vin:
                log_debug("No se proporcionó patente o VIN para consultar catálogo original")
                return json.dumps({
                    "ok": False,
                    "mensaje": "Necesito la patente o VIN del vehículo para buscar el catálogo original 🚗🔍"
                }, ensure_ascii=False, indent=2)

            # Normalizar UENs
            if not uens:
                uens = []

            # Filtrar UENs "TODAS"
            uens = [uen for uen in uens if uen != "TODAS"]

            # Obtener datos del vehículo desde ClickHouse
            query = """
                SELECT
                    TOP 1
                    placaPatente as patente,
                    marca as marca,
                    modelo as modelo,
                    anioFabricacion as anio_fabricacion,
                    vin as vin,
                    tipoVehiculo as tipo_vehiculo
                FROM
                    implementos.flota_cliente
            """

            if patente:
                query += f" WHERE placaPatente = '{patente}'"
            elif vin:
                query += f" WHERE vin = '{vin}'"

            vehiculo_data = self.execute_query(query)

            if not vehiculo_data:
                log_debug(f"No se encontró el vehículo con patente={patente} o vin={vin}")
                return json.dumps({
                    "ok": False,
                    "mensaje": "Lo siento 😕, no se encontró la patente o VIN en nuestros sistemas."
                }, ensure_ascii=False, indent=2)

            # Obtener el catálogo original desde la API
            url = "https://b2b-api.implementos.cl/api/catalogo/catalogoOriginal"
            if patente:
                url += f"?patente={patente}"
            elif vin:
                url += f"?vin={vin}"

            headers = {
                "Authorization": self.BASIC_AUTH
            }

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                log_debug(f"Error al obtener catálogo original: {response.status_code} - {response.text}")
                return json.dumps({
                    "ok": False,
                    "mensaje": f"Error al obtener el catálogo original. Por favor, intenta nuevamente más tarde. 😔"
                }, ensure_ascii=False, indent=2)

            catalogo_data = response.json().get("data", [])

            # Extraer SKUs del catálogo
            skus = self._obtener_skus(catalogo_data)

            if not skus:
                titulo = f"recomendación de skus para '{patente or vin}'"
                log_debug(f"No se encontraron SKUs en el catálogo original para {patente or vin}")
                return json.dumps({
                    "ok": False,
                    "mensaje": "Ningún articulo encontrado."
                }, ensure_ascii=False, indent=2)

            # Buscar artículos en MongoDB
            try:
                client = MongoClient(Config.MONGO_NUBE)
                db = client.Implenet
                articulos_collection = db.articulos

                # Construir la consulta
                query = {"sku": {"$in": skus}}
                if uens and len(uens) > 0:
                    query["uen"] = {"$in": uens}

                # Obtener los artículos
                articulos_cursor = articulos_collection.aggregate([
                    {
                        "$match": query
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "imagen": {"$concat": ["https://images.implementos.cl/img/150/", "$sku", "-1.jpg"]},
                            "sku": "$sku",
                            "nombre": "$nombre",
                            "marca": "$marca",
                            "precio": "$precio",
                            "categoria": "$categoria",
                            "uen": "$uen"
                        }
                    }
                ])

                articulos = list(articulos_cursor)
                client.close()

                if not articulos:
                    log_debug(f"No se encontraron artículos en MongoDB para los SKUs del catálogo original")
                    return json.dumps({
                        "ok": False,
                        "mensaje": "No se encontraron artículos en MongoDB para los SKUs del catálogo original"
                    }, ensure_ascii=False, indent=2)

                # Preparar el mensaje de respuesta
                vehiculo_info = vehiculo_data[0]

                # Construir la respuesta final
                resultado = {
                    "informacion_vehiculo": vehiculo_info,
                    "productos": articulos
                }

                log_debug(f"Se encontraron {len(articulos)} artículos para el catálogo original de {patente or vin}")
                return json.dumps(resultado, ensure_ascii=False, indent=2)

            except Exception as e:
                log_debug(f"Error al buscar artículos en MongoDB: {e}")
                return json.dumps({
                    "ok": False,
                    "mensaje": f"Error al procesar los artículos del catálogo. Por favor, intenta nuevamente más tarde. 😔"
                }, ensure_ascii=False, indent=2)

        except Exception as e:
            error_message = f"Error al obtener catálogo original: {e}"
            logger.warning(error_message)
            return json.dumps({
                "ok": False,
                "mensaje": "Ocurrió un error al obtener el catálogo original. Por favor, intenta nuevamente más tarde. 😔"
            }, ensure_ascii=False, indent=2)

    def _obtener_skus(self, data: List[Dict[str, Any]]) -> List[str]:
        """
        Procesa los datos del catálogo para extraer los SKUs

        Args:
            data (List[Dict[str, Any]]): Datos del catálogo

        Returns:
            List[str]: Lista de SKUs únicos encontrados
        """
        all_skus = []

        def process_data(items):
            if isinstance(items, list):
                for item in items:
                    # Procesar los SKUs si existen
                    if item.get("skus") and isinstance(item.get("skus"), list):
                        for sku in item["skus"]:
                            if sku and sku.get("sku"):
                                all_skus.append(sku["sku"])

                    # Continuar procesando estructuras anidadas
                    if item.get("subcategorias"):
                        process_data(item["subcategorias"])
                    if item.get("unidades"):
                        process_data(item["unidades"])
                    if item.get("detalle"):
                        process_data(item["detalle"])

        # Llamar a la función recursiva con los datos iniciales
        process_data(data)

        # Eliminar duplicados
        unique_skus = list(set(all_skus))

        return unique_skus

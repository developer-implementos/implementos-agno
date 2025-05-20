import datetime
import json
import concurrent.futures
from agno.tools import Toolkit
import clickhouse_connect
from databases.clickhouse_client import config
from typing import List


class DataVentasTool(Toolkit):
    def __init__(self):
        super().__init__(name="DataVentasTool", cache_results=True, cache_ttl=3000)
        self.register(self.run_select_query)
        self.register(self.list_schema)
        self.register(self.run_query_batch)

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

    def list_schema(self):
        """Schema Table ventas"""

        return """
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
        - tipoTransaccion (String): tipo de Documento fiscal
        - sku (String): Código producto
        - cantidad (Int32): Unidades vendidas
        - precio (Float64): Precio unitario
        - descuento (Float64): Descuento aplicado
        - totalNetoItem (Float64): Total línea en valor neto
        - totalMargenItem (Float64): contribucion de la linea de transaccion
        - uen/categoria/linea (String): Clasificación del producto (mayusculas)
        """

    def execute_query(self, query: str):
        """Ejecuta una consulta SQL y devuelve los resultados como una lista de diccionarios"""
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

    def run_select_query(self, objetivo: str, query: str):
        """Ejecuta una consulta SELECT valida y sin errores en CLICKHOUSE

        Args:
            objetivo (str): Objetivo de la quwry que se busca conocer
            query (str): Solo el texto sin formato sin saltos de linea sin comentarios solo query sql valida en clickhouse

        Requisitos para las consultas:
            - Solo consultas SQL válidas para ClickHouse
            - VALORES NUMERICOS MAXIMO 1 DECIMAL

        Returns:
            str: Resultados en formato JSON.
        """
        try:
            # Validar que sea una consulta SELECT
            clean_query = query.strip()
            # print("objetivo:"+objetivo+" query:"+clean_query)
            result = self.execute_query(clean_query)
            result = self._format_numeric_values(result)

            def json_serializer(obj):
                if isinstance(obj, (datetime.date, datetime.datetime)):
                    return obj.isoformat()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

            json_result = json.dumps(result, ensure_ascii=False, indent=2, default=json_serializer)
            return json_result

        except concurrent.futures.TimeoutError:
            return "Error: Consulta cancelada por tiempo de espera excesivo."
        except Exception as err:
            print(clean_query)
            return f"Error al ejecutar la consulta: {err}"

    def _format_numeric_values(self, data):
        """Formatea valores numéricos: montos sin decimales, otros valores con 1 decimal."""
        if isinstance(data, list):
            return [self._format_numeric_values(item) for item in data]
        elif isinstance(data, dict):
            result = {}
            for key, value in data.items():
                if isinstance(value, float):
                    # Valores grandes (montos) sin decimales
                    if abs(value) >= 10:
                        result[key] = int(round(value, 0))
                    # Valores pequeños (porcentajes, ratios) con 1 decimal
                    else:
                        result[key] = round(value, 1)
                else:
                    result[key] = self._format_numeric_values(value)
            return result
        else:
            return data

    def run_query_batch(self, query_batch: List[dict]):
        """Ejecuta un lote de consultas SQL en ClickHouse.

        Args:
            query_batch (List[dict]): Lista de diccionarios con formato {objetivo:"", query:""}

        Requisitos para las consultas:
            - Solo consultas SQL válidas para ClickHouse
            - VALORES NUMERICOS MAXIMO 1 DECIMAL
            - Texto sin formato, sin saltos de línea, sin comentarios
            - Deben ser consultas exploratorias o de agregación (tipo resumen)
            - Cada consulta debe limitar sus resultados a máximo 10 registros (usar LIMIT)

        Returns:
            str: JSON con lista de resultados con formato {objetivo:"", resultado:"", status:"success|error"}
        """
        if not isinstance(query_batch, list):
            return "Error: Se esperaba una lista de consultas."

        results = []

        for item in query_batch:
            if not isinstance(item, dict) or "objetivo" not in item or "query" not in item:
                results.append({
                    "objetivo": "desconocido",
                    "resultado": "Error: Formato incorrecto. Se esperaba {objetivo:'', query:''}",
                    "status": "error"
                })
                continue

            objetivo = item["objetivo"]
            query = item["query"]

            try:
                # Validar que sea una consulta SELECT
                clean_query = query.strip()
                # print("Bach: Objetivo:"+objetivo+" query:"+query)
                query_result = self.execute_query(clean_query)
                query_result = self._format_numeric_values(query_result)
                results.append({
                    "objetivo": objetivo,
                    "resultado": query_result,
                    "status": "success"
                })

            except Exception as err:
                results.append({
                    "objetivo": objetivo,
                    "resultado": f"Error: {str(err)}",
                    "status": "error"
                })

        # Agregar el serializador JSON para manejar fechas
        def json_serializer(obj):
            if isinstance(obj, (datetime.date, datetime.datetime)):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        return json.dumps(results, ensure_ascii=False, indent=2, default=json_serializer)

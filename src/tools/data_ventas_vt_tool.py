import json
import concurrent.futures
import clickhouse_connect
from agno.tools import Toolkit
from databases.clickhouse_client import config


class DataVentasVTTool(Toolkit):
    def __init__(self):
        super().__init__(name="DataVentasTools",cache_results=True,cache_ttl=3000)
        self.register(self.run_select_query)
        self.register(self.list_schema)  # Registramos list_schema para que sea visible
        self.register(self.validate_and_rewrite_sql)
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
        """Schema Table ventasrealtime in database implementos"""
        
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
                - uen/categoria/linea (String): Clasificación del producto (mayusculas)

                ÍNDICE: (rutCliente, documento, tipoTransaccion, fecha)
                ORDENADO POR: (fecha, rutCliente, sku, uen, categoria, linea, codVendedor, sucursal)
                ENGINE: MergeTree
                
                Tabla: implementos.estado_tiendas
                Descripción: muestra si un sku esta en el assortment de una tienda y su tipologias de importancia 
                COLUMNAS
                - sku (String): Codigo de producto
                - sucursal (String): Sucursal / tienda
                - tipologiaTienda (Int32): tipo de importancia para la tienda (1 y 2 son los mas importantes)
                - tipologiaCompania (Int32): tipo de importancia para la compañia (1 y 2 son los mas importantes)
                - assortment (Int32): 1 o 0 indica si es parte del assortment de la tienda
                ÍNDICE: (sucursal, sku)
                ORDENADO POR: (sucursal, sku)
                ENGINE = MergeTree             
                """

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
        
        except concurrent.futures.TimeoutError:
            return f"Queries taking longer currently not supported."
    
    def validate_and_rewrite_sql(self, query: str) -> str:
        """
        1. Valida la sintaxis con EXPLAIN.
        2. Devuelve el SQL original si es válido.
        """
        try:
            # EXPLAIN no ejecuta, solo comprueba sintaxis
            self.execute_query(f"EXPLAIN {query}")
            return query
        except Exception as e:
            # En caso de error, levanta para que el agente lo maneje
            raise RuntimeError(f"Error de sintaxis SQL: {e}")    
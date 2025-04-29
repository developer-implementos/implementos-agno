import json
import requests
from typing import List, Optional
from datetime import datetime
from pymongo import MongoClient
from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger
from bson.json_util import dumps
from config.config import Config
from databases.clickhouse_client import config
import clickhouse_connect

class ClientesVtTool(Toolkit):
    def __init__(self):
        super().__init__(name="clientes_vt_tool")
        # Registrar las funciones en el toolkit para que sean accesibles dinámicamente
        self.register(self.clientes_bloqueados)
        self.register(self.contactos_cliente)
        self.register(self.direcciones_cliente)
        self.register(self.facturas_cliente)
        self.register(self.listado_clientes_co)
        self.register(self.pedidos_pendientes_cliente)
        self.register(self.resumen_cliente)
        self.register(self.segmentos_cliente)
        self.register(self.uen_fugadas_cliente)
        self.register(self.ultima_compra_cliente)
        self.register(self.flota_cliente)
        self.register(self.pedidos_pendientes_por_estado)

    def _obtener_ruts_cartera_objetivo(self, codigo_empleado: str) -> List[str]:
        """
        Obtiene los RUTs de la cartera objetivo de un vendedor.
        
        Args:
            codigo_empleado (str): Código del empleado
            
        Returns:
            List[str]: Lista de RUTs de la cartera objetivo
        """
        try:
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            cartera_objetivo = db.CarteraObjetivo
            
            data = cartera_objetivo.aggregate([
                {
                    "$match": {
                        "codigoEmpleado": codigo_empleado,
                        "estadoVigente": 1
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "rut": "$rutCliente"
                    }
                }
            ])
            
            result = list(data)
            client.close()
            
            ruts = [item["rut"] for item in result]
            return ruts
        except Exception as e:
            logger.error(f"Error al obtener RUTs de cartera objetivo: {e}")
            return []

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
        
    def clientes_bloqueados(self, codigo_empleado: str, ruts: Optional[List[str]] = None) -> str:
        """
        Función para buscar clientes bloqueados por sus RUTs
        
        Args:
            codigo_empleado (str): Código del empleado para obtener su cartera objetivo
            ruts (Optional[List[str]]): Lista de RUTs de clientes a buscar. Si no se proporciona, 
                                         se usan todos los RUTs de la cartera objetivo.
            
        Returns:
            str: Información de los clientes bloqueados en formato JSON
        """
        try:
            if ruts is None:
                ruts = self._obtener_ruts_cartera_objetivo(codigo_empleado)
                if not ruts:
                    return json.dumps({
                        "ok": False,
                        "mensaje": "No se encontraron RUTs en la cartera objetivo"
                    }, ensure_ascii=False, indent=2)
            
            log_debug(f"Consultando clientes bloqueados con RUTs: {ruts}")
            
            # Limpiar los RUTs (quitar puntos)
            ruts_clean = [rut.replace(".", "") for rut in ruts]
            
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            clientes = db.clientes
            
            data = clientes.aggregate([
                {
                    "$match": {
                        "rut": {
                            "$in": ruts_clean
                        },
                        "estado": {
                            "$in": ["TODO", "FACTURA"]
                        }
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "rut": 1,
                        "nombre": 1,
                        "estado": 1,
                        "nombreMotivoBloqueo": 1,
                        "documento_cobros.folio": 1,
                        "documento_cobros.estado": 1,
                        "documento_cobros.saldo": 1,
                        "documento_cobros.fechaVencimiento": 1
                    }
                }
            ])
            
            result = list(data)
            
            mapped_result = []
            for cliente in result:
                documento_cobros = cliente.get("documento_cobros", [])
                deuda_total = sum(doc.get("saldo", 0) for doc in documento_cobros)
                
                facturas = []
                for doc in documento_cobros:
                    estado = "POR VENCER" if doc.get("estado") == "ABIERTA" else doc.get("estado")
                    factura = {
                        "folio": doc.get("folio"),
                        "estado": estado,
                        "saldo": doc.get("saldo"),
                        "fecha_vencimiento": doc.get("fechaVencimiento")
                    }
                    facturas.append(factura)
                
                facturas.sort(key=lambda x: x["fecha_vencimiento"] if x["fecha_vencimiento"] else datetime.max)
                
                mapped_cliente = {
                    "rut": cliente.get("rut"),
                    "nombre": cliente.get("nombre"),
                    "tipo": cliente.get("estado"),
                    "motivo": cliente.get("nombreMotivoBloqueo", "No Registrado"),
                    "deuda_total": deuda_total,
                    "facturas": facturas
                }
                mapped_result.append(mapped_cliente)
            
            mapped_result.sort(key=lambda x: x["nombre"])
            
            client.close()
            
            log_debug(f"Se encontraron {len(mapped_result)} clientes bloqueados")
            return json.dumps(mapped_result, ensure_ascii=False, indent=2, default=str)
            
        except Exception as e:
            error_message = f"Error al buscar clientes bloqueados: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def contactos_cliente(self, rut: str) -> str:
        """
        Función para obtener los contactos de un cliente por su RUT
        
        Args:
            rut (str): RUT del cliente a consultar
            
        Returns:
            str: Información de los contactos del cliente en formato JSON
        """
        try:
            rut_clean = rut.replace(".", "")
            
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            clientes_ia = db.ClienteIA
            
            data = clientes_ia.aggregate([
                {
                    "$match": {
                        "clienteId": rut_clean
                    }
                },
                {
                    "$unwind": "$contactos"
                },
                {
                    "$project": {
                        "_id": 0,
                        "rut_cliente": "$clienteId",
                        "nombre": "$contactos.nombre",
                        "apellido": "$contactos.apellido",
                        "correo": "$contactos.correo",
                        "telefono": "$contactos.telefono",
                        "cargo": "$contactos.cargo"
                    }
                }
            ])
            
            result = list(data)
            
            client.close()
            
            log_debug(f"Se encontraron {len(result)} contactos para el cliente con RUT {rut}")
            return json.dumps(result, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al buscar contactos del cliente con RUT {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def direcciones_cliente(self, rut: str) -> str:
        """
        Función para obtener las direcciones de un cliente por su RUT
        
        Args:
            rut (str): RUT del cliente a consultar
            
        Returns:
            str: Información de las direcciones del cliente en formato JSON
        """
        try:
            rut_clean = rut.replace(".", "")
            
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            clientes_ia = db.ClienteIA
            
            data = clientes_ia.aggregate([
                {
                    "$match": {
                        "clienteId": rut_clean
                    }
                },
                {
                    "$unwind": "$direcciones"
                },
                {
                    "$project": {
                        "_id": 0,
                        "rut_cliente": "$clienteId",
                        "nombre": "$nombre",
                        "tipo": "$direcciones.tipo",
                        "direccion": "$direcciones.direccionCompleta"
                    }
                }
            ])
            
            result = list(data)
            
            for item in result:
                if "direccion" in item and item["direccion"]:
                    item["direccion"] = item["direccion"].replace("\n", " ")
            
            client.close()
            
            log_debug(f"Se encontraron {len(result)} direcciones para el cliente con RUT {rut}")
            return json.dumps(result, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al buscar direcciones del cliente con RUT {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def facturas_cliente(self, codigo_empleado: str, ruts: Optional[List[str]] = None) -> str:
        """
        Función para obtener las facturas pendientes de clientes
        
        Args:
            codigo_empleado (str): Código del empleado para obtener su cartera objetivo
            ruts (Optional[List[str]]): Lista de RUTs de clientes a consultar. Si no se proporciona,
                                        se usan todos los RUTs de la cartera objetivo.
            
        Returns:
            str: Información de las facturas pendientes en formato JSON
        """
        try:
            if ruts is None:
                ruts = self._obtener_ruts_cartera_objetivo(codigo_empleado)
                if not ruts:
                    return json.dumps({
                        "ok": False,
                        "mensaje": "No se encontraron RUTs en la cartera objetivo"
                    }, ensure_ascii=False, indent=2)
            
            # Limpiar los RUTs (quitar puntos)
            ruts_clean = [rut.replace(".", "") for rut in ruts]
            
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            clientes = db.clientes
            
            data = clientes.aggregate([
                {
                    "$match": {
                        "rut": {
                            "$in": ruts_clean
                        }
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "rut": 1,
                        "nombre": 1,
                        "estado": 1,
                        "nombreMotivoBloqueo": 1,
                        "documento_cobros.folio": 1,
                        "documento_cobros.estado": 1,
                        "documento_cobros.saldo": 1,
                        "documento_cobros.fechaVencimiento": 1
                    }
                }
            ])
            
            result = list(data)
            
            mapped_result = []
            for cliente in result:
                documento_cobros = cliente.get("documento_cobros", [])
                deuda_total = sum(doc.get("saldo", 0) for doc in documento_cobros)
                
                facturas = []
                for doc in documento_cobros:
                    estado = "POR VENCER" if doc.get("estado") == "ABIERTA" else doc.get("estado")
                    factura = {
                        "folio": doc.get("folio"),
                        "estado": estado,
                        "saldo": doc.get("saldo"),
                        "fecha_vencimiento": doc.get("fechaVencimiento")
                    }
                    facturas.append(factura)
                
                facturas.sort(key=lambda x: x["fecha_vencimiento"] if x["fecha_vencimiento"] else datetime.max)
                
                mapped_cliente = {
                    "rut": cliente.get("rut"),
                    "nombre": cliente.get("nombre"),
                    "tipo": cliente.get("estado"),
                    "motivo": cliente.get("nombreMotivoBloqueo", "No Registrado"),
                    "deuda_total": deuda_total,
                    "facturas": facturas
                }
                mapped_result.append(mapped_cliente)
            
            mapped_result.sort(key=lambda x: x["nombre"])
            
            client.close()
            
            log_debug(f"Se encontraron {len(mapped_result)} clientes con facturas pendientes")
            return json.dumps(mapped_result, ensure_ascii=False, indent=2, default=str)
            
        except Exception as e:
            error_message = f"Error al buscar facturas pendientes: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def listado_clientes_co(self, cod_empleado: str) -> str:
        """
        Función para obtener el listado de clientes de la cartera objetivo
        
        Args:
            cod_empleado (str): Código del empleado
            
        Returns:
            str: Listado de clientes de la cartera objetivo en formato JSON
        """
        try:
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            cartera_objetivo = db.CarteraObjetivo
            
            data = cartera_objetivo.aggregate([
                {
                    "$match": {
                        "codigoEmpleado": cod_empleado,
                        "estadoVigente": 1
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "rut": "$rutCliente",
                        "nombre": "$nombreCliente"
                    }
                }
            ])
            
            result = list(data)
            
            result.sort(key=lambda x: x["nombre"])
            
            client.close()
            
            log_debug(f"Se encontraron {len(result)} clientes en la cartera objetivo del empleado {cod_empleado}")
            return json.dumps(result, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al buscar clientes de la cartera objetivo: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def pedidos_pendientes_cliente(self, rut: str, rut_vendedor: str) -> str:
        """
        Función para obtener los pedidos pendientes de un cliente
        
        Args:
            rut (str): RUT del cliente (0 para todos los clientes)
            rut_vendedor (str): RUT del vendedor
            
        Returns:
            str: Información de los pedidos pendientes en formato JSON
        """
        try:
            rut_clean = rut.replace(".", "") if rut else "0"
            rut_vendedor_clean = rut_vendedor.replace(".", "")
            
            desde = datetime.now().replace(day=1, month=datetime.now().month-2 if datetime.now().month > 2 else 10, year=datetime.now().year if datetime.now().month > 2 else datetime.now().year-1).strftime("%Y%m%d")
            hasta = datetime.now().strftime("%Y%m%d")
            
            url = f"https://replicacion.implementos.cl/ApiVendedor/api/vendedor/consultar-pedidos?rutVendedor={rut_vendedor_clean}&rutsClientes={rut_clean}&desde={desde}&hasta={hasta}&tipo=0"
            
            headers = {
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                data = result.get("data", [])
                
                mapped_data = []
                for pedido in data:
                    mapped_pedido = {
                        "folio": pedido.get("numero"),
                        "rut": pedido.get("rutCliente"),
                        "nombre": pedido.get("nombreCliente"),
                        "fecha_documento": pedido.get("fechaDocumento"),
                        "estado_proceso": pedido.get("estado"),
                        "estado_ax": pedido.get("estadoAX"),
                        "total_neto": pedido.get("totalNeto")
                    }
                    mapped_data.append(mapped_pedido)
                
                log_debug(f"Se encontraron {len(mapped_data)} pedidos pendientes para el cliente con RUT {rut}")
                return json.dumps(mapped_data, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error en la solicitud a la API: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al consultar pedidos pendientes para cliente con RUT {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def resumen_cliente(self, codigo_empleado: str, ruts: Optional[List[str]] = None) -> str:
        """
        Función para obtener el resumen de clientes
        
        Args:
            codigo_empleado (str): Código del empleado para obtener su cartera objetivo
            ruts (Optional[List[str]]): Lista de RUTs de clientes a consultar. Si no se proporciona,
                                        se usan todos los RUTs de la cartera objetivo.
            
        Returns:
            str: Resumen de los clientes en formato JSON
        """
        try:
            if ruts is None:
                ruts = self._obtener_ruts_cartera_objetivo(codigo_empleado)
                if not ruts:
                    return json.dumps({
                        "ok": False,
                        "mensaje": "No se encontraron RUTs en la cartera objetivo"
                    }, ensure_ascii=False, indent=2)
            
            # Limpiar los RUTs (quitar puntos)
            ruts_clean = [rut.replace(".", "") for rut in ruts]
            
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            clientes_ia = db.ClienteIA
            
            data = clientes_ia.aggregate([
                {
                    "$match": {
                        "clienteId": {
                            "$in": ruts_clean
                        }
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "rut": "$clienteId",
                        "nombre": "$nombre",
                        "credito": "$credito",
                        "credito_utilizado": "$creditoUtilizado",
                        "facturas_pendientes": {"$size": "$facturasPendientes"},
                        "ciclo_vida": "$cicloVida",
                        "bloqueo": "$bloqueo",
                        "tipo_bloqueo": "$tipoBloqueo"
                    }
                }
            ])
            
            result = list(data)
            
            client.close()
            
            log_debug(f"Se obtuvo el resumen para {len(result)} clientes")
            return json.dumps(result, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al obtener resumen de clientes: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def segmentos_cliente(self, codigo_empleado: str, ruts: Optional[List[str]] = None) -> str:
        """
        Función para obtener los segmentos de clientes
        
        Args:
            codigo_empleado (str): Código del empleado para obtener su cartera objetivo
            ruts (Optional[List[str]]): Lista de RUTs de clientes a consultar. Si no se proporciona,
                                        se usan todos los RUTs de la cartera objetivo.
            
        Returns:
            str: Información de los segmentos de clientes en formato JSON
        """
        try:
            if ruts is None:
                ruts = self._obtener_ruts_cartera_objetivo(codigo_empleado)
                if not ruts:
                    return json.dumps({
                        "ok": False,
                        "mensaje": "No se encontraron RUTs en la cartera objetivo"
                    }, ensure_ascii=False, indent=2)
            
            segmentos_diccionario = {
                "TODOS": "TODOS",
                "TLC": "TELECOMUNICACIONES",
                "SDI": "SUB DISTRIBUCION (E)",
                "SAE": "SIN INICIACION DE ACTIVIDADES (E)",
                "TPA": "TRANSPORTE DE PASAJEROS",
                "OTRNS": "OTROS TIPOS DE TRANSPORTES",
                "TMEC": "TALLERES MECANICOS",
                "SLD": "SALUD",
                "OEM": "OEM (E)",
                "CNST": "CONSTRUCCION",
                "COM": "COMERCIO",
                "ARM": "ARMADORES",
                "REP": "REPUESTEROS",
                "AGRO": "AGROPECUARIO",
                "DCOMB": "DISTRIBUIDORES DE COMBUSTIBLES",
                "SPRT": "SERVICIOS PARTICULARES",
                "EDU": "EDUCACION",
                "IND": "INDUSTRIAL",
                "GBN": "GUBERNAMENTAL",
                "MIN": "MINERIA",
                "TCA": "TRANSPORTE DE CARGA",
                "ML": "MERCADO LIBRE (E)"
            }
            
            # Limpiar los RUTs (quitar puntos)
            ruts_clean = [rut.replace(".", "") for rut in ruts]
            
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            clientes = db.clientes
            
            data = clientes.aggregate([
                {
                    "$match": {
                        "rut": {
                            "$in": ruts_clean
                        }
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "rut": 1,
                        "nombre": 1,
                        "segmento": {
                            "$ifNull": ["$segmento", "TCA"]
                        }
                    }
                }
            ])
            
            result = list(data)
            
            for cliente in result:
                segmento_codigo = cliente.get("segmento", "TCA")
                cliente["nombre_segmento"] = segmentos_diccionario.get(segmento_codigo, segmentos_diccionario["TCA"])
            
            client.close()
            
            log_debug(f"Se obtuvieron segmentos para {len(result)} clientes")
            return json.dumps(result, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al obtener segmentos de clientes: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def uen_fugadas_cliente(self, codigo_empleado: str, ruts: Optional[List[str]] = None) -> str:
        """
        Función para obtener las UEN fugadas de clientes
        
        Args:
            codigo_empleado (str): Código del empleado para obtener su cartera objetivo
            ruts (Optional[List[str]]): Lista de RUTs de clientes a consultar. Si no se proporciona,
                                        se usan todos los RUTs de la cartera objetivo.
            
        Returns:
            str: Información de las UEN fugadas en formato JSON
        """
        try:
            if ruts is None:
                ruts = self._obtener_ruts_cartera_objetivo(codigo_empleado)
                if not ruts:
                    return json.dumps({
                        "ok": False,
                        "mensaje": "No se encontraron RUTs en la cartera objetivo"
                    }, ensure_ascii=False, indent=2)
            
            # Limpiar los RUTs (quitar puntos)
            ruts_clean = [rut.replace(".", "") for rut in ruts]
            
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            clientes_ia = db.ClienteIA
            
            data = clientes_ia.aggregate([
                {
                    "$match": {
                        "clienteId": {
                            "$in": ruts_clean
                        }
                    }
                },
                {
                    "$unwind": "$resumenComercial"
                },
                {
                    "$match": {
                        "resumenComercial.estado": {
                            "$in": ["PELIGRO FUGA", "FUGADO"]
                        }
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "rut": "$clienteId",
                        "nombre": "$nombre",
                        "uen": "$resumenComercial.uen",
                        "estado": "$resumenComercial.estado"
                    }
                }
            ])
            
            result = list(data)
            
            client.close()
            
            log_debug(f"Se encontraron {len(result)} UEN fugadas para los clientes consultados")
            return json.dumps(result, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al obtener UEN fugadas de clientes: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def ultima_compra_cliente(self, rut: str) -> str:
        """
        Función para obtener la última compra de cliente
        
        Args:
            rut (str): RUT de cliente a consultar
            
        Returns:
            str: Información de las últimas compras en formato JSON
        """
        try:
            query = f"""
            SELECT 
              rutCliente as rut, 
              nombreCliente as nombre, 
              documento as folio, 
              ov as ov, 
              fecha as fecha, 
              sku as sku, 
              uen as uen, 
              categoria as categoria, 
              linea as linea,
              totalNetoItem as total
            FROM implementos.ventasrealtime
            WHERE (rutCliente, documento) IN (
                SELECT rutCliente, documento
                FROM (
                    SELECT 
                        rutCliente,
                        documento,
                        ROW_NUMBER() OVER (PARTITION BY rutCliente ORDER BY MAX(fecha) DESC, documento DESC) AS rn
                    FROM implementos.ventasrealtime
                    WHERE 
                        rutCliente = '{rut}' AND
                        tipoTransaccion IN ('FEL', 'BEL')
                    GROUP BY rutCliente, documento
                ) 
                WHERE rn = 1
            )
            ORDER BY rutCliente, sku
            """
            
            log_debug(f"Consulta de últimas compras para {rut}")
            result = self.execute_query(query)

            return json.dumps(result, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al obtener últimas compras de cliente: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def flota_cliente(self, rut: str, marcas: List[str] = None, anio_min: int = None, anio_max: int = None) -> str:
        """
        Función para obtener la flota de vehículos de un cliente
        
        Args:
            rut (str): RUT de cliente a consultar
            marcas (List[str], optional): Lista de marcas de vehículos a filtrar
            anio_min (int, optional): Año mínimo de fabricación
            anio_max (int, optional): Año máximo de fabricación
            
        Returns:
            str: Información de la flota de vehículos en formato JSON
        """
        try:
            
            query = f"""
            SELECT 
              rut as rut,
              nombre as nombre,
              placaPatente as patente,
              marca as marca,
              modelo as modelo,
              anioFabricacion as anio_fabricacion,
              vin as vin,
              tipoVehiculo as tipo_vehiculo
            FROM 
              implementos.flota_cliente
            WHERE rut = '{rut}'
            """
            
            if marcas and len(marcas) > 0:
                marcas_quoted = ", ".join([f"'{marca}'" for marca in marcas])
                query += f" AND marca IN ({marcas_quoted})"
                
            if anio_min and anio_min > 0:
                query += f" AND anioFabricacion >= {anio_min}"
                
            if anio_max and anio_max > 0:
                query += f" AND anioFabricacion <= {anio_max}"
            
            log_debug(f"Consulta de flota para {rut} clientes")

            result = self.execute_query(query)

            return json.dumps(result, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al obtener flota de cliente: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def pedidos_pendientes_por_estado(self, rut: str, rut_vendedor: str, estados_pedido: List[str] = None) -> str:
        """
        Función para obtener los pedidos pendientes de un cliente filtrados por estado
        
        Args:
            rut (str): RUT del cliente (0 para todos los clientes)
            rut_vendedor (str): RUT del vendedor
            estados_pedido (List[str], optional): Lista de estados de pedido para filtrar
            
        Returns:
            str: Información de los pedidos pendientes en formato JSON
        """
        try:
            # Estados de pedido disponibles
            ESTADOS_PEDIDO = {
                "POR_FACTURAR": "POR FACTURAR",
                "FACTURA_POR_SINCRONIZAR": "FACTURA POR SINCRONIZAR",
                "POR_VENCER": "POR VENCER",
                "POR_CONVERTIR": "POR CONVERTIR"
            }
            
            rut_clean = rut.replace(".", "") if rut else "0"
            rut_vendedor_clean = rut_vendedor.replace(".", "")
            
            # Calcular fechas
            fecha_hasta = datetime.now()
            if fecha_hasta.month > 2:
                fecha_desde = fecha_hasta.replace(day=1, month=fecha_hasta.month-2)
            else:
                mes = 10 + fecha_hasta.month
                fecha_desde = fecha_hasta.replace(day=1, month=mes, year=fecha_hasta.year-1)
                
            desde = fecha_desde.strftime("%Y%m%d")
            hasta = fecha_hasta.strftime("%Y%m%d")
            
            url = f"https://replicacion.implementos.cl/ApiVendedor/api/vendedor/consultar-pedidos?rutVendedor={rut_vendedor_clean}&rutsClientes={rut_clean}&desde={desde}&hasta={hasta}&tipo=0"
            
            headers = {
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                pedidos_pendientes = result.get("data", [])
                
                # Filtrar por estados si se especifican
                if estados_pedido and len(estados_pedido) > 0:
                    # Normalizar estados de pedido
                    estados_normalizados = [estado.replace("-", " ").upper() for estado in estados_pedido]
                    pedidos_pendientes = [pedido for pedido in pedidos_pendientes 
                                        if pedido.get("estado") in estados_normalizados]
                
                # Contar por estado
                contador_estados = {
                    "por_facturar": 0,
                    "por_sincronizar": 0,
                    "por_vencer": 0,
                    "por_convertir": 0
                }
                
                for pedido in pedidos_pendientes:
                    estado = pedido.get("estado")
                    if estado == ESTADOS_PEDIDO["POR_FACTURAR"]:
                        contador_estados["por_facturar"] += 1
                    elif estado == ESTADOS_PEDIDO["FACTURA_POR_SINCRONIZAR"]:
                        contador_estados["por_sincronizar"] += 1
                    elif estado == ESTADOS_PEDIDO["POR_VENCER"]:
                        contador_estados["por_vencer"] += 1
                    elif estado == ESTADOS_PEDIDO["POR_CONVERTIR"]:
                        contador_estados["por_convertir"] += 1
                
                # Mapear los resultados
                mapped_data = []
                for pedido in pedidos_pendientes:
                    mapped_pedido = {
                        "folio": pedido.get("numero"),
                        "rut": pedido.get("rutCliente"),
                        "nombre": pedido.get("nombreCliente"),
                        "fecha_documento": pedido.get("fechaDocumento"),
                        "estado_proceso": pedido.get("estado"),
                        "estado_ax": pedido.get("estadoAX"),
                        "total_neto": pedido.get("totalNeto")
                    }
                    mapped_data.append(mapped_pedido)
                
                # Añadir resumen
                result_data = {
                    "pedidos": mapped_data,
                    "resumen": {
                        "por_facturar": contador_estados["por_facturar"],
                        "por_sincronizar": contador_estados["por_sincronizar"],
                        "por_vencer": contador_estados["por_vencer"],
                        "por_convertir": contador_estados["por_convertir"],
                        "total": len(mapped_data)
                    }
                }
                
                log_debug(f"Se encontraron {len(mapped_data)} pedidos pendientes para el cliente con RUT {rut}")
                return json.dumps(result_data, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error en la solicitud a la API: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al consultar pedidos pendientes por estado para cliente con RUT {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
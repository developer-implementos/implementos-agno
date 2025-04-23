import json
import requests
from typing import List
from datetime import datetime
from pymongo import MongoClient
from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger
from bson.json_util import dumps
from config.config import Config

class ClientesTool(Toolkit):
    def __init__(self):
        super().__init__(name="clientes_tool")
        # Registrar las funciones en el toolkit para que sean accesibles dinámicamente.
        self.register(self.buscar_cliente_por_rut)
        self.register(self.buscar_direcciones_cliente)
        self.register(self.buscar_vehiculos_cliente)
        self.register(self.search_cliente_nombre)
        self.register(self.pedidos_pendientes)
        self.register(self.notas_credito_cliente)
        self.register(self.clientes_facturas_pendientes)
        self.register(self.productos_recomendados)
    def buscar_cliente_por_rut(self, rut: str) -> str:
        """
        Función para buscar un cliente por su RUT 
        
        Args:
            rut (str): RUT del cliente a buscar
        
        Returns:
            str: Información del cliente en formato JSON si se encuentra, error en caso contrario
        """
        try:
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            clientes = db.clientes
            
            campos = {
                "rut": 1,
                "apellido": 1,
                "correos": 1,
                "nombre": 1,
                "telefonos": 1,
                "direcciones": 1,
                "ciudad": 1,
                "provincia": 1,
                "clasificacionFinanciera": 1,
                "tipoCartera": 1,
                "credito": 1,
                "creditoUtilizado": 1,
                "giros": 1,
                "segmento": 1,
                "subSegmento": 1,
                "contactos": 1,
                "zona": 1,
                "sucPrecio": 1,
                "ultimaCompra": 1,
                "sucCompra": 1,
                "ultimaOv": 1,
                "creditoDisponible": 1,
                "segmentoBI": 1,
                "estado":"",
                "nombreMotivoBloqueo":1,
                "_id": 0  # Excluir el campo _id
            }
            
            # Buscar cliente por RUT incluyendo solo los campos especificados
            cliente = clientes.find_one({"rut": rut}, projection=campos)
            
            # Cerrar la conexión
            client.close()
            
            # Filtrar campos adicionales en las direcciones
            if cliente and 'direcciones' in cliente:
                direcciones_filtradas = []
                for direccion in cliente['direcciones']:
                    direccion_filtrada = {
                        'calle': direccion.get('calle', ''),
                        'numero': direccion.get('numero', ''),
                        'comuna': direccion.get('comuna', ''),
                        'direccionCompleta': direccion.get('direccionCompleta', ''),
                        'tipo': direccion.get('tipo', ''),
                        'localidad': direccion.get('localidad', '')
                    }
                    direcciones_filtradas.append(direccion_filtrada)
                cliente['direcciones'] = direcciones_filtradas
                
            # Filtrar campos adicionales en los contactos
            if cliente and 'contactos' in cliente:
                contactos_filtrados = []
                for contacto in cliente['contactos']:
                    contacto_filtrado = {
                        'nombre': contacto.get('nombre', ''),
                        'apellido': contacto.get('apellido', ''),
                        'contactoDe': contacto.get('contactoDe', ''),
                        'telefono': contacto.get('telefono', ''),
                        'correo': contacto.get('correo', ''),
                        'cargo': contacto.get('cargo', '')
                    }
                    contactos_filtrados.append(contacto_filtrado)
                cliente['contactos'] = contactos_filtrados
            
            # Convertir el resultado a diccionario Python
            if cliente and 'ultimaCompra' in cliente and cliente['ultimaCompra']:
                cliente['ultimaCompra'] = cliente['ultimaCompra'].isoformat()
                
            if cliente:
                cliente_json = json.dumps(cliente, ensure_ascii=False, indent=2)
                log_debug(f"Cliente con RUT {rut} encontrado correctamente")
                return cliente_json
            
            log_debug(f"No se encontró cliente con el RUT: {rut}")
            return json.dumps({"error": f"No se encontró cliente con el RUT: {rut}"}, ensure_ascii=False, indent=2)
        
        except Exception as e:
            error_message = f"Error al buscar cliente con RUT {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
   
    def clientes_bloqueados(self, rut_list: List[str]) -> str:
        """
        Función para buscar clientes bloqueados por su RUT
        
        Args:
            rut_list (List[str]): Lista de RUTs de clientes a buscar
            
        Returns:
            str: Información de los clientes bloqueados en formato JSON
        """
        try:
            # Establecer conexión con MongoDB
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            clientes = db.clientes
            log_debug(f"Consultando clientes bloqueados con RUTs: {rut_list}")
            
            # Campos a recuperar de la base de datos
            campos = {
                "rut": 1,
                "nombre": 1,
                "credito": 1,
                "creditoUtilizado": 1,
                "ultimaCompra": 1,
                "creditoDisponible": 1,
                "estado": 1,
                "cicloVida": 1,
                "nombreMotivoBloqueo": 1,
                "_id": 0  # Excluir el campo _id
            }
            
            # Buscar clientes por RUT que cumplan la condición de estado distinto a "NO"
            resultados = clientes.find(
                {
                    "rut": {"$in": rut_list},
                    "estado": {"$ne": "NO"}
                },
                projection=campos
            )
            
            # Convertir el cursor a una lista de diccionarios
            lista_resultados = list(resultados)
            
            # Utilizar bson.json_util.dumps para manejar tipos de datos de MongoDB
            clientes_json = dumps(lista_resultados, ensure_ascii=False)
            
            # Cerrar la conexión
            client.close()
            
            log_debug(f"Se encontraron {len(lista_resultados)} clientes bloqueados")
            return clientes_json
            
        except Exception as e:
            error_message = f"Error al buscar clientes bloqueados: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    def buscar_direcciones_cliente(self, rut: str) -> str:
        """
        Buscar direcciones de despacho de un cliente por su RUT 
        
        Args:
            rut (str): RUT del cliente a buscar
        
        Returns:
            str: Listado de direcciones de despacho en formato JSON
        """
        try:
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            clientes = db.clientes
            
            campos = {
                "rut": 1,
                "direcciones": 1,
                "_id": 0  # Excluir el campo _id
            }
            
            # Buscar cliente por RUT incluyendo solo los campos especificados
            cliente = clientes.find_one({"rut": rut}, projection=campos)
            
            # Cerrar la conexión
            client.close()
            
            # Filtrar campos adicionales en las direcciones
            if cliente and 'direcciones' in cliente:
                direcciones_filtradas = []
                for direccion in cliente['direcciones']:
                    direccion_filtrada = {
                        'comuna': direccion.get('comuna', ''),
                        'direccionCompleta': direccion.get('direccionCompleta', ''),
                        'tipo': direccion.get('tipo', '')
                    }
                    direcciones_filtradas.append(direccion_filtrada)
                cliente['direcciones'] = direcciones_filtradas    
          
            if cliente:
                cliente_json = json.dumps(cliente, ensure_ascii=False, indent=2)
                log_debug(f"Direcciones del cliente con RUT {rut} consultadas correctamente")
                return cliente_json
            
            log_debug(f"No se encontraron direcciones para el cliente con RUT: {rut}")
            return json.dumps({"error": f"No se encontraron direcciones para el cliente con RUT: {rut}"}, ensure_ascii=False, indent=2)
        
        except Exception as e:
            error_message = f"Error al buscar direcciones del cliente con RUT {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
     
    def productos_recomendados(self, rut: str, limite: int = 10) -> str:
        """
        Función para obtener productos SKU recomendados para un cliente basado en su RUT
        
        Args:
            rut (str): RUT del cliente
            limite (int, opcional): Número máximo de productos a devolver. Por defecto es 10.
        
        Returns:
            str: Lista de productos recomendados en formato JSON ordenados por probabilidad
        """
        try:
            # Establecer conexión con MongoDB
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            recomendaciones = db.recomendacion_clientes
            
            log_debug(f"Consultando productos recomendados para cliente con RUT: {rut}")
            
            # Campos a recuperar de la base de datos
            campos = {
                "rut": 1,
                "producto": 1,
                "probabilidad": 1,
                "_id": 0  # Excluir el campo _id
            }
            
            # Buscar recomendaciones por RUT y ordenarlas por probabilidad (descendente)
            resultados = recomendaciones.find(
                {"rut": rut},
                projection=campos
            ).sort("probabilidad", -1).limit(limite)
            
            # Convertir el cursor a una lista de diccionarios
            lista_recomendaciones = list(resultados)
            
            # Cerrar la conexión
            client.close()
            
            if lista_recomendaciones:
                # Formatear los resultados para devolverlos
                for item in lista_recomendaciones:
                    # Asegurar que la probabilidad sea un valor entre 0 y 1 con 2 decimales
                    if "probabilidad" in item:
                        item["probabilidad"] = round(float(item["probabilidad"]), 2)
                
                log_debug(f"Se encontraron {len(lista_recomendaciones)} productos recomendados para el cliente con RUT {rut}")
                return json.dumps(lista_recomendaciones, ensure_ascii=False, indent=2)
            else:
                log_debug(f"No se encontraron productos recomendados para el cliente con RUT: {rut}")
                return json.dumps({"error": f"No se encontraron productos recomendados para el cliente con RUT: {rut}"}, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al buscar productos recomendados para cliente con RUT {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
   
    def buscar_vehiculos_cliente(self, rut: str) -> str:
        """
        Función para buscar vehículos de un cliente 
        
        Args:
            rut (str): RUT del cliente a buscar
        
        Returns:
            str: Información de los vehículos en formato JSON
        """
        try:
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            clientes = db.RVM_RUT
            
            campos = {
                "RUT": 1,
                "NOMBRE": 1,
                "PLACA_PATENTE": 1,
                "MARCA": 1,
                "MODELO": 1,
                "TIPO_VEHICULO": 1,
                "ANO_FABRICACION": 1,
                "COLOR": 1,
                "COD_CHASIS": 1,
                "_id": 0 
            }
            
            cliente = clientes.find_one({"RUT": rut}, projection=campos)
            
            # Cerrar la conexión
            client.close()

            if cliente:
                cliente_json = json.dumps(cliente, ensure_ascii=False, indent=2)
                log_debug(f"Vehículos del cliente con RUT {rut} consultados correctamente")
                return cliente_json
            
            log_debug(f"No se encontraron vehículos para el cliente con RUT: {rut}")
            return json.dumps({"error": f"No se encontraron vehículos para el cliente con RUT: {rut}"}, ensure_ascii=False, indent=2)
        
        except Exception as e:
            error_message = f"Error al buscar vehículos del cliente con RUT {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
    def search_cliente_nombre(self, texto: str) -> str:
        """
        Buscar información de cliente por nombre
        
        Args:
            texto (str): texto a buscar.
            
        Returns:
            str: Resultado de la consulta en formato JSON.
        """
        try:
            # URL de la API
            api_url = f"https://replicacion.implementos.cl/apiOmnichannel/api/cliente/obtener?search={texto}"
            
            # Configurar los headers
            headers = {
                "Content-Type": "application/json"
            }
            
            # Realizar la solicitud GET
            response = requests.get(api_url, headers=headers)
            
            # Verificar si la solicitud fue exitosa
            if response.status_code == 200:
                # Convertir la respuesta a JSON
                result = response.json()
                
                formatted_result = json.dumps(result, ensure_ascii=False, indent=2)
                log_debug(f"Búsqueda de cliente por nombre '{texto}' completada correctamente")
                return formatted_result
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
        
        except Exception as e:
            error_message = f"Error al buscar cliente por nombre '{texto}': {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
    def pedidos_pendientes(self, rut: str) -> str:
        """
        Consulta pedidos(OV) o cotizaciones(CO) de un cliente y el estado (facturado, abierto, cancelado, pendiente)
        
        Args:
            rut (str): rut del cliente 
            
        Returns:
            str: Resultado de la consulta en formato JSON.
        """
        try:
            # URL de la API
            api_url = "https://b2b-api.implementos.cl/api/cliente/pedidosCRM"
            
            # Preparar los datos para la solicitud POST
            payload = {
                "rutCliente": rut,
                "limit": 30,
                "page": 1,
                "rutVendedor": 0
            }
            
            # Configurar los headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            # Realizar la solicitud POST
            response = requests.post(api_url, headers=headers, json=payload)
            
            # Verificar si la solicitud fue exitosa
            if response.status_code == 200:
                # Convertir la respuesta a JSON
                result = response.json()
                
                # Formatear el resultado para devolverlo
                formatted_result = json.dumps(result, ensure_ascii=False, indent=2)
                log_debug(f"Pedidos pendientes para cliente con RUT {rut} consultados correctamente")
                return formatted_result
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
                
        except Exception as e:
            error_message = f"Error al consultar pedidos pendientes para cliente con RUT {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
    def notas_credito_cliente(self, rut: str) -> str:
        """
        Consulta últimas notas de crédito de un cliente
        
        Args:
            rut (str): RUT del cliente
            
        Returns:
            str: Resultado de la consulta en formato JSON
        """
        try:
            # URL de la API
            api_url = "https://b2b-api.implementos.cl/api/cliente/notasCreditoCRM"
            
            # Preparar los datos para la solicitud POST
            payload = {
                "rut": rut,
                "limit": 30,
                "page": 1,
                "sort": "fecha|-1"
            }
            
            # Configurar los headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            # Realizar la solicitud POST
            response = requests.post(api_url, headers=headers, json=payload)
            
            # Verificar si la solicitud fue exitosa
            if response.status_code == 200:
                # Convertir la respuesta a JSON
                result = response.json()
                
                # Crear el array formateado con los datos requeridos
                formatted_data = []
                
                for item in result.get('data', []):
                    # Formatear la fecha como string en formato dd-mm-yyyy
                    fecha_obj = datetime.strptime(item.get('fecha', ''), '%Y-%m-%dT%H:%M:%S.000Z')
                    fecha_str = fecha_obj.strftime('%d-%m-%Y')
                    
                    # Crear diccionario con los datos solicitados
                    formatted_item = {
                        "fecha": fecha_str,
                        "folioDoc": item.get('folioDoc', ''),
                        "monto": item.get('monto', 0),
                        "ov": item.get('ov', ''),
                        "sucursal": item.get('sucursal', ''),
                        "vendedor": item.get('vendedor', '')
                    }
                    
                    formatted_data.append(formatted_item)
                
                formatted_result = json.dumps(formatted_data, ensure_ascii=False, indent=2)
                log_debug(f"Notas de crédito para cliente con RUT {rut} consultadas correctamente")
                return formatted_result
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al consultar notas de crédito para cliente con RUT {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
    def clientes_facturas_pendientes(self, rut: str) -> str:
        """
        Función para buscar facturas vencidas y pendientes de pago de un cliente por su RUT
        
        Args:
            rut (str): RUT de cliente a buscar
            
        Returns:
            str: JSON con la información de las facturas pendientes
        """
        try:
            # Establecer conexión con MongoDB
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            clientes = db.clientes
            
            # Campos a recuperar de la base de datos
            campos = {
                "rut": 1,
                "apellido": 1,
                "nombre": 1,
                "documento_cobros": 1,
                "_id": 0  # Excluir el campo _id
            }
            
            # Buscar cliente por RUT
            cliente = clientes.find_one(
                {
                    "rut": rut
                },
                projection=campos
            )
            
            # Si el cliente existe y tiene documentos de cobro
            facturas_pendientes = []
            if cliente and "documento_cobros" in cliente and cliente["documento_cobros"]:
                for documento in cliente["documento_cobros"]:
                    # Formatear fecha de vencimiento como string (fecha corta)
                    fecha_vencimiento = ""
                    if "fechaVencimiento" in documento:
                        fecha_vencimiento_obj = documento.get("fechaVencimiento")
                        if isinstance(fecha_vencimiento_obj, datetime):
                            fecha_vencimiento = fecha_vencimiento_obj.strftime("%d-%m-%Y")
                    
                    # Crear diccionario con los campos solicitados
                    factura = {
                        "nota_venta": documento.get("nota_venta", ""),
                        "folio": documento.get("folio", ""),
                        "fechaVencimiento": fecha_vencimiento,
                        "saldo": documento.get("saldo", 0),
                        "estado": documento.get("estado", "")
                    }
                    
                    facturas_pendientes.append(factura)
            
            # Información básica del cliente
            cliente_info = {
                "rut": cliente.get("rut", "") if cliente else "",
                "nombre": cliente.get("nombre", "") if cliente else "",
                "apellido": cliente.get("apellido", "") if cliente else "",
                "facturas_pendientes": facturas_pendientes
            }
            
            # Cerrar la conexión
            client.close()
            
            # Convertir a JSON
            resultado_json = json.dumps(cliente_info, ensure_ascii=False, indent=2)
            log_debug(f"Facturas pendientes para cliente con RUT {rut} consultadas correctamente")
            return resultado_json
            
        except Exception as e:
            error_message = f"Error al buscar facturas pendientes para cliente con RUT {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
import json
import requests
from typing import List
from pymongo import MongoClient
from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger
from datetime import datetime, date
from bson import ObjectId
from config.config import Config

class CarroEcommerceTool(Toolkit):
    def __init__(self):
        super().__init__(name="carro_ecommerce_tools")
        # Registrar las funciones en el toolkit para que sean accesibles dinámicamente
        self.register(self.listar_carro)
        self.register(self.gestionar_carro)
        self.register(self.generar_retiro_tienda)
        self.register(self.clientes_informacion)

    def listar_carro(self, rut: str, sucursal: str) -> str:
        """
        Listar carro abierto de un cliente
            
        Args:
            rut (str): rut cliente.
            sucursal (str): codigo de sucursal de tienda valido
                
        Returns:
            str: Resultado del carro de compra abierto en formato JSON.
        """
        try:
            # URL de la API
            api_url = f"https://b2b-api.implementos.cl/api/carro/omni?usuario={rut}&sucursal={sucursal}&rut={rut}&vendedor=jespinoza&ov=&folioPropuesta="
                
            # Configurar los headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
                
            # Realizar la solicitud GET
            response = requests.get(api_url, headers=headers)
            print(api_url)
            
            # Verificar si la solicitud fue exitosa
            if response.status_code == 200:
                # Convertir la respuesta a JSON
                result = response.json()
                        
                if not result or result.get('error', True) or 'data' not in result:
                    message = f"No se encontró carro abierto para el cliente con RUT {rut}"
                    log_debug(message)
                    return json.dumps({"message": message}, ensure_ascii=False, indent=2)
                        
                order_data = result['data']
                        
                # Prepare simplified product list
                simplified_products = []
                for product in order_data.get('productos', []):
                    simplified_product = {
                        'sku': product.get('sku', ''),
                        'nombre': product.get('nombre', ''),
                        'cantidad': product.get('cantidad', 0),
                        'precio': product.get('precio', 0)
                    }
                    simplified_products.append(simplified_product)
                        
                # Create summary object with just totalCarro and productos
                summary = {
                    'totalCarro': sum(product.get('precio', 0) * product.get('cantidad', 0) for product in order_data.get('productos', [])),
                    'productos': simplified_products
                }
                        
                formatted_result = json.dumps(summary, ensure_ascii=False, indent=2)
                log_debug(f"Carro consultado correctamente para cliente con RUT {rut}")
                return formatted_result
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
                
        except Exception as e:
            error_message = f"Error al consultar carro para cliente con RUT {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def gestionar_carro(self, rut: str, sucursal: str, accion: str, productos: List[dict] = None) -> str:
        """
        Gestiona un carro: agregar, editar, eliminar o listar carro de un cliente
        
        Args:
            rut (str): rut cliente.
            sucursal (str): codigo de sucursal de tienda
            accion (str): acción a realizar: "listar", "agregar", "editar", "eliminar", "pagar"
            productos (List[dict], optional): lista de productos a agregar/editar al carro,
                            donde cada producto es un diccionario con las claves 'sku' (str) y 'cantidad' (int).
                            Ejemplo: [{'sku': '123456', 'cantidad': 2}, {'sku': '789012', 'cantidad': 1}]
                            Para eliminar todos los productos, enviar una lista vacía.
            
        Returns:
            str: Resultado de la operación del carro de compra en formato JSON.
        """
        
        # Definir la URL de la API según la acción
        base_url = "https://b2b-api.implementos.cl/api/carro/omni"
        
        if accion == "pagar":
            api_url = f"https://b2b-api.implementos.cl/api/carro/omni?usuario={rut}&sucursal={sucursal}&rut={rut}&vendedor=jespinoza&ov=&folioPropuesta="
            
            # Realizar la solicitud GET
            headers = {
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            response = requests.get(api_url, headers=headers)
            if response.status_code == 200:
                result = response.json()
                
                # Verificar si hay datos en la respuesta del GET
                if not result or result.get('error', True) or 'data' not in result:
                    message = f"No hay productos en el carro para proceder al pago"
                    log_debug(message)
                    return json.dumps({"message": message}, ensure_ascii=False, indent=2)
                
                # Obtener los datos completos del carro
                datacarro = result.get("data", {})
                
                # Verificar si hay un ID de carro válido
                if not datacarro.get("_id", ""):
                    message = f"No se encontró un ID de carro válido para procesar el pago"
                    log_debug(message)
                    return json.dumps({"message": message}, ensure_ascii=False, indent=2)
                
                api_url_link = "https://b2b-api.implementos.cl/api/carro/crearCarroOmnichanel"
                
                # Modificar el datacarro para establecer la forma de pago
                datacarro["formaPago"] = "LINK_EC"
                datacarro["id"] =  datacarro["_id"]
                # Enviar el objeto datacarro completo en el body
                post_response = requests.post(api_url_link, headers=headers, json=datacarro)
                
                # Verificar si la solicitud POST fue exitosa
                if post_response.status_code == 200:
                    post_result = post_response.json()
                    print(post_result)
                    # Verificar si hay datos en la respuesta del POST
                    if post_result and not post_result.get('error', True):
                        # Extraer los datos relevantes del resultado
                        payment_link = post_result.get('data', {}).get('url', '')
                        payment_id = post_result.get('data', {}).get('id', '')
                        
                        # Crear un resumen del resultado
                        summary = {
                            'totalCarro': datacarro.get('totalCarro', 0),
                            'urlPago': payment_link,
                            'idPago': payment_id,
                            'productos': []
                        }
                        
                        # Añadir los productos al resumen si están disponibles
                        if 'productos' in datacarro and datacarro['productos']:
                            for product in datacarro['productos']:
                                simplified_product = {
                                    'sku': product.get('sku', ''),
                                    'nombre': product.get('nombre', ''),
                                    'cantidad': product.get('cantidad', 0),
                                    'precio': product.get('precio', 0)
                                }
                                summary['productos'].append(simplified_product)
      
                        return json.dumps(summary, ensure_ascii=False, indent=2)
                    else:
                        error_message = f"Error al generar el enlace de pago: {post_result.get('msg', 'Error desconocido')}"
                        log_debug(error_message)
                        return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
                else:
                    error_message = f"Error en la solicitud de pago: {post_response.status_code} - {post_response.text}"
                    log_debug(error_message)
                    return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error al obtener información del carrito: {response.status_code} - {response.text}"
                log_debug(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
        elif accion in ["agregar", "editar", "eliminar"]:
            if productos is None and accion != "eliminar":
                error_message = f"Error: Para la acción '{accion}' se requiere una lista de productos"
                log_debug(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
            # URL para operaciones de agregar/editar/eliminar
            api_url = f"{base_url}/articulo"
            
            # Si es eliminar con lista vacía, preparamos el cuerpo especial
            if accion == "eliminar" and (productos is None or len(productos) == 0):
                body = {
                    "usuario": rut,
                    "rut": rut,
                    "sucursal": sucursal,
                    "tipoCarro": "OMN",
                    "ov": "",
                    "folioPropuesta": "",
                    "folio": "",
                    "vendedor": "jespinoza",
                    "productos": []  # Lista vacía para eliminar todos los productos
                }
            else:
                # Preparar los productos en el formato correcto
                productos_formateados = []
                for producto in productos:
                    # Verificar que el producto tenga las claves necesarias
                    if 'sku' not in producto or 'cantidad' not in producto:
                        error_message = "Error: Cada producto debe contener 'sku' y 'cantidad'"
                        log_debug(error_message)
                        return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
                    
                    productos_formateados.append({
                        "sku": producto["sku"],
                        "cantidad": producto["cantidad"],
                        "origen": {
                            "origen": "OMN",
                            "subOrigen": "",
                            "seccion": "bot",
                            "recomendado": "",
                            "uen": "",
                            "ficha": False,
                            "cyber": 0
                        },
                        "estado": "NORMAL",
                        "ventaMinima": 1
                    })
                
                # Preparar el cuerpo de la solicitud
                body = {
                    "usuario": rut,
                    "rut": rut,
                    "sucursal": sucursal,
                    "tipoCarro": "OMN",
                    "ov": "",
                    "folioPropuesta": "",
                    "folio": "",
                    "vendedor": "jespinoza",
                    "productos": productos_formateados
                }
            
            # Configurar los headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            # Realizar la solicitud POST
            response = requests.post(api_url, headers=headers, json=body)
        
        else:
            error_message = f"Error: Acción '{accion}' no válida. Las acciones válidas son: listar, agregar, editar, eliminar"
            log_debug(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
        
        # Verificar si la solicitud fue exitosa
        if response.status_code == 200:
            # Convertir la respuesta a JSON
            result = response.json()
            
            # Verificar si hay datos en la respuesta
            if not result or result.get('error', True) or 'data' not in result:
                message = f"Operación '{accion}' ejecutada, pero no hay productos en el carro"
                log_debug(message)
                
                # Añadir mensaje explicativo basado en la acción
                mensaje = ""
                if accion == "listar":
                    mensaje = "Carro listado correctamente. No hay productos en el carro."
                elif accion == "agregar":
                    mensaje = "Productos agregados correctamente al carro."
                elif accion == "editar":
                    mensaje = "Carro editado correctamente."
                elif accion == "eliminar":
                    mensaje = "Todos los productos han sido eliminados del carro. El carro está vacío."
                
                return json.dumps({"message": mensaje}, ensure_ascii=False, indent=2)
            
            order_data = result['data']
            
            # Verificar si hay productos en el carro
            if 'productos' not in order_data or not order_data['productos']:
                mensaje = f"Operación '{accion}' ejecutada, pero no hay productos en el carro"
                return json.dumps({"message": mensaje}, ensure_ascii=False, indent=2)
                
            # Prepare simplified product list
            simplified_products = []
            for product in order_data['productos']:
                simplified_product = {
                    'sku': product.get('sku', ''),
                    'nombre': product.get('nombre', ''),
                    'cantidad': product.get('cantidad', 0),
                    'precio': product.get('precio', 0)
                }
                simplified_products.append(simplified_product)
            
            # Create summary object with just totalCarro and productos
            summary = {
                'totalCarro': sum(product.get('precio', 0) * product.get('cantidad', 0) for product in order_data['productos']),
                'productos': simplified_products
            }
                   
            # Añadir mensaje explicativo basado en la acción
            mensaje = ""
            if accion == "listar":
                mensaje = "Carro listado correctamente. Estos son los productos en el carro."
            elif accion == "agregar":
                mensaje = "Productos agregados correctamente al carro."
            elif accion == "editar":
                mensaje = "Carro editado correctamente con los nuevos productos y cantidades."
            elif accion == "eliminar" and (productos is None or len(productos) == 0):
                mensaje = "Todos los productos han sido eliminados del carro."
            elif accion == "eliminar":
                mensaje = "Los productos especificados han sido eliminados del carro."
            
            log_debug(f"Operación '{accion}' de carro ejecutada correctamente para cliente con RUT {rut}")
            return json.dumps({"message": mensaje, "data": summary}, ensure_ascii=False, indent=2)
        else:
            error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
            log_debug(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def convertir_para_json(self, obj):
        if isinstance(obj, datetime) or isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, ObjectId):
            return str(obj)
        return obj


    def procesar_documento(self, documento):
        if documento is None:
            return None
        
        if isinstance(documento, dict):
            resultado = {}
            for key, value in documento.items():
                if isinstance(value, dict):
                    resultado[key] = self.procesar_documento(value)
                elif isinstance(value, list):
                    resultado[key] = [self.procesar_documento(item) for item in value]
                else:
                    resultado[key] = self.convertir_para_json(value)
            return resultado
        elif isinstance(documento, list):
            return [self.procesar_documento(item) for item in documento]
        else:
            return self.convertir_para_json(documento)
    
    def generar_retiro_tienda(self, rut: str, sucursal: str, productos: List[dict]) -> str:
        """
        Asigna metodo de despacho con retiro en tienda elegido por el cliente antes de pago
        
        Args:
            rut (str): rut cliente.
            sucursal (str): codigo de sucursal de tienda valido
            productos (List[dict]): lista de productos del carro abierto del cliente
                            donde cada producto es un diccionario con las claves 'sku' (str) y 'cantidad' (int).
                            Ejemplo: [{'sku': '123456', 'cantidad': 2}, {'sku': '789012', 'cantidad': 1}]

        Returns:
            str: Resultado del proceso confirmado en formato JSON.
        """
        try:
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            
            # Paso 1: Llamada a la API de retiro en tienda
            base_url = f"https://b2b-api.implementos.cl/api/promesa-entrega/retiroTienda/{sucursal}"
            
            # Preparar el cuerpo de la solicitud para retiro en tienda
            body_retiro = {
                "omni": True,
                "bodegaDesdeCodigo": "",
                "byPassStock": "0",
                "multiProveedor": False,
                "productos": productos,
                "proveedorCodigo": "",
                "rut": rut,
                "stockSeguridad": False,
                "usarStockAX": True
            }
            
            # Configurar los headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            # Realizar la solicitud POST para retiro en tienda
            response_retiro = requests.post(base_url, headers=headers, json=body_retiro)
            
            # Verificar si la solicitud fue exitosa
            if response_retiro.status_code != 200:
                resultado_error = {
                    "mensaje": f"Error en la solicitud de retiro en tienda: {response_retiro.status_code} - {response_retiro.text}"
                }
                log_debug(f"Error en solicitud de retiro en tienda para RUT {rut}: {response_retiro.status_code}")
                return json.dumps(resultado_error, ensure_ascii=False, indent=2)
            
            # Obtener y procesar la respuesta de la API de retiro
            try:
                respuesta_retiro = response_retiro.json()
                log_debug(f"Respuesta de retiro en tienda recibida para RUT {rut}")
                
                # Procesar la respuesta según el formato necesario
                datos_procesados = {}
                
                # Obtener información de la tienda
                dataTienda = db.tiendas
                camposTienda = {
                    "recid": 1,
                    "_id": 0  # Excluir el campo _id
                }
                resultadoTienda = dataTienda.find_one(
                    {
                        "codigo": sucursal
                    },
                    projection=camposTienda
                )
                
                if not resultadoTienda or "recid" not in resultadoTienda:
                    error_message = f"No se encontró información de la tienda con código {sucursal}"
                    log_debug(error_message)
                    return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
                    
                # Convertir recidTienda a valor numérico (long)
                recidTienda = int(resultadoTienda["recid"]) if isinstance(resultadoTienda["recid"], str) else resultadoTienda["recid"]
                log_debug(f"recidTienda: {recidTienda}, tipo: {type(recidTienda)}")
                
                # CORRECCIÓN: La estructura de la respuesta es diferente
                # La respuesta tiene formato: {"status": "success", "data": {...}}
                if isinstance(respuesta_retiro, dict) and "status" in respuesta_retiro and respuesta_retiro["status"] == "success":
                    # Acceder a los datos anidados
                    if "data" in respuesta_retiro and isinstance(respuesta_retiro["data"], dict):
                        data_interna = respuesta_retiro["data"]
                        
                        # Verificar si hay datos de opciones de envío
                        if "data" in data_interna and isinstance(data_interna["data"], list):
                            respuesta_data = data_interna["data"]
                            datos_procesados["hayEntrega"] = len(respuesta_data) > 0
                            
                            # Obtener otros campos si existen
                            datos_procesados["productosSurtidos"] = data_interna.get("productosSurtidos", [])
                            datos_procesados["productosSinCumplir"] = data_interna.get("productosSinCumplir", [])
                            
                            # Convertimos productos a formato requerido para productosDespachar con "producto" en lugar de "codigo"
                            productos_despachar = []
                            for prod in productos:
                                productos_despachar.append({
                                    "producto": prod["sku"],  # Cambio de "codigo" a "producto"
                                    "cantidad": prod["cantidad"]
                                })
                            
                            # Crear nuevos grupos de despacho con la estructura correcta según el ejemplo que funciona
                            grupos = []
                            if datos_procesados["hayEntrega"]:
                                # Usar solo la primera opción de envío disponible
                                opcion_envio = respuesta_data[0]
                                
                                # Crear un objeto de fletes con todas las opciones de envío
                                fletes = []
                                for op_envio in respuesta_data:
                                    flete = {
                                        "fecha": op_envio.get("fecha", [""])[0] if isinstance(op_envio.get("fecha"), list) and op_envio.get("fecha") else "",
                                        "fechaDia": self._obtener_dia_semana(op_envio.get("fecha", [""])[0]) if isinstance(op_envio.get("fecha"), list) and op_envio.get("fecha") else "",
                                        "fechaPicking": op_envio.get("fechaPicking", ""),
                                        "fechaPickingDia": self._obtener_dia_semana(op_envio.get("fechaPicking", "")),
                                        "valor": op_envio.get("precio", 0),
                                        "identificador": op_envio.get("identificador", ""),
                                        "tipoEnvioVenta": {
                                            "codigo": op_envio.get("tipoEnvioVenta", {}).get("codigo", 0),
                                            "descripcion": op_envio.get("tipoEnvioVenta", {}).get("descripcion", "")
                                        },
                                        "opcionServicio": {
                                            "preciofinal": "0",
                                            "diashabilesnecesarios": op_envio.get("diasdemora", 0),
                                            "tser_nomb": "RETIRO EN ORIGEN",
                                            "tser_codi": op_envio.get("tipoenvio", ""),
                                            "bode_codi": op_envio.get("origen", ""),
                                            "identificador": op_envio.get("identificador", "")
                                        },
                                        "proveedor": {
                                            "codigo": op_envio.get("proveedor", ""),
                                            "nombre": op_envio.get("nombreProveedor", "")
                                        }
                                    }
                                    fletes.append(flete)
                                
                                # Crear la estructura del grupo según el ejemplo que funciona
                                grupo = {
                                    "productos": productos_despachar,
                                    "despacho": {
                                        "tipo": opcion_envio.get("tipoenvio", ""),
                                        "codTipo": "VEN- RPTDA",  # Tipo fijo para retiro en tienda
                                        "origen": opcion_envio.get("origen", ""),
                                        "recidDireccion": recidTienda,
                                        "codProveedor": opcion_envio.get("proveedor", ""),
                                        "nombreProveedor": opcion_envio.get("nombreProveedor", ""),
                                        "precio": opcion_envio.get("precio", 0),
                                        "descuento": 0,
                                        "observacion": "bot",
                                        "diasNecesarios": opcion_envio.get("diasdemora", 0),
                                        "identificador": opcion_envio.get("identificador", ""),
                                        "codTipoEnvioVenta": opcion_envio.get("tipoEnvioVenta", {}).get("codigo", 0),
                                        "tipoEnvioVenta": opcion_envio.get("tipoEnvioVenta", {}).get("descripcion", ""),
                                        "fechaPicking": opcion_envio.get("fechaPicking", ""),
                                        "fechaEntrega": opcion_envio.get("fecha", [""])[0] if isinstance(opcion_envio.get("fecha"), list) and opcion_envio.get("fecha") else "",
                                        "fechaDespacho": opcion_envio.get("fecha", [""])[0] if isinstance(opcion_envio.get("fecha"), list) and opcion_envio.get("fecha") else ""
                                    }
                                }
                                print(grupo)
                                grupos.append(grupo)
                            else:
                                # Si no hay lista de 'data' interna, inicializar grupos como vacío
                                grupos = []
                        else:
                            # Si no hay 'data' interna, inicializar grupos como vacío
                            grupos = []
                    else:
                        # Si no hay 'data' interna, inicializar grupos como vacío
                        grupos = []
                else:
                    # Si la respuesta no tiene el formato esperado, inicializar grupos como vacío
                    grupos = []
                    
                
                # Si no hay grupos de despacho, no es necesario realizar la segunda llamada
                if not grupos:
                    resultado_sin_grupos = {
                        "mensaje": "No hay despacho posible para retiro en tienda.",
                    }
                    log_debug(f"No hay grupos de despacho disponibles para RUT {rut}")
                    return json.dumps(resultado_sin_grupos, ensure_ascii=False, indent=2)
                
                usuario_vendedor = "jespinoza"
            
               
                dataCarro = db.carros
                resultadoCarro = dataCarro.update_one(
                    {
                        "usuario": rut,
                        "estado": "abierto",
                        "vendedor": usuario_vendedor
                    },
                    {"$set": {"grupos": grupos, "despacho": grupos[0]["despacho"]}}
                )
                # Verificar si la actualización fue exitosa
                if resultadoCarro.modified_count > 0 or resultadoCarro.matched_count > 0:
                    # Obtener el documento actualizado
                    carro_actualizado = dataCarro.find_one({
                        "usuario": rut,
                        "estado": "abierto",
                        "vendedor": usuario_vendedor
                    })
                    
                    # Procesar el documento para hacerlo serializable
                    carro_procesado = self.procesar_documento(carro_actualizado)
                    
                    return json.dumps("proceso realizado correctamente!!", ensure_ascii=False, indent=2)
                                    
            except json.JSONDecodeError as je:
                error_message = f"Error al decodificar la respuesta JSON: {je}"
                log_debug(error_message)
                resultado_error_json = {
                    "exito": False,
                    "mensaje": f"Error al procesar la respuesta de la API: {error_message}",
                    "datos_retiro": response_retiro.text if hasattr(response_retiro, 'text') else None,
                    "datos_despacho": None
                }
                return json.dumps(resultado_error_json, ensure_ascii=False, indent=2)
        
        except Exception as e:
            error_message = f"Error al procesar retiro en tienda para RUT {rut}: {e}"
            logger.warning(error_message)
            resultado_excepcion = {
                "exito": False,
                "mensaje": f"Error interno: {str(e)}",
                "datos_retiro": None,
                "datos_despacho": None
            }
            return json.dumps(resultado_excepcion, ensure_ascii=False, indent=2)

    def _obtener_dia_semana(self, fecha_str):
        """Obtiene el nombre del día de la semana a partir de una fecha en formato ISO."""
        if not fecha_str:
            return ""
        try:
            from datetime import datetime
            fecha = datetime.fromisoformat(fecha_str.replace('Z', '+00:00'))
            dias = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
            return dias[fecha.weekday()]
        except Exception:
            return ""
    def generar_despacho_domicilio(self, rut: str, recid: str, localidad: str, productos: List[dict]) -> str:
        """
        Asigna metodo de despacho con entrega en direccion del cliente elegida por el cliente antes de pago
        
        Args:
            rut (str): rut cliente.
            recid (str): id de la direccion registrada por el cliente
            localidad (str): nombre de la localidad (ciudad, comuna, localidad) de la direccion del cliente
            productos (List[dict]): lista de productos del carro abierto del cliente
                            donde cada producto es un diccionario con las claves 'sku' (str) y 'cantidad' (int).
                            Ejemplo: [{'sku': '123456', 'cantidad': 2}, {'sku': '789012', 'cantidad': 1}]

        Returns:
            str: Resultado del proceso confirmado en formato JSON.
        """
        try:
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            
            # Paso 1: Llamada a la API de despacho a domicilio
            base_url = f"https://b2b-api.implementos.cl/api/promesa-entrega/domicilio/{localidad}"
            
            # Preparar el cuerpo de la solicitud para despacho a domicilio
            body_retiro = {
                "omni": True,
                "bodegaDesdeCodigo": "",
                "byPassStock": "0",
                "multiProveedor": False,
                "productos": productos,
                "proveedorCodigo": "",
                "rut": rut,
                "stockSeguridad": False,
                "usarStockAX": True
            }
            
            # Configurar los headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            # Realizar la solicitud POST para despacho a domicilio
            response_retiro = requests.post(base_url, headers=headers, json=body_retiro)
            
            # Verificar si la solicitud fue exitosa
            if response_retiro.status_code != 200:
                resultado_error = {
                    "mensaje": f"Error en la solicitud de despacho a domicilio: {response_retiro.status_code} - {response_retiro.text}"
                }
                log_debug(f"Error en solicitud de despacho a domicilio para RUT {rut}: {response_retiro.status_code}")
                return json.dumps(resultado_error, ensure_ascii=False, indent=2)
            
            # Obtener y procesar la respuesta de la API de despacho
            try:
                respuesta_retiro = response_retiro.json()
                log_debug(f"Respuesta de despacho a domicilio recibida para RUT {rut}")
                
                # Procesar la respuesta según el formato necesario
                datos_procesados = {}
                
                # Convertir recid a valor numérico (long)
                recid_numerico = int(recid) if isinstance(recid, str) else recid
                log_debug(f"recid_numerico: {recid_numerico}, tipo: {type(recid_numerico)}")
                
                # CORRECCIÓN: La estructura de la respuesta es diferente
                # La respuesta tiene formato: {"status": "success", "data": {...}}
                if isinstance(respuesta_retiro, dict) and "status" in respuesta_retiro and respuesta_retiro["status"] == "success":
                    # Acceder a los datos anidados
                    if "data" in respuesta_retiro and isinstance(respuesta_retiro["data"], dict):
                        data_interna = respuesta_retiro["data"]
                        
                        # Verificar si hay datos de opciones de envío
                        if "data" in data_interna and isinstance(data_interna["data"], list):
                            respuesta_data = data_interna["data"]
                            datos_procesados["hayEntrega"] = len(respuesta_data) > 0
                            
                            # Obtener otros campos si existen
                            datos_procesados["productosSurtidos"] = data_interna.get("productosSurtidos", [])
                            datos_procesados["productosSinCumplir"] = data_interna.get("productosSinCumplir", [])
                            
                            # Convertimos productos a formato requerido para productosDespachar con "producto" en lugar de "codigo"
                            productos_despachar = []
                            for prod in productos:
                                productos_despachar.append({
                                    "producto": prod["sku"],  # Cambio de "codigo" a "producto"
                                    "cantidad": prod["cantidad"]
                                })
                            
                            # Crear nuevos grupos de despacho con la estructura correcta según el ejemplo que funciona
                            grupos = []
                            if datos_procesados["hayEntrega"]:
                                # Usar solo la primera opción de envío disponible
                                opcion_envio = respuesta_data[0]
                                
                                # Crear un objeto de fletes con todas las opciones de envío
                                fletes = []
                                for op_envio in respuesta_data:
                                    flete = {
                                        "fecha": op_envio.get("fecha", [""])[0] if isinstance(op_envio.get("fecha"), list) and op_envio.get("fecha") else "",
                                        "fechaDia": self._obtener_dia_semana(op_envio.get("fecha", [""])[0]) if isinstance(op_envio.get("fecha"), list) and op_envio.get("fecha") else "",
                                        "fechaPicking": op_envio.get("fechaPicking", ""),
                                        "fechaPickingDia": self._obtener_dia_semana(op_envio.get("fechaPicking", "")),
                                        "valor": op_envio.get("precio", 0),
                                        "identificador": op_envio.get("identificador", ""),
                                        "tipoEnvioVenta": {
                                            "codigo": op_envio.get("tipoEnvioVenta", {}).get("codigo", 0),
                                            "descripcion": op_envio.get("tipoEnvioVenta", {}).get("descripcion", "")
                                        },
                                        "opcionServicio": {
                                            "preciofinal": "0",
                                            "diashabilesnecesarios": op_envio.get("diasdemora", 0),
                                            "tser_nomb": "ENVIO A DOMICILIO",
                                            "tser_codi": op_envio.get("tipoenvio", ""),
                                            "bode_codi": op_envio.get("origen", "")
                                        },
                                        "proveedor": {
                                            "codigo": op_envio.get("proveedor", ""),
                                            "nombre": op_envio.get("nombreProveedor", "")
                                        }
                                    }
                                    fletes.append(flete)
                                
                                # Crear la estructura del grupo según el ejemplo que funciona
                                grupo = {
                                    "identificador": opcion_envio.get("identificador", ""),
                                    "bodega": opcion_envio.get("origen", ""),
                                    "pesoTotal": 1,  # Valor por defecto
                                    "tipoEnvioVenta": {
                                        "codigo": opcion_envio.get("tipoEnvioVenta", {}).get("codigo", 0),
                                        "descripcion": opcion_envio.get("tipoEnvioVenta", {}).get("descripcion", "")
                                    },
                                    "productosDespachar": productos_despachar,
                                    "envio": [
                                        {
                                            "identificador": opcion_envio.get("identificador", ""),
                                            "preciofinal": 0,
                                            "diashabilesnecesarios": 0,
                                            "bode_codi": opcion_envio.get("origen", ""),
                                            "tser_nomb": "ENVIO A DOMICILIO",
                                            "tser_codi": opcion_envio.get("tipoenvio", "")
                                        }
                                    ],
                                    "encontrado": True,
                                    "paraCalculo": {
                                        "valorPrimero": "0",
                                        "diasPrimero": 0,
                                        "valorUltimo": "0",
                                        "valoresEstandar": {
                                            "precio": "0",
                                            "dias": 0
                                        },
                                        "factorDesicion": 1
                                    },
                                    "fletes": fletes,
                                    "direccion": recid_numerico  # Añadir recid como parámetro de dirección
                                }
                                
                                grupos.append(grupo)
                        else:
                            # Si no hay lista de 'data' interna, inicializar grupos como vacío
                            grupos = []
                            datos_procesados["hayEntrega"] = False
                    else:
                        # Si no hay 'data' interna, inicializar grupos como vacío
                        grupos = []
                        datos_procesados["hayEntrega"] = False
                else:
                    # Si la respuesta no tiene el formato esperado, inicializar grupos como vacío
                    grupos = []
                    datos_procesados["hayEntrega"] = False
                    datos_procesados["productosSurtidos"] = []
                    datos_procesados["productosSinCumplir"] = []
                    
                datos_procesados["grupos"] = grupos
                
                # Si no hay grupos de despacho, no es necesario realizar la segunda llamada
                if not grupos:
                    resultado_sin_grupos = {
                        "mensaje": "No hay despacho posible para esta dirección.",
                    }
                    log_debug(f"No hay grupos de despacho disponibles para RUT {rut}")
                    return json.dumps(resultado_sin_grupos, ensure_ascii=False, indent=2)
                
                usuario_vendedor = "jespinoza"
            
                # Paso 2: Configurar los grupos de despacho
                url_despacho = "https://b2b-api.implementos.cl/api/carro/grupos/despacho"
                
                # Preparar el cuerpo de la solicitud para grupos de despacho con la estructura correcta
                body_despacho = {
                    "usuario": rut,
                    "grupos": grupos,
                    "sucursal": "SAN BRNRDO",  # Valor fijo para despacho a domicilio
                    "ov": "",
                    "folioPropuesta": "",
                    "vendedor": usuario_vendedor
                }
                
                # Debug - guardar lo que se está enviando
                log_debug(f"Enviando grupos de despacho: {json.dumps(body_despacho, ensure_ascii=False)}")
                
                # Realizar la solicitud POST para configurar grupos de despacho
                response_despacho = requests.post(url_despacho, headers=headers, json=body_despacho)
                
                # Verificar si la solicitud de despacho fue exitosa
                if response_despacho.status_code != 200:
                    resultado_error_despacho = {
                        "exito": False,
                        "mensaje": f"Despacho a domicilio configurado correctamente, pero hubo un error al configurar grupos de despacho: {response_despacho.status_code} - {response_despacho.text}",
                        "datos_retiro": respuesta_retiro,
                        "datos_despacho": None
                    }
                    log_debug(f"Error al configurar grupos de despacho para RUT {rut}: {response_despacho.status_code}")
                    return json.dumps(resultado_error_despacho, ensure_ascii=False, indent=2)
                
                # Obtener la respuesta de la API de despacho
                try:
                    # Capturar respuesta y texto original para depuración
                    respuesta_texto = response_despacho.text
                    log_debug(f"Respuesta texto del servidor: {respuesta_texto}")
                    
                    # Intentar parsear como JSON
                    respuesta_despacho = response_despacho.json()
                    log_debug(f"Despacho a domicilio configurado correctamente para RUT {rut}")
                    
                    # Siempre devolver como JSON formateado
                    return json.dumps("Despacho a domicilio configurado correctamente", ensure_ascii=False, indent=2)
                    
                except json.JSONDecodeError:
                    # Si no es un JSON válido, crear una respuesta de éxito basada en el código HTTP 200
                    log_debug(f"Respuesta no es JSON válido, pero el código HTTP es 200 (éxito)")
                    respuesta_manual = {
                        "exito": True,
                        "mensaje": "Despacho a domicilio configurado correctamente.",
                        "respuesta_original": respuesta_texto
                    }
                    return json.dumps(respuesta_manual, ensure_ascii=False, indent=2)
                
            except json.JSONDecodeError as je:
                error_message = f"Error al decodificar la respuesta JSON: {je}"
                log_debug(error_message)
                resultado_error_json = {
                    "exito": False,
                    "mensaje": f"Error al procesar la respuesta de la API: {error_message}",
                    "datos_retiro": response_retiro.text if hasattr(response_retiro, 'text') else None,
                    "datos_despacho": None
                }
                return json.dumps(resultado_error_json, ensure_ascii=False, indent=2)
        
        except Exception as e:
            error_message = f"Error al procesar despacho a domicilio para RUT {rut}: {e}"
            logger.warning(error_message)
            resultado_excepcion = {
                "exito": False,
                "mensaje": f"Error interno: {str(e)}",
                "datos_retiro": None,
                "datos_despacho": None
            }
            return json.dumps(resultado_excepcion, ensure_ascii=False, indent=2)

    def clientes_informacion(self, rut: str) -> str:
            """
            buscar un cliente por su RUT y direcciones util para despachos
            
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
                    "nombre": 1,
                    "direcciones":1,
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


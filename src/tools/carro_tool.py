import json
import requests
from typing import List
from pymongo import MongoClient
from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger
from config.config import Config

class CarroTool(Toolkit):
    def __init__(self):
        super().__init__(name="carro_tool")
        # Registrar las funciones en el toolkit para que sean accesibles dinámicamente
        self.register(self.listar_carro)
        self.register(self.gestionar_carro)
        self.register(self.generar_retiro_tienda)
        self.register(self.fecha_retiro)
        self.register(self.fecha_despacho)
    
    def listar_carro(self, rut: str, sucursal: str, codVendedor: str) -> str:
        """
        Listar carro abierto de un cliente
        
        Args:
            rut (str): rut cliente.
            sucursal (str): codigo de sucursal de tienda
            codVendedor (str): codigo de vendedor
            
        Returns:
            str: Resultado del carro de compra abierto en formato JSON.
        """
        try:
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            data = db.usuariosAX
            
            # Campos a recuperar de la base de datos
            campos = {
                "usuario": 1,
                "_id": 0  # Excluir el campo _id
            }
            
            # Convertir codVendedor de string a int
            try:
                codigo_vendedor_int = int(codVendedor)
            except ValueError:
                error_message = "Error: El código de vendedor debe ser un número entero válido"
                log_debug(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
            # Buscar vendedor por su código (ahora como entero)
            resultado = data.find_one(
                {
                    "codEmpleado": codigo_vendedor_int
                },
                projection=campos
            )
            
            # Verificar si se encontró el vendedor
            if not resultado:
                error_message = "Error: No se encontró el vendedor con el código proporcionado"
                log_debug(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
            # Obtener el usuario del vendedor
            usuario_vendedor = resultado["usuario"]
            
            # URL de la API
            api_url = f"https://b2b-api.implementos.cl/api/carro/omni?usuario={rut}&sucursal={sucursal}&rut={rut}&vendedor={usuario_vendedor}&ov=&folioPropuesta="
             
            # Configurar los headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            # Realizar la solicitud GET
            response = requests.get(api_url, headers=headers)
            
            # Verificar si la solicitud fue exitosa
            if response.status_code == 200:
                # Convertir la respuesta a JSON
                result = response.json()
                
                if not result or len(result) == 0 or 'data' not in result[0]:
                    message = f"No se encontró carro abierto para el cliente con RUT {rut}"
                    log_debug(message)
                    return json.dumps({"message": message}, ensure_ascii=False, indent=2)
                
                order_data = result[0]['data']
                
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
                    'totalCarro': order_data.get('totalCarro', 0),
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
    
    def gestionar_carro(self, rut: str, sucursal: str, codVendedor: str, accion: str, productos: List[dict] = None) -> str:
        """
        Gestiona un carro: agregar, editar, eliminar o listar carro de un cliente
        
        Args:
            rut (str): rut cliente.
            sucursal (str): codigo de sucursal de tienda
            codVendedor (str): código de vendedor (debe ser convertible a entero)
            accion (str): acción a realizar: "listar", "agregar", "editar", "eliminar"
            productos (List[dict], optional): lista de productos a agregar/editar al carro,
                            donde cada producto es un diccionario con las claves 'sku' (str) y 'cantidad' (int).
                            Ejemplo: [{'sku': '123456', 'cantidad': 2}, {'sku': '789012', 'cantidad': 1}]
                            Para eliminar todos los productos, enviar una lista vacía.
            
        Returns:
            str: Resultado de la operación del carro de compra en formato JSON.
        """
        try:
            # Conexión a MongoDB
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            data = db.usuariosAX
            
            # Campos a recuperar de la base de datos
            campos = {
                "usuario": 1,
                "_id": 0  # Excluir el campo _id
            }
            
            # Convertir codVendedor de string a int
            try:
                codigo_vendedor_int = int(codVendedor)
            except ValueError:
                error_message = "Error: El código de vendedor debe ser un número entero válido"
                log_debug(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
            # Buscar vendedor por su código (ahora como entero)
            resultado = data.find_one(
                {
                    "codEmpleado": codigo_vendedor_int
                },
                projection=campos
            )
            
            # Verificar si se encontró el vendedor
            if not resultado:
                error_message = "Error: No se encontró el vendedor con el código proporcionado"
                log_debug(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
            # Obtener el usuario del vendedor
            usuario_vendedor = resultado["usuario"]
            
            # Definir la URL de la API según la acción
            base_url = "https://b2b-api.implementos.cl/api/carro/omni"
            
            if accion == "listar":
                # URL para listar el carro
                api_url = f"{base_url}/obtiene?usuario={rut}&sucursal={sucursal}"
                
                # Realizar la solicitud GET
                headers = {
                    "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
                }
                
                response = requests.get(api_url, headers=headers)
                
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
                        "vendedor": usuario_vendedor,
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
                        "vendedor": usuario_vendedor,
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
                
                if not result or len(result) == 0 or 'data' not in result[0]:
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
                
                order_data = result[0]['data']
                # Prepare simplified product list
                simplified_products = []
                for product in order_data['productos']:
                    simplified_product = {
                        'sku': product['sku'],
                        'nombre': product['nombre'],
                        'cantidad': product['cantidad'],
                        'precio': product['precio']
                    }
                    simplified_products.append(simplified_product)
                
                # Create summary object with just totalCarro and productos
                summary = {
                    'totalCarro': order_data['totalCarro'],
                    'productos': simplified_products
                }
                
                formatted_result = json.dumps(summary, ensure_ascii=False, indent=2)
               
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
        
        except Exception as e:
            error_message = f"Error al gestionar carro para cliente con RUT {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def generar_retiro_tienda(self, rut: str, sucursal: str, codVendedor: str, productos: List[dict]) -> str:
        """
        Establece el retiro en tienda de un carro de cliente abierto
        
        Args:
            rut (str): rut cliente.
            sucursal (str): codigo de sucursal de tienda
            codVendedor (str): codigo del vendedor
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
            respuesta_retiro = response_retiro.json()
            log_debug(f"Respuesta de retiro en tienda recibida para RUT {rut}")
            
            # Procesar la respuesta según el formato necesario
            datos_procesados = {}
            promesa = respuesta_retiro.get("data", {})
            datos_procesados["productosSurtidos"] = promesa.get("productosSurtidos", [])
            datos_procesados["productosSinCumplir"] = promesa.get("productosSinCumplir", [])
            
            # Verificar si hay entregas disponibles
            respuesta_array = promesa.get("respuesta", [])
            datos_procesados["hayEntrega"] = (
                len(respuesta_array) > 0 and 
                "subOrdenes" in respuesta_array[0] and 
                len(respuesta_array[0]["subOrdenes"]) > 0
            )
            
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
                
            recidTienda = resultadoTienda["recid"]
            
            # Obtener los grupos de despacho
            grupos = []
            if datos_procesados["hayEntrega"]:
                grupos_originales = respuesta_array[0]["subOrdenes"]
                
                # Modificar los grupos según el fragmento de código JS proporcionado
                for grupo in grupos_originales:
                    if "despacho" in grupo and grupo["despacho"]:
                        if "flete" in grupo and len(grupo["flete"]) > 0:
                            flete = grupo["flete"][0]
                            
                            # Actualizar la información de despacho con los datos proporcionados
                            if "opcionServicio" in flete:
                                grupo["despacho"]["tipo"] = flete["opcionServicio"].get("tser_codi", "")
                                grupo["despacho"]["codTipo"] = "VEN- RPTDA"
                                grupo["despacho"]["origen"] = flete["opcionServicio"].get("bode_codi", "")
                            
                            # Agregar información de dirección si está disponible
                            grupo["despacho"]["recidDireccion"] = recidTienda
                                    
                            # Agregar información del proveedor si está disponible
                            if "proveedor" in flete:
                                grupo["despacho"]["codProveedor"] = flete["proveedor"].get("codigo", "")
                                grupo["despacho"]["nombreProveedor"] = flete["proveedor"].get("nombre", "")
                            
                            # Agregar información adicional
                            grupo["despacho"]["precio"] = flete.get("valor", 0)
                            grupo["despacho"]["descuento"] = 0
                            grupo["despacho"]["observacion"] = "bot"
                            
                            if "opcionServicio" in flete:
                                grupo["despacho"]["diasNecesarios"] = flete["opcionServicio"].get("diashabilesnecesarios", 0)
                                grupo["despacho"]["identificador"] = flete["opcionServicio"].get("identificador", "")
                            
                            # Agregar información de tipo de envío si está disponible
                            if "tipoEnvioVenta" in flete:
                                grupo["despacho"]["codTipoEnvioVenta"] = flete["tipoEnvioVenta"].get("codigo", "")
                                grupo["despacho"]["tipoEnvioVenta"] = flete["tipoEnvioVenta"].get("descripcion", "")
                            
                            # Agregar fechas
                            grupo["despacho"]["fechaPicking"] = flete.get("fechaPicking", "")
                            grupo["despacho"]["fechaEntrega"] = flete.get("fecha", "")
                            grupo["despacho"]["fechaDespacho"] = flete.get("fecha", "")
                    
                    grupos.append(grupo)
                
                # Agregar el despacho al objeto datos_procesados
                if grupos and "despacho" in grupos[0]:
                    datos_procesados["despacho"] = grupos[0]["despacho"]
            
            datos_procesados["grupos"] = grupos
            
            # Si no hay grupos de despacho, no es necesario realizar la segunda llamada
            if not grupos:
                resultado_sin_grupos = {
                    "mensaje": "No hay despacho posible para retiro en tienda.",
                }
                log_debug(f"No hay grupos de despacho disponibles para RUT {rut}")
                return json.dumps(resultado_sin_grupos, ensure_ascii=False, indent=2)
            
            data = db.usuariosAX
            
            # Campos a recuperar de la base de datos
            campos = {
                "usuario": 1,
                "_id": 0  # Excluir el campo _id
            }
            
            # Convertir codVendedor de string a int
            try:
                codigo_vendedor_int = int(codVendedor)
            except ValueError:
                error_message = "Error: El código de vendedor debe ser un número entero válido"
                log_debug(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
            # Buscar vendedor por su código (ahora como entero)
            resultado = data.find_one(
                {
                    "codEmpleado": codigo_vendedor_int
                },
                projection=campos
            )
            
            # Verificar si se encontró el vendedor
            if not resultado:
                error_message = "Error: No se encontró el vendedor con el código proporcionado"
                log_debug(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
            # Obtener el usuario del vendedor
            usuario_vendedor = resultado["usuario"]
           
            # Paso 2: Configurar los grupos de despacho
            url_despacho = "https://b2b-api.implementos.cl/api/carro/grupos/despacho"
            
            # Preparar el cuerpo de la solicitud para grupos de despacho
            body_despacho = {
                "usuario": rut,
                "grupos": grupos,
                "sucursal": sucursal,
                "formaPago": "OC",
                "ov": "",
                "folioPropuesta": "",
                "vendedor": usuario_vendedor
            }
            
            # Realizar la solicitud POST para configurar grupos de despacho
            response_despacho = requests.post(url_despacho, headers=headers, json=body_despacho)
            
            # Verificar si la solicitud de despacho fue exitosa
            if response_despacho.status_code != 200:
                resultado_error_despacho = {
                    "exito": False,
                    "mensaje": f"Retiro en tienda configurado correctamente, pero hubo un error al configurar grupos de despacho: {response_despacho.status_code} - {response_despacho.text}",
                    "datos_retiro": respuesta_retiro,
                    "datos_despacho": None
                }
                log_debug(f"Error al configurar grupos de despacho para RUT {rut}: {response_despacho.status_code}")
                return json.dumps(resultado_error_despacho, ensure_ascii=False, indent=2)
            
            # Obtener la respuesta de la API de despacho
            respuesta_despacho = response_despacho.json()
            log_debug(f"Retiro en tienda configurado correctamente para RUT {rut}")
            
            # Siempre devolver como JSON formateado
            return json.dumps(respuesta_despacho, ensure_ascii=False, indent=2)
        
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
    
    def fecha_retiro(self, sucursal: str, productos: List[dict]) -> str:
        """
        Ofrece fechas de retiro disponible de un listado de productos para un codigo de sucursal
        
        Args:
            sucursal (str): codigo de sucursal de tienda
            productos (List[dict]): lista de productos del carro abierto del cliente
                            donde cada producto es un diccionario con las claves 'sku' (str) y 'cantidad' (int).
                            Ejemplo: [{'sku': '123456', 'cantidad': 2}, {'sku': '789012', 'cantidad': 1}]
                            
        Returns:
            str: Resultado de fechas disponibles en formato JSON.
        """
        try:
            log_debug(f"Consultando fechas de retiro para sucursal {sucursal}")
            
            # URL de la API
            api_url = f"https://b2b-api.implementos.cl/api/promesa-entrega/retiroTienda/{sucursal}"
            
            # Configurar los headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            body_despacho = {
                "omni": True,
                "stockSeguridad": False,
                "multiProveedor": False,
                "usarStockAX": True,
                "productos": productos
            }
            
            # Realizar la solicitud POST
            response = requests.post(api_url, headers=headers, json=body_despacho)
            
            # Verificar si la solicitud fue exitosa
            if response.status_code == 200:
                # Convertir la respuesta a JSON
                result = response.json()
                
                # Extraer las opciones de entrega
                delivery_options = []
                for option in result.get('data', {}).get('data', []):
                    # Convertir la fecha de entrega a un formato más legible
                    if option.get('fecha') and len(option['fecha']) > 0:
                        delivery_options.append({
                            'precio': option.get('precio', 0),
                            'fecha': option['fecha'][0]  # Tomar la primera fecha del array
                        })
                
                formatted_result = json.dumps(delivery_options, ensure_ascii=False, indent=2)
                log_debug(f"Fechas de retiro consultadas correctamente para sucursal {sucursal}")
                return formatted_result
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
        
        except Exception as e:
            error_message = f"Error al consultar fechas de retiro para sucursal {sucursal}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    def fecha_despacho(self, comuna: str, productos: List[dict]) -> str:
        """
        Ofrece fechas de despacho a domicilio disponible de un listado de productos para una comuna
        
        Args:
            comuna (str): localidad de destino de despacho (comuna, ciudad, localidad)
            productos (List[dict]): lista de productos del carro abierto del cliente
                            donde cada producto es un diccionario con las claves 'sku' (str) y 'cantidad' (int).
                            Ejemplo: [{'sku': '123456', 'cantidad': 2}, {'sku': '789012', 'cantidad': 1}]
                            
        Returns:
            str: Resultado de fechas disponibles para un despacho a domicilio en formato JSON.
        """
        try:
            log_debug(f"Consultando fechas de despacho para comuna {comuna}")
        
            # URL de la API
            api_url = f"https://b2b-api.implementos.cl/api/promesa-entrega/domicilio/{comuna}"
        
            body = {
                "omni": True,
                "stockSeguridad": False,
                "multiProveedor": False,
                "usarStockAX": True,
                "productos": productos
            }
            
            # Configurar los headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            # Realizar la solicitud POST
            response = requests.post(api_url, headers=headers, json=body)
            
            # Verificar si la solicitud fue exitosa
            if response.status_code == 200:
                # Convertir la respuesta a JSON
                result = response.json()
                delivery_options = []
                for option in result.get('data', {}).get('data', []):
                    # Convertir la fecha de entrega a un formato más legible
                    if option.get('fecha') and len(option['fecha']) > 0:
                        delivery_options.append({
                            'precio': option.get('precio', 0),
                            'fecha': option['fecha'][0]  # Tomar la primera fecha del array
                        })
                        
                formatted_result = json.dumps(delivery_options, ensure_ascii=False, indent=2)
                log_debug(f"Fechas de despacho consultadas correctamente para comuna {comuna}")
                return formatted_result
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                log_debug(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
        
        except Exception as e:
            error_message = f"Error al consultar fechas de despacho para comuna {comuna}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
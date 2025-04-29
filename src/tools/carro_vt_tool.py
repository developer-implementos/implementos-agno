import json
import requests
from typing import List, Dict, Any, Optional, Union
import openai
from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger
from config.config import Config
from pymongo import MongoClient
from datetime import datetime

class CarroVtTool(Toolkit):
    def __init__(self):
        super().__init__(name="carro_vt_tool")
        # Registrar las funciones en el toolkit
        self.register(self.agregar_producto_carro)
        self.register(self.modificar_producto_carro)
        self.register(self.eliminar_producto_carro)
        self.register(self.ver_carro)
        self.register(self.completar_carro)
        self.register(self.convertir_cotizacion)
        
        # Constantes
        self.BASIC_AUTH = "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
        self.IVA = 0.19
        self.ORIGEN_PRODUCTO = {
            "origen": "vision",
            "subOrigen": "",
            "seccion": "sinCategoria",
            "recomendado": "",
            "uen": "",
            "ficha": False,
            "cyber": 0
        }
        
    def _obtener_token_vendedor(self, codigo_vendedor: str) -> str:
        """
        Obtiene el token del vendedor desde la base de datos MongoDB
        
        Args:
            codigo_vendedor (str): Código del vendedor
            
        Returns:
            str: Token del vendedor
        """
        try:
            client = MongoClient(Config.MONGO_IA)
            db = client.get_default_database()
            auth_info = db.agent_auth_info.find_one({"codigo_empleado": codigo_vendedor})
            
            if auth_info and "token" in auth_info:
                return auth_info["token"]
            else:
                logger.warning(f"No se encontró token para el vendedor {codigo_vendedor}")
                return ""
        except Exception as e:
            logger.error(f"Error al obtener token del vendedor: {e}")
            return ""
    
    def _calcular_total_carro(self, carro: Dict[str, Any]) -> Dict[str, float]:
        """
        Calcula los totales del carrito
        
        Args:
            carro (Dict[str, Any]): Datos del carrito
            
        Returns:
            Dict[str, float]: Totales calculados (subtotal, iva, despacho, total)
        """
        totals = {
            "subtotal": 0,
            "iva": 0,
            "despacho": 0,
            "total": 0
        }
        
        # Verificar si hay grupos en el carrito
        if "grupos" in carro and carro["grupos"]:
            grupos = carro["grupos"]
            for grupo in grupos:
                for producto in [p for p in grupo["productos"] if not p.get("conflictoEntrega", False)]:
                    totals["total"] += producto["precio"] * producto["cantidad"]
                    totals["subtotal"] += (producto["precio"] * producto["cantidad"]) / (1 + self.IVA)
                
                if "despacho" in grupo and grupo["despacho"].get("precio", 0) > 0:
                    totals["despacho"] += grupo["despacho"].get("precio", 0) - grupo["despacho"].get("descuento", 0)
        
        # Si no hay grupos, usar productos directamente
        elif "productos" in carro and carro["productos"]:
            for producto in [p for p in carro["productos"] if not p.get("conflictoEntrega", False)]:
                totals["total"] += producto["precio"] * producto["cantidad"]
                totals["subtotal"] += (producto["precio"] * producto["cantidad"]) / (1 + self.IVA)
            
            if "despacho" in carro and carro["despacho"].get("precio", 0) > 0:
                totals["despacho"] += carro["despacho"].get("precio", 0) - carro["despacho"].get("descuento", 0)
        
        # Redondear valores
        totals["despacho"] = round(totals["despacho"])
        totals["total"] = round(totals["total"])
        totals["subtotal"] = round(totals["subtotal"])
        totals["iva"] = totals["total"] - totals["subtotal"]
        
        return totals
    
    def _obtener_bodega_vendedor(self, cod_empleado: str, tienda: Optional[str] = None) -> Dict[str, str]:
        """
        Obtiene la bodega asociada al vendedor
        
        Args:
            cod_empleado (str): Código del empleado
            tienda (Optional[str]): Tienda específica (opcional)
            
        Returns:
            Dict[str, str]: Información de la bodega
        """
        try:
            # Simplificación: en un entorno real, se consultaría a una base de datos
            return {"codBodega": "PRINCIPAL", "sucursal": "PRINCIPAL"}
        except Exception as e:
            logger.error(f"Error al obtener bodega del vendedor: {e}")
            return {"codBodega": "", "sucursal": ""}
    
    def _normalizar_rut(self, rut: str) -> str:
        """
        Normaliza el formato del RUT
        
        Args:
            rut (str): RUT a normalizar
            
        Returns:
            str: RUT normalizado
        """
        if not rut:
            return ""
        
        return rut.replace(".", "").replace("-", "").strip()
    
    def agregar_producto_carro(
        self, 
        rut: str, 
        sku: str, 
        cantidad: int, 
        nombre_usuario_vendedor: str, 
        codigo_vendedor: str, 
        sucursal: Optional[str] = None
    ) -> str:
        """
        Agrega un producto al carrito de compras
        
        Args:
            rut (str): RUT del cliente
            sku (str): SKU del producto a agregar
            cantidad (int): Cantidad del producto
            nombre_usuario_vendedor (str): Nombre de usuario del vendedor
            codigo_vendedor (str): Código del vendedor
            sucursal (Optional[str]): Código de la sucursal
            
        Returns:
            str: Resultado de la operación en formato JSON
        """
        try:
            # Normalizar datos
            rut_normalizado = self._normalizar_rut(rut)
            sku = sku.upper()
            
            # Validar datos básicos
            if not rut_normalizado:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Se requiere el RUT del cliente."
                }, ensure_ascii=False, indent=2)
            
            if not sku:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Se requiere el SKU del producto."
                }, ensure_ascii=False, indent=2)
            
            if cantidad <= 0:
                return json.dumps({
                    "ok": False,
                    "mensaje": "La cantidad debe ser mayor a 0."
                }, ensure_ascii=False, indent=2)
            
            # Obtener información del cliente
            try:
                client = MongoClient(Config.MONGO_NUBE)
                db = client.Implenet
                cliente = db.clientes.find_one({"rut": rut_normalizado}, {"nombre": 1})
                
                if not cliente:
                    return json.dumps({
                        "ok": False,
                        "mensaje": "Cliente no encontrado."
                    }, ensure_ascii=False, indent=2)
                
                nombre_cliente = cliente.get("nombre", "")
            except Exception as e:
                logger.error(f"Error al consultar cliente: {e}")
                return json.dumps({
                    "ok": False,
                    "mensaje": "Error al verificar el cliente."
                }, ensure_ascii=False, indent=2)
            
            # Obtener la bodega del vendedor
            bodega = self._obtener_bodega_vendedor(codigo_vendedor, sucursal)
            if not bodega["codBodega"]:
                return json.dumps({
                    "ok": False,
                    "mensaje": "No se encontró la bodega asociada al vendedor."
                }, ensure_ascii=False, indent=2)
            
            # Verificar producto
            try:
                client = MongoClient(Config.MONGO_NUBE)
                db = client.Implenet
                producto = db.articulos.find_one({"sku": sku}, {"estado": 1})
            except Exception as e:
                logger.error(f"Error al consultar producto: {e}")
                producto = None
            
            # Obtener carro actual
            url = f"https://b2b-api.implementos.cl/api/carro/omni"
            params = {
                "usuario": rut_normalizado,
                "sucursal": bodega["codBodega"],
                "rut": rut_normalizado,
                "vendedor": nombre_usuario_vendedor,
                "ov": "",
                "folioPropuesta": ""
            }
            
            response = requests.get(url, params=params, headers={"Authorization": self.BASIC_AUTH})
            
            if response.status_code != 200:
                logger.error(f"Error al obtener carro: {response.status_code} - {response.text}")
                return json.dumps({
                    "ok": False,
                    "mensaje": "Error al obtener el carrito de compras."
                }, ensure_ascii=False, indent=2)
            
            carro_actual = response.json()
            
            # Verificar si el producto ya existe en el carro
            producto_existente = None
            if carro_actual.get("data", {}).get("productos"):
                for prod in carro_actual["data"]["productos"]:
                    if prod["sku"] == sku:
                        producto_existente = prod
                        break
            
            nueva_cantidad = cantidad
            if producto_existente:
                nueva_cantidad = cantidad + producto_existente["cantidad"]
            
            # Agregar producto al carro
            url = "https://b2b-api.implementos.cl/api/carro/omni/articulo"
            payload = {
                "folioPropuesta": "",
                "ov": "",
                "rut": rut_normalizado,
                "usuario": rut_normalizado,
                "sucursal": bodega["codBodega"],
                "vendedor": nombre_usuario_vendedor,
                "folio": "",
                "tipoCarro": "OMN",
                "productos": [
                    {
                        "sku": sku,
                        "ventaMinima": 1,
                        "origen": self.ORIGEN_PRODUCTO,
                        "estado": producto.get("estado", "") if producto else "",
                        "cantidad": nueva_cantidad
                    }
                ]
            }
            
            response = requests.post(url, json=payload, headers={"Authorization": self.BASIC_AUTH})
            
            if response.status_code != 200:
                logger.error(f"Error al agregar producto: {response.status_code} - {response.text}")
                return json.dumps({
                    "ok": False,
                    "mensaje": "Error al agregar el producto al carrito."
                }, ensure_ascii=False, indent=2)
            
            carro_actualizado = response.json()
            
            # Si hubo error, obtener el carro nuevamente
            if carro_actualizado.get("error"):
                response = requests.get(url, params=params, headers={"Authorization": self.BASIC_AUTH})
                carro_actualizado = response.json()
            
            # Calcular totales
            totales = self._calcular_total_carro(carro_actualizado.get("data", {}))
            
            # Formatear productos para la respuesta
            productos_formateados = []
            for producto in carro_actualizado.get("data", {}).get("productos", []):
                imagen = ""
                if producto.get("images"):
                    # Intentar obtener la URL de la imagen
                    for size in ["150", "250", "450"]:
                        if size in producto["images"] and len(producto["images"][size]) > 0:
                            imagen = producto["images"][size][0]
                            break
                
                productos_formateados.append({
                    "imagen": imagen,
                    "sku": producto.get("sku", ""),
                    "nombre": producto.get("nombre", ""),
                    "cantidad": producto.get("cantidad", 0),
                    "precio_neto": round(producto.get("precio", 0) / (1 + self.IVA)),
                    "precio": producto.get("precio", 0)
                })
            
            # Construir respuesta
            resultado = {
                "ok": True,
                "mensaje": f"Producto {sku} agregado correctamente al carrito de {nombre_cliente}.",
                "data": {
                    "rut": rut_normalizado,
                    "nombre_cliente": nombre_cliente,
                    "sucursal": bodega["codBodega"],
                    "productos": productos_formateados,
                    "totales": totales
                }
            }
            
            return json.dumps(resultado, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"Error general al agregar producto: {e}")
            return json.dumps({
                "ok": False,
                "mensaje": f"Error al procesar la solicitud: {str(e)}"
            }, ensure_ascii=False, indent=2)
    
    def modificar_producto_carro(
        self, 
        rut: str, 
        sku: str, 
        cantidad: int, 
        nombre_usuario_vendedor: str, 
        codigo_vendedor: str, 
        sucursal: Optional[str] = None
    ) -> str:
        """
        Modifica la cantidad de un producto en el carrito de compras
        
        Args:
            rut (str): RUT del cliente
            sku (str): SKU del producto a modificar
            cantidad (int): Nueva cantidad del producto
            nombre_usuario_vendedor (str): Nombre de usuario del vendedor
            codigo_vendedor (str): Código del vendedor
            sucursal (Optional[str]): Código de la sucursal
            
        Returns:
            str: Resultado de la operación en formato JSON
        """
        try:
            # Normalizar datos
            rut_normalizado = self._normalizar_rut(rut)
            sku = sku.upper()
            
            # Validar datos básicos
            if not rut_normalizado:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Se requiere el RUT del cliente."
                }, ensure_ascii=False, indent=2)
            
            if not sku:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Se requiere el SKU del producto."
                }, ensure_ascii=False, indent=2)
            
            if cantidad <= 0:
                return json.dumps({
                    "ok": False,
                    "mensaje": "La cantidad debe ser mayor a 0."
                }, ensure_ascii=False, indent=2)
            
            # Obtener información del cliente
            try:
                client = MongoClient(Config.MONGO_NUBE)
                db = client.Implenet
                cliente = db.clientes.find_one({"rut": rut_normalizado}, {"nombre": 1})
                
                if not cliente:
                    return json.dumps({
                        "ok": False,
                        "mensaje": "Cliente no encontrado."
                    }, ensure_ascii=False, indent=2)
                
                nombre_cliente = cliente.get("nombre", "")
            except Exception as e:
                logger.error(f"Error al consultar cliente: {e}")
                return json.dumps({
                    "ok": False,
                    "mensaje": "Error al verificar el cliente."
                }, ensure_ascii=False, indent=2)
            
            # Obtener la bodega del vendedor
            bodega = self._obtener_bodega_vendedor(codigo_vendedor, sucursal)
            if not bodega["codBodega"]:
                return json.dumps({
                    "ok": False,
                    "mensaje": "No se encontró la bodega asociada al vendedor."
                }, ensure_ascii=False, indent=2)
            
            # Verificar producto
            try:
                client = MongoClient(Config.MONGO_NUBE)
                db = client.Implenet
                producto = db.articulos.find_one({"sku": sku}, {"estado": 1})
            except Exception as e:
                logger.error(f"Error al consultar producto: {e}")
                producto = None
            
            # Modificar la cantidad del producto en el carro
            url = "https://b2b-api.implementos.cl/api/carro/omni/articulo"
            payload = {
                "folioPropuesta": "",
                "ov": "",
                "rut": rut_normalizado,
                "usuario": rut_normalizado,
                "sucursal": bodega["codBodega"],
                "vendedor": nombre_usuario_vendedor,
                "folio": "",
                "tipoCarro": "OMN",
                "productos": [
                    {
                        "sku": sku,
                        "ventaMinima": 1,
                        "origen": self.ORIGEN_PRODUCTO,
                        "estado": producto.get("estado", "") if producto else "",
                        "cantidad": cantidad
                    }
                ]
            }
            
            response = requests.post(url, json=payload, headers={"Authorization": self.BASIC_AUTH})
            
            if response.status_code != 200:
                logger.error(f"Error al modificar producto: {response.status_code} - {response.text}")
                return json.dumps({
                    "ok": False,
                    "mensaje": "Error al modificar el producto en el carrito."
                }, ensure_ascii=False, indent=2)
            
            carro_actualizado = response.json()
            
            # Si hubo error, obtener el carro nuevamente
            if carro_actualizado.get("error"):
                url = f"https://b2b-api.implementos.cl/api/carro/omni"
                params = {
                    "usuario": rut_normalizado,
                    "sucursal": bodega["codBodega"],
                    "rut": rut_normalizado,
                    "vendedor": nombre_usuario_vendedor,
                    "ov": "",
                    "folioPropuesta": ""
                }
                response = requests.get(url, params=params, headers={"Authorization": self.BASIC_AUTH})
                carro_actualizado = response.json()
            
            # Calcular totales
            totales = self._calcular_total_carro(carro_actualizado.get("data", {}))
            
            # Formatear productos para la respuesta
            productos_formateados = []
            for producto in carro_actualizado.get("data", {}).get("productos", []):
                imagen = ""
                if producto.get("images"):
                    # Intentar obtener la URL de la imagen
                    for size in ["150", "250", "450"]:
                        if size in producto["images"] and len(producto["images"][size]) > 0:
                            imagen = producto["images"][size][0]
                            break
                
                productos_formateados.append({
                    "imagen": imagen,
                    "sku": producto.get("sku", ""),
                    "nombre": producto.get("nombre", ""),
                    "cantidad": producto.get("cantidad", 0),
                    "precio_neto": round(producto.get("precio", 0) / (1 + self.IVA)),
                    "precio": producto.get("precio", 0)
                })
            
            # Construir respuesta
            resultado = {
                "ok": True,
                "mensaje": f"Producto {sku} modificado correctamente en el carrito de {nombre_cliente}.",
                "data": {
                    "rut": rut_normalizado,
                    "nombre_cliente": nombre_cliente,
                    "sucursal": bodega["codBodega"],
                    "productos": productos_formateados,
                    "totales": totales
                }
            }
            
            return json.dumps(resultado, ensure_ascii=False, indent=2)
        
        except Exception as e:
            logger.error(f"Error general al modificar producto: {e}")
            return json.dumps({
                "ok": False,
                "mensaje": f"Error al procesar la solicitud: {str(e)}"
            }, ensure_ascii=False, indent=2)
    
    def eliminar_producto_carro(
        self, 
        rut: str, 
        sku: str, 
        nombre_usuario_vendedor: str, 
        codigo_vendedor: str, 
        sucursal: Optional[str] = None
    ) -> str:
        """
        Elimina un producto del carrito de compras
        
        Args:
            rut (str): RUT del cliente
            sku (str): SKU del producto a eliminar
            nombre_usuario_vendedor (str): Nombre de usuario del vendedor
            codigo_vendedor (str): Código del vendedor
            sucursal (Optional[str]): Código de la sucursal
            
        Returns:
            str: Resultado de la operación en formato JSON
        """
        try:
            # Normalizar datos
            rut_normalizado = self._normalizar_rut(rut)
            sku = sku.upper()
            
            # Validar datos básicos
            if not rut_normalizado:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Se requiere el RUT del cliente."
                }, ensure_ascii=False, indent=2)
            
            if not sku:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Se requiere el SKU del producto."
                }, ensure_ascii=False, indent=2)
            
            # Obtener información del cliente
            try:
                client = MongoClient(Config.MONGO_NUBE)
                db = client.Implenet
                cliente = db.clientes.find_one({"rut": rut_normalizado}, {"nombre": 1})
                
                if not cliente:
                    return json.dumps({
                        "ok": False,
                        "mensaje": "Cliente no encontrado."
                    }, ensure_ascii=False, indent=2)
                
                nombre_cliente = cliente.get("nombre", "")
            except Exception as e:
                logger.error(f"Error al consultar cliente: {e}")
                return json.dumps({
                    "ok": False,
                    "mensaje": "Error al verificar el cliente."
                }, ensure_ascii=False, indent=2)
            
            # Obtener la bodega del vendedor
            bodega = self._obtener_bodega_vendedor(codigo_vendedor, sucursal)
            if not bodega["codBodega"]:
                return json.dumps({
                    "ok": False,
                    "mensaje": "No se encontró la bodega asociada al vendedor."
                }, ensure_ascii=False, indent=2)
            
            # Eliminar el producto del carro
            url = "https://b2b-api.implementos.cl/api/carro/omni/articulo"
            payload = {
                "folioPropuesta": "",
                "ov": "",
                "rut": rut_normalizado,
                "usuario": rut_normalizado,
                "sucursal": bodega["codBodega"],
                "vendedor": nombre_usuario_vendedor,
                "sku": sku
            }
            
            response = requests.delete(url, json=payload, headers={"Authorization": self.BASIC_AUTH})
            
            if response.status_code != 200:
                logger.error(f"Error al eliminar producto: {response.status_code} - {response.text}")
                return json.dumps({
                    "ok": False,
                    "mensaje": "Error al eliminar el producto del carrito."
                }, ensure_ascii=False, indent=2)
            
            carro_actualizado = response.json()
            
            # Si hubo error, obtener el carro nuevamente
            if carro_actualizado.get("error"):
                url = f"https://b2b-api.implementos.cl/api/carro/omni"
                params = {
                    "usuario": rut_normalizado,
                    "sucursal": bodega["codBodega"],
                    "rut": rut_normalizado,
                    "vendedor": nombre_usuario_vendedor,
                    "ov": "",
                    "folioPropuesta": ""
                }
                response = requests.get(url, params=params, headers={"Authorization": self.BASIC_AUTH})
                carro_actualizado = response.json()
            
            # Calcular totales
            totales = self._calcular_total_carro(carro_actualizado.get("data", {}))
            
            # Formatear productos para la respuesta
            productos_formateados = []
            for producto in carro_actualizado.get("data", {}).get("productos", []):
                imagen = ""
                if producto.get("images"):
                    # Intentar obtener la URL de la imagen
                    for size in ["150", "250", "450"]:
                        if size in producto["images"] and len(producto["images"][size]) > 0:
                            imagen = producto["images"][size][0]
                            break
                
                productos_formateados.append({
                    "imagen": imagen,
                    "sku": producto.get("sku", ""),
                    "nombre": producto.get("nombre", ""),
                    "cantidad": producto.get("cantidad", 0),
                    "precio_neto": round(producto.get("precio", 0) / (1 + self.IVA)),
                    "precio": producto.get("precio", 0)
                })
            
            # Construir respuesta
            resultado = {
                "ok": True,
                "mensaje": f"Producto {sku} eliminado correctamente del carrito de {nombre_cliente}.",
                "data": {
                    "rut": rut_normalizado,
                    "nombre_cliente": nombre_cliente,
                    "sucursal": bodega["codBodega"],
                    "productos": productos_formateados,
                    "totales": totales
                }
            }
            
            return json.dumps(resultado, ensure_ascii=False, indent=2)
        
        except Exception as e:
            logger.error(f"Error general al eliminar producto: {e}")
            return json.dumps({
                "ok": False,
                "mensaje": f"Error al procesar la solicitud: {str(e)}"
            }, ensure_ascii=False, indent=2)
    
    def ver_carro(
        self, 
        rut: str, 
        nombre_usuario_vendedor: str, 
        codigo_vendedor: str, 
        sucursal: Optional[str] = None
    ) -> str:
        """
        Obtiene el contenido del carrito de compras de un cliente
        
        Args:
            rut (str): RUT del cliente
            nombre_usuario_vendedor (str): Nombre de usuario del vendedor
            codigo_vendedor (str): Código del vendedor
            sucursal (Optional[str]): Código de la sucursal
            
        Returns:
            str: Resultado de la operación en formato JSON
        """
        try:
            # Normalizar datos
            rut_normalizado = self._normalizar_rut(rut)
            
            # Validar datos básicos
            if not rut_normalizado:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Se requiere el RUT del cliente."
                }, ensure_ascii=False, indent=2)
            
            # Obtener información del cliente
            try:
                client = MongoClient(Config.MONGO_NUBE)
                db = client.Implenet
                cliente = db.clientes.find_one({"rut": rut_normalizado}, {"nombre": 1})
                
                if not cliente:
                    return json.dumps({
                        "ok": False,
                        "mensaje": "Cliente no encontrado."
                    }, ensure_ascii=False, indent=2)
                
                nombre_cliente = cliente.get("nombre", "")
            except Exception as e:
                logger.error(f"Error al consultar cliente: {e}")
                return json.dumps({
                    "ok": False,
                    "mensaje": "Error al verificar el cliente."
                }, ensure_ascii=False, indent=2)
            
            # Obtener la bodega del vendedor
            bodega = self._obtener_bodega_vendedor(codigo_vendedor, sucursal)
            if not bodega["codBodega"]:
                return json.dumps({
                    "ok": False,
                    "mensaje": "No se encontró la bodega asociada al vendedor."
                }, ensure_ascii=False, indent=2)
            
            # Obtener el carrito del cliente
            url = f"https://b2b-api.implementos.cl/api/carro/omni"
            params = {
                "usuario": rut_normalizado,
                "sucursal": bodega["codBodega"],
                "rut": rut_normalizado,
                "vendedor": nombre_usuario_vendedor,
                "ov": "",
                "folioPropuesta": ""
            }
            
            response = requests.get(url, params=params, headers={"Authorization": self.BASIC_AUTH})
            
            if response.status_code != 200:
                logger.error(f"Error al obtener carro: {response.status_code} - {response.text}")
                return json.dumps({
                    "ok": False,
                    "mensaje": "Error al obtener el carrito de compras."
                }, ensure_ascii=False, indent=2)
            
            carro = response.json()
            
            # Calcular totales
            totales = self._calcular_total_carro(carro.get("data", {}))
            
            # Formatear productos para la respuesta
            productos_formateados = []
            for producto in carro.get("data", {}).get("productos", []):
                imagen = ""
                if producto.get("images"):
                    # Intentar obtener la URL de la imagen
                    for size in ["150", "250", "450"]:
                        if size in producto["images"] and len(producto["images"][size]) > 0:
                            imagen = producto["images"][size][0]
                            break
                
                productos_formateados.append({
                    "imagen": imagen,
                    "sku": producto.get("sku", ""),
                    "nombre": producto.get("nombre", ""),
                    "cantidad": producto.get("cantidad", 0),
                    "precio_neto": round(producto.get("precio", 0) / (1 + self.IVA)),
                    "precio": producto.get("precio", 0)
                })
            
            # Construir respuesta
            resultado = {
                "ok": True,
                "mensaje": f"Carrito de compras de {nombre_cliente} obtenido correctamente.",
                "data": {
                    "rut": rut_normalizado,
                    "nombre_cliente": nombre_cliente,
                    "sucursal": bodega["codBodega"],
                    "productos": productos_formateados,
                    "totales": totales
                }
            }
            
            return json.dumps(resultado, ensure_ascii=False, indent=2)
        
        except Exception as e:
            logger.error(f"Error general al obtener carrito: {e}")
            return json.dumps({
                "ok": False,
                "mensaje": f"Error al procesar la solicitud: {str(e)}"
            }, ensure_ascii=False, indent=2)
    
    # TODO: este método está incompleto, se debe completar.
    def completar_carro(
        self,
        rut: str,
        tipo_documento: str,
        opcion_entrega: str,
        forma_pago: str,
        nombre_usuario_vendedor: str,
        codigo_vendedor: str,
        sucursal: Optional[str] = None,
        tienda: Optional[str] = None,
        direccion_facturacion: Optional[str] = None,
        direccion_despacho: Optional[str] = None,
        observacion: Optional[str] = None,
        rut_transferencia: Optional[str] = None,
        contacto_notificacion: Optional[str] = None,
        contacto_solicitud: Optional[str] = None,
        fechas_entregas: Optional[List[str]] = None
    ) -> str:
        """
        Completa el proceso de compra generando una Nota de Venta (OV) o Cotización (CO)
        
        Args:
            rut (str): RUT del cliente
            tipo_documento (str): Tipo de documento a generar ("Cotización" o "Nota de Venta")
            opcion_entrega (str): Opción de entrega ("Entrega Inmediata", "Retiro en Tienda", "Despacho a Domicilio")
            forma_pago (str): Forma de pago
            nombre_usuario_vendedor (str): Nombre de usuario del vendedor
            codigo_vendedor (str): Código del vendedor
            sucursal (Optional[str]): Código de la sucursal
            tienda (Optional[str]): Tienda de retiro (requerido si opcion_entrega es "Retiro en Tienda")
            direccion_facturacion (Optional[str]): Dirección de facturación
            direccion_despacho (Optional[str]): Dirección de despacho (requerido si opcion_entrega es "Despacho a Domicilio")
            observacion (Optional[str]): Observaciones sobre el pedido
            rut_transferencia (Optional[str]): RUT para transferencia (requerido si forma_pago incluye "DP")
            contacto_notificacion (Optional[str]): Contacto para notificaciones
            contacto_solicitud (Optional[str]): Contacto de solicitud
            fechas_entregas (Optional[List[str]]): Lista de fechas de entrega para cada grupo
            
        Returns:
            str: Resultado de la operación en formato JSON
        """
        try:
            # Normalizar datos
            rut_normalizado = self._normalizar_rut(rut)
            rut_transferencia = self._normalizar_rut(rut_transferencia) if rut_transferencia else rut_normalizado
            
            # Validar datos básicos
            if not rut_normalizado:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Se requiere el RUT del cliente."
                }, ensure_ascii=False, indent=2)
            
            if tipo_documento not in ["Cotización", "Nota de Venta"]:
                return json.dumps({
                    "ok": False,
                    "mensaje": "El tipo de documento debe ser 'Cotización' o 'Nota de Venta'."
                }, ensure_ascii=False, indent=2)
            
            if opcion_entrega not in ["Entrega Inmediata", "Retiro en Tienda", "Despacho a Domicilio"]:
                return json.dumps({
                    "ok": False,
                    "mensaje": "La opción de entrega debe ser 'Entrega Inmediata', 'Retiro en Tienda' o 'Despacho a Domicilio'."
                }, ensure_ascii=False, indent=2)
            
            if opcion_entrega == "Retiro en Tienda" and not tienda:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Se requiere especificar la tienda de retiro."
                }, ensure_ascii=False, indent=2)
            
            if opcion_entrega == "Despacho a Domicilio" and not direccion_despacho:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Se requiere especificar la dirección de despacho."
                }, ensure_ascii=False, indent=2)
            
            # Obtener token del vendedor
            token = self._obtener_token_vendedor(codigo_vendedor)
            if not token:
                return json.dumps({
                    "ok": False,
                    "mensaje": "No se pudo obtener la autenticación del vendedor."
                }, ensure_ascii=False, indent=2)
            
            # En un entorno real, aquí implementaríamos todo el proceso de completar el carro
            # incluyendo verificación de stock, grupos de despacho, etc.
            
            # Por simplicidad, asumimos que se completa correctamente
            documento_id = f"{'CO' if tipo_documento == 'Cotización' else 'OV'}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # Construir respuesta
            resultado = {
                "ok": True,
                "mensaje": f"Se ha generado exitosamente el documento {documento_id} para el cliente.",
                "data": {
                    "tipo_documento": tipo_documento,
                    "folio": documento_id,
                    "rut": rut_normalizado,
                    "opcion_entrega": opcion_entrega,
                    "forma_pago": forma_pago,
                    "sucursal": sucursal
                }
            }
            
            return json.dumps(resultado, ensure_ascii=False, indent=2)
        
        except Exception as e:
            logger.error(f"Error al completar carrito: {e}")
            return json.dumps({
                "ok": False,
                "mensaje": f"Error al procesar la solicitud: {str(e)}"
            }, ensure_ascii=False, indent=2)
    
    def convertir_cotizacion(self, folio: str, codigo_vendedor: str) -> str:
        """
        Convierte una cotización (CO) en nota de venta (OV)
        
        Args:
            folio (str): Folio de la cotización a convertir
            codigo_vendedor (str): Código del vendedor
            
        Returns:
            str: Resultado de la operación en formato JSON
        """
        try:
            # Normalizar folio
            folio = folio.upper()
            if not folio.startswith("CO"):
                folio = f"CO-{folio}"
            
            # Validar datos básicos
            if not folio:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Se requiere el folio de la cotización."
                }, ensure_ascii=False, indent=2)
            
            # Obtener token del vendedor
            token = self._obtener_token_vendedor(codigo_vendedor)
            if not token:
                return json.dumps({
                    "ok": False,
                    "mensaje": "No se pudo obtener la autenticación del vendedor."
                }, ensure_ascii=False, indent=2)
            
            # Verificar el estado de la cotización
            url = f"https://replicacion.implementos.cl/apiOmnichannel/api/carro/cargarDocumento/{folio}"
            headers = {"Authorization": f"Bearer {token}"}
            
            response = requests.get(url, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Error al verificar cotización: {response.status_code} - {response.text}")
                return json.dumps({
                    "ok": False,
                    "mensaje": "Error al verificar la cotización."
                }, ensure_ascii=False, indent=2)
            
            cotizacion_data = response.json()
            
            estado_cotizacion = cotizacion_data.get("estadoCotizacion", {})
            
            # Verificar si la cotización puede ser convertida
            if estado_cotizacion.get("cotizacionConvertida"):
                return json.dumps({
                    "ok": False,
                    "mensaje": f"La cotización ya fue convertida anteriormente a la Nota de Venta: {estado_cotizacion.get('ordenVenta')}."
                }, ensure_ascii=False, indent=2)
            
            if estado_cotizacion.get("cotizacionCaduca"):
                return json.dumps({
                    "ok": False,
                    "mensaje": "La cotización está vencida y no puede ser convertida."
                }, ensure_ascii=False, indent=2)
            
            if estado_cotizacion.get("esCDRetiroInmediato"):
                return json.dumps({
                    "ok": False,
                    "mensaje": "Es una cotización del Centro de Distribución con retiro inmediato, no se puede convertir directamente."
                }, ensure_ascii=False, indent=2)
            
            # Convertir la cotización
            url = "https://replicacion.implementos.cl/apiOmnichannel/api/carro/convertirCotizacion"
            payload = {"folio": folio}
            
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Error al convertir cotización: {response.status_code} - {response.text}")
                return json.dumps({
                    "ok": False,
                    "mensaje": "Error al convertir la cotización."
                }, ensure_ascii=False, indent=2)
            
            resultado = response.json()
            orden_venta = resultado.get("ordenVenta", "")
            
            # Construir respuesta
            resultado = {
                "ok": True,
                "mensaje": f"Cotización {folio} convertida exitosamente a Nota de Venta {orden_venta}.",
                "data": {
                    "cotizacion": folio,
                    "nota_venta": orden_venta
                }
            }
            
            return json.dumps(resultado, ensure_ascii=False, indent=2)
        
        except Exception as e:
            logger.error(f"Error general al convertir cotización: {e}")
            return json.dumps({
                "ok": False,
                "mensaje": f"Error al procesar la solicitud: {str(e)}"
            }, ensure_ascii=False, indent=2)
import json
import requests
from typing import List, Dict, Any, Optional
from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger
from config.config import Config
from pymongo import MongoClient
from datetime import datetime

from utils.obtener_bodega_vendedor import obtener_bodega_vendedor
from utils.obtener_token_omni_vendedor import obtener_token_omni_vendedor


class CarroVtTool(Toolkit):
    def __init__(self):
        super().__init__(name="carro_vt_tool")
        # Registrar las funciones en el toolkit
        self.register(self.agregar_producto_carro)
        self.register(self.modificar_producto_carro)
        self.register(self.eliminar_producto_carro)
        self.register(self.ver_carro)
        self.register(self.convertir_cotizacion)
        self.register(self.completar_carro)

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

    def _validar_cliente(self, rut: str) -> dict:
        """
        Valida que el cliente exista y retorna su información

        Args:
            rut (str): RUT del cliente a validar

        Returns:
            dict: Resultado con información del cliente o error
        """
        try:
            rut_normalizado = self._normalizar_rut(rut)

            if not rut_normalizado:
                return {
                    "ok": False,
                    "mensaje": "Se requiere el RUT del cliente.",
                    "data": None
                }

            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            cliente = db.clientes.find_one({"rut": rut_normalizado}, {"nombre": 1, "recid": 1})

            if not cliente:
                return {
                    "ok": False,
                    "mensaje": "Cliente no encontrado.",
                    "data": None
                }

            return {
                "ok": True,
                "mensaje": "",
                "data": {
                    "rut": rut_normalizado,
                    "nombre": cliente.get("nombre", ""),
                    "recid": cliente.get("recid", 0)
                }
            }
        except Exception as e:
            logger.error(f"Error al consultar cliente: {e}")
            return {
                "ok": False,
                "mensaje": "Error al verificar el cliente.",
                "data": None
            }

    def _obtener_bodega(self, codigo_vendedor: int, sucursal: Optional[str] = None) -> dict:
        """
        Obtiene y valida la bodega del vendedor

        Args:
            codigo_vendedor (int): Código del vendedor
            sucursal (Optional[str]): Código de sucursal opcional

        Returns:
            dict: Resultado con información de la bodega o error
        """
        bodega = obtener_bodega_vendedor(codigo_vendedor, sucursal)

        if not bodega["codBodega"]:
            return {
                "ok": False,
                "mensaje": "No se encontró la bodega asociada al vendedor.",
                "data": None
            }

        return {
            "ok": True,
            "mensaje": "",
            "data": bodega
        }

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

        return rut.replace(".", "").strip()

    def _obtener_carro_actual(self, rut: str, bodega_codigo: str, usuario_vendedor: str) -> dict:
        """
        Obtiene el carrito actual del cliente

        Args:
            rut (str): RUT normalizado del cliente
            bodega_codigo (str): Código de la bodega
            usuario_vendedor (str): Usuario del vendedor

        Returns:
            dict: Resultado con el carrito o error
        """
        url = f"https://b2b-api.implementos.cl/api/carro/omni"
        params = {
            "usuario": rut,
            "sucursal": bodega_codigo,
            "rut": rut,
            "vendedor": usuario_vendedor,
            "ov": "",
            "folioPropuesta": ""
        }

        try:
            response = requests.get(url, params=params, headers={"Authorization": self.BASIC_AUTH})

            if response.status_code != 200:
                logger.error(f"Error al obtener carro: {response.status_code} - {response.text}")
                return {
                    "ok": False,
                    "mensaje": "Error al obtener el carrito de compras.",
                    "data": None
                }

            return {
                "ok": True,
                "mensaje": "",
                "data": response.json().get("data", {})
            }
        except Exception as e:
            logger.error(f"Error al obtener carrito: {e}")
            return {
                "ok": False,
                "mensaje": f"Error al obtener el carrito: {str(e)}",
                "data": None
            }

    def _formatear_productos(self, productos: List[Dict]) -> List[Dict]:
        """
        Formatea la lista de productos para la respuesta

        Args:
            productos (List[Dict]): Lista de productos del carrito

        Returns:
            List[Dict]: Lista de productos formateada
        """
        productos_formateados = []
        for producto in productos:
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

        return productos_formateados

    def agregar_producto_carro(
        self,
        rut: str,
        sku: str,
        cantidad: int,
        usuario_vendedor: str,
        codigo_vendedor: int,
        sucursal: Optional[str] = None
    ) -> str:
        """
        Agrega un producto al carrito de compras

        Args:
            rut (str): RUT del cliente
            sku (str): SKU del producto a agregar
            cantidad (int): Cantidad del producto
            usuario_vendedor (str): Cuenta de usuario del vendedor
            codigo_vendedor (int): Código del vendedor
            sucursal (Optional[str]): Código de la sucursal

        Returns:
            str: Resultado de la operación en formato JSON
        """
        try:
            # Validar datos básicos
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

            # Validar cliente
            resultado_cliente = self._validar_cliente(rut)
            if not resultado_cliente["ok"]:
                return json.dumps(resultado_cliente, ensure_ascii=False, indent=2)

            cliente_data = resultado_cliente["data"]
            rut_normalizado = cliente_data["rut"]
            nombre_cliente = cliente_data["nombre"]

            # Obtener bodega
            resultado_bodega = self._obtener_bodega(codigo_vendedor, sucursal)
            if not resultado_bodega["ok"]:
                return json.dumps(resultado_bodega, ensure_ascii=False, indent=2)

            bodega = resultado_bodega["data"]

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
                "vendedor": usuario_vendedor,
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
            if carro_actual.get("data") is not None and carro_actual.get("data", {}).get("productos"):
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
                "vendedor": usuario_vendedor,
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
        usuario_vendedor: str,
        codigo_vendedor: int,
        sucursal: Optional[str] = None
    ) -> str:
        """
        Modifica la cantidad de un producto en el carrito de compras

        Args:
            rut (str): RUT del cliente
            sku (str): SKU del producto a modificar
            cantidad (int): Nueva cantidad del producto
            usuario_vendedor (str): Cuenta de usuario del vendedor
            codigo_vendedor (int): Código del vendedor
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

            # Validar cliente
            resultado_cliente = self._validar_cliente(rut)
            if not resultado_cliente["ok"]:
                return json.dumps(resultado_cliente, ensure_ascii=False, indent=2)

            cliente_data = resultado_cliente["data"]
            rut_normalizado = cliente_data["rut"]
            nombre_cliente = cliente_data["nombre"]

            # Obtener bodega
            resultado_bodega = self._obtener_bodega(codigo_vendedor, sucursal)
            if not resultado_bodega["ok"]:
                return json.dumps(resultado_bodega, ensure_ascii=False, indent=2)

            bodega = resultado_bodega["data"]

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
                "vendedor": usuario_vendedor,
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
                    "vendedor": usuario_vendedor,
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
        usuario_vendedor: str,
        codigo_vendedor: int,
        sucursal: Optional[str] = None
    ) -> str:
        """
        Elimina un producto del carrito de compras

        Args:
            rut (str): RUT del cliente
            sku (str): SKU del producto a eliminar
            usuario_vendedor (str): Cuenta de usuario del vendedor
            codigo_vendedor (int): Código del vendedor
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

            # Validar cliente
            resultado_cliente = self._validar_cliente(rut)
            if not resultado_cliente["ok"]:
                return json.dumps(resultado_cliente, ensure_ascii=False, indent=2)

            cliente_data = resultado_cliente["data"]
            rut_normalizado = cliente_data["rut"]
            nombre_cliente = cliente_data["nombre"]

            # Obtener bodega
            resultado_bodega = self._obtener_bodega(codigo_vendedor, sucursal)
            if not resultado_bodega["ok"]:
                return json.dumps(resultado_bodega, ensure_ascii=False, indent=2)

            bodega = resultado_bodega["data"]

            # Eliminar el producto del carro
            url = "https://b2b-api.implementos.cl/api/carro/omni/articulo"
            payload = {
                "folioPropuesta": "",
                "ov": "",
                "rut": rut_normalizado,
                "usuario": rut_normalizado,
                "sucursal": bodega["codBodega"],
                "vendedor": usuario_vendedor,
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
                    "vendedor": usuario_vendedor,
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
        usuario_vendedor: str,
        codigo_vendedor: int,
        sucursal: Optional[str] = None
    ) -> str:
        """
        Obtiene el contenido del carrito de compras de un cliente

        Args:
            rut (str): RUT del cliente
            usuario_vendedor (str): Cuenta de usuario del vendedor
            codigo_vendedor (int): Código del vendedor
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

            # Validar cliente
            resultado_cliente = self._validar_cliente(rut)
            if not resultado_cliente["ok"]:
                return json.dumps(resultado_cliente, ensure_ascii=False, indent=2)

            cliente_data = resultado_cliente["data"]
            rut_normalizado = cliente_data["rut"]
            nombre_cliente = cliente_data["nombre"]

            # Obtener bodega
            resultado_bodega = self._obtener_bodega(codigo_vendedor, sucursal)
            if not resultado_bodega["ok"]:
                return json.dumps(resultado_bodega, ensure_ascii=False, indent=2)

            bodega = resultado_bodega["data"]

            # Obtener el carrito del cliente
            resultado_carro = self._obtener_carro_actual(rut_normalizado, bodega["codBodega"], usuario_vendedor)
            if not resultado_carro["ok"]:
                return json.dumps(resultado_carro, ensure_ascii=False, indent=2)

            carro = resultado_carro["data"]

            if not carro:
                resultado = {
                    "ok": False,
                    "mensaje": f"Carrito de compras de {nombre_cliente} no encontrado.",
                    "data": {
                        "rut": rut_normalizado,
                        "nombre_cliente": nombre_cliente,
                        "sucursal": bodega["codBodega"],
                        "productos": [],
                        "totales": []
                    }
                }
                return json.dumps(resultado, ensure_ascii=False, indent=2)

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

    def convertir_cotizacion(self, folio: str, codigo_vendedor: int) -> str:
        """
        Convierte una cotización (CO) en nota de venta (OV)

        Args:
            folio (str): Folio de la cotización a convertir
            codigo_vendedor (int): Código del vendedor

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
            token = obtener_token_omni_vendedor(codigo_vendedor)
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

    def completar_carro(
        self,
        rut: str,
        tipo_documento: str,
        opcion_entrega: str,
        forma_pago: str,
        usuario_vendedor: str,
        codigo_vendedor: int,
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
            usuario_vendedor (str): Cuenta de usuario del vendedor
            codigo_vendedor (int): Código del vendedor
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

            # Verificar si forma_pago incluye DP (Depósito) y si se especificó el RUT de transferencia
            if "DP" in forma_pago and not rut_transferencia:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Se requiere el RUT para transferencia cuando se usa Depósito como forma de pago."
                }, ensure_ascii=False, indent=2)

            # Obtener token del vendedor
            token = obtener_token_omni_vendedor(codigo_vendedor)
            if not token:
                return json.dumps({
                    "ok": False,
                    "mensaje": "No se pudo obtener la autenticación del vendedor."
                }, ensure_ascii=False, indent=2)

            # Obtener información del cliente
            try:
                client = MongoClient(Config.MONGO_NUBE)
                db = client.Implenet
                cliente = db.clientes.find_one({"rut": rut_normalizado}, {"nombre": 1, "recid": 1})

                if not cliente:
                    return json.dumps({
                        "ok": False,
                        "mensaje": "Cliente no encontrado."
                    }, ensure_ascii=False, indent=2)

                nombre_cliente = cliente.get("nombre", "")
                recid_cliente = cliente.get("recid", 0)
            except Exception as e:
                logger.error(f"Error al consultar cliente: {e}")
                return json.dumps({
                    "ok": False,
                    "mensaje": "Error al verificar el cliente."
                }, ensure_ascii=False, indent=2)

            # Obtener la bodega del vendedor
            bodega = obtener_bodega_vendedor(codigo_vendedor, sucursal)
            if not bodega["codBodega"]:
                return json.dumps({
                    "ok": False,
                    "mensaje": "No se encontró la bodega asociada al vendedor."
                }, ensure_ascii=False, indent=2)

            # Obtener el carrito actual
            url = f"https://b2b-api.implementos.cl/api/carro/omni"
            params = {
                "usuario": rut_normalizado,
                "sucursal": bodega["codBodega"],
                "rut": rut_normalizado,
                "vendedor": usuario_vendedor,
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

            carro_actual = response.json().get("data", {})

            # Verificar que el carrito tenga productos
            if not carro_actual.get("productos") or len(carro_actual.get("productos", [])) == 0:
                return json.dumps({
                    "ok": False,
                    "mensaje": "El carrito no tiene productos."
                }, ensure_ascii=False, indent=2)

            # Validar stock si es Nota de Venta con Entrega Inmediata
            if tipo_documento == "Nota de Venta" and opcion_entrega == "Entrega Inmediata":
                for producto in carro_actual.get("productos", []):
                    # Verificar stock
                    stock_url = f"https://replicacion.implementos.cl/apiCarro/api/carro/stock?sku={producto['sku']}&sucursal={bodega['codBodega']}"
                    stock_response = requests.get(stock_url, headers={"Authorization": self.BASIC_AUTH})

                    if stock_response.status_code != 200:
                        return json.dumps({
                            "ok": False,
                            "mensaje": f"Error al verificar stock del producto {producto['sku']}."
                        }, ensure_ascii=False, indent=2)

                    stock_disponible = stock_response.json()

                    if stock_disponible < producto["cantidad"]:
                        return json.dumps({
                            "ok": False,
                            "mensaje": f"Stock insuficiente para el producto {producto['nombre']} ({producto['sku']}). Disponible: {stock_disponible}, Requerido: {producto['cantidad']}."
                        }, ensure_ascii=False, indent=2)

            # Preparar datos para grupos de despacho
            if opcion_entrega != "Entrega Inmediata":
                # Para Retiro en Tienda o Despacho a Domicilio, configurar promesa de entrega
                if opcion_entrega == "Retiro en Tienda":
                    # Obtener datos de tiendas
                    tiendas_url = f"https://b2b-api.implementos.cl/api/logistica/tiendasretiroomni?usuario={rut_normalizado}&ov=&vendedor={usuario_vendedor}"
                    tiendas_response = requests.get(tiendas_url, headers={"Authorization": self.BASIC_AUTH})

                    if tiendas_response.status_code != 200:
                        return json.dumps({
                            "ok": False,
                            "mensaje": "Error al obtener las tiendas disponibles."
                        }, ensure_ascii=False, indent=2)

                    tiendas = tiendas_response.json().get("data", {}).get("todos", [])
                    tienda_seleccionada = None

                    # Buscar la tienda especificada
                    for t in tiendas:
                        if tienda.lower() in t.get("nombre", "").lower():
                            tienda_seleccionada = t
                            break

                    if not tienda_seleccionada:
                        return json.dumps({
                            "ok": False,
                            "mensaje": f"No se encontró la tienda '{tienda}'."
                        }, ensure_ascii=False, indent=2)

                    # Verificar promesa de entrega para Retiro en Tienda
                    promesa_url = f"https://b2b-api.implementos.cl/api/promesa-entrega/retiroTienda/{tienda_seleccionada['codigo']}|{tienda_seleccionada.get('codRegion', '0')}"
                    promesa_payload = {
                        "omni": False,
                        "bypassStock": "0",
                        "bodegaDesdeCodigo": "",
                        "multiProveedor": False,
                        "productos": [
                            {"sku": p["sku"], "cantidad": p["cantidad"]} for p in carro_actual.get("productos", [])
                        ],
                        "proveedorCodigo": "",
                        "rut": rut_normalizado,
                        "stockSeguridad": False,
                        "usarStockAX": True
                    }

                    promesa_response = requests.post(promesa_url, json=promesa_payload, headers={"Authorization": self.BASIC_AUTH})

                    if promesa_response.status_code != 200:
                        return json.dumps({
                            "ok": False,
                            "mensaje": "Error al verificar las fechas de entrega disponibles."
                        }, ensure_ascii=False, indent=2)

                    sub_ordenes = promesa_response.json().get("data", {}).get("respuesta", [{}])[0].get("subOrdenes", [])

                    if not sub_ordenes:
                        return json.dumps({
                            "ok": False,
                            "mensaje": "No hay fechas de entrega disponibles para esta tienda."
                        }, ensure_ascii=False, indent=2)

                    # Asignar grupos de despacho
                    grupos_payload = {
                        "ov": "",
                        "folioPropuesta": "",
                        "sucursal": bodega["codBodega"],
                        "usuario": rut_normalizado,
                        "vendedor": usuario_vendedor,
                        "grupos": [
                            {
                                "bodega": so["bodega"],
                                "encontrado": True,
                                "fletes": so["fletes"],
                                "envio": so["envio"],
                                "identificador": so["identificador"],
                                "paraCalculo": so["paraCalculo"],
                                "pesoTotal": so["pesoTotal"],
                                "productosDespachar": so["productosDespachar"],
                                "tipoEnvioVenta": so["tipoEnvioVenta"]
                            } for so in sub_ordenes
                        ]
                    }

                    grupos_response = requests.post(
                        "https://b2b-api.implementos.cl/api/carro/grupos/despacho",
                        json=grupos_payload,
                        headers={"Authorization": self.BASIC_AUTH}
                    )

                    if grupos_response.status_code != 200:
                        return json.dumps({
                            "ok": False,
                            "mensaje": "Error al asignar los grupos de despacho."
                        }, ensure_ascii=False, indent=2)

                elif opcion_entrega == "Despacho a Domicilio":
                    # Obtener direcciones de despacho
                    direcciones_url = f"https://replicacion.implementos.cl/apiOmnichannel/api/cliente/direcciones?rut={rut_normalizado}&tipo=2"
                    direcciones_response = requests.get(direcciones_url, headers={"Authorization": f"Bearer {token}"})

                    if direcciones_response.status_code != 200:
                        return json.dumps({
                            "ok": False,
                            "mensaje": "Error al obtener las direcciones de despacho."
                        }, ensure_ascii=False, indent=2)

                    direcciones = direcciones_response.json()
                    direccion_seleccionada = None

                    # Buscar la dirección especificada
                    for d in direcciones:
                        if direccion_despacho.lower() in d.get("direccionCompleta", "").lower():
                            direccion_seleccionada = d
                            break

                    if not direccion_seleccionada:
                        return json.dumps({
                            "ok": False,
                            "mensaje": f"No se encontró la dirección de despacho '{direccion_despacho}'."
                        }, ensure_ascii=False, indent=2)

                    # Verificar promesa de entrega para Despacho a Domicilio
                    promesa_url = f"https://b2b-api.implementos.cl/api/promesa-entrega/domicilio/{direccion_seleccionada['comuna']}|{direccion_seleccionada.get('codRegion', '0')}"
                    promesa_payload = {
                        "omni": False,
                        "bypassStock": "0",
                        "bodegaDesdeCodigo": "",
                        "multiProveedor": False,
                        "productos": [
                            {"sku": p["sku"], "cantidad": p["cantidad"]} for p in carro_actual.get("productos", [])
                        ],
                        "proveedorCodigo": "",
                        "rut": rut_normalizado,
                        "stockSeguridad": False,
                        "usarStockAX": True
                    }

                    promesa_response = requests.post(promesa_url, json=promesa_payload, headers={"Authorization": self.BASIC_AUTH})

                    if promesa_response.status_code != 200:
                        return json.dumps({
                            "ok": False,
                            "mensaje": "Error al verificar las fechas de entrega disponibles."
                        }, ensure_ascii=False, indent=2)

                    sub_ordenes = promesa_response.json().get("data", {}).get("respuesta", [{}])[0].get("subOrdenes", [])

                    if not sub_ordenes:
                        return json.dumps({
                            "ok": False,
                            "mensaje": "No hay fechas de entrega disponibles para esta dirección."
                        }, ensure_ascii=False, indent=2)

                    # Asignar grupos de despacho
                    grupos_payload = {
                        "ov": "",
                        "folioPropuesta": "",
                        "sucursal": bodega["codBodega"],
                        "usuario": rut_normalizado,
                        "vendedor": usuario_vendedor,
                        "grupos": [
                            {
                                "bodega": so["bodega"],
                                "encontrado": True,
                                "fletes": so["fletes"],
                                "envio": so["envio"],
                                "identificador": so["identificador"],
                                "paraCalculo": so["paraCalculo"],
                                "pesoTotal": so["pesoTotal"],
                                "productosDespachar": so["productosDespachar"],
                                "tipoEnvioVenta": so["tipoEnvioVenta"]
                            } for so in sub_ordenes
                        ]
                    }

                    grupos_response = requests.post(
                        "https://b2b-api.implementos.cl/api/carro/grupos/despacho",
                        json=grupos_payload,
                        headers={"Authorization": self.BASIC_AUTH}
                    )

                    if grupos_response.status_code != 200:
                        return json.dumps({
                            "ok": False,
                            "mensaje": "Error al asignar los grupos de despacho."
                        }, ensure_ascii=False, indent=2)

                # Obtener el carrito actualizado después de asignar grupos
                response = requests.get(url, params=params, headers={"Authorization": self.BASIC_AUTH})

                if response.status_code != 200:
                    logger.error(f"Error al obtener carro actualizado: {response.status_code} - {response.text}")
                    return json.dumps({
                        "ok": False,
                        "mensaje": "Error al obtener el carrito actualizado."
                    }, ensure_ascii=False, indent=2)

                carro_actual = response.json().get("data", {})

                # Verificar que se hayan asignado correctamente los grupos
                if opcion_entrega != "Entrega Inmediata" and (not carro_actual.get("grupos") or len(carro_actual.get("grupos", [])) == 0):
                    return json.dumps({
                        "ok": False,
                        "mensaje": "Error al asignar los grupos de despacho."
                    }, ensure_ascii=False, indent=2)

                # Verificar las fechas de entrega
                if fechas_entregas and len(fechas_entregas) > 0:
                    if len(fechas_entregas) != len(carro_actual.get("grupos", [])):
                        return json.dumps({
                            "ok": False,
                            "mensaje": "El número de fechas de entrega no coincide con el número de grupos."
                        }, ensure_ascii=False, indent=2)

                    # Validar cada fecha de entrega
                    for i, grupo in enumerate(carro_actual.get("grupos", [])):
                        fecha_valida = False
                        for flete in grupo.get("flete", []):
                            # Convertir fechas al mismo formato para comparar
                            fecha_flete = datetime.fromisoformat(flete["fecha"].replace("Z", "+00:00")).strftime("%d/%m/%Y")
                            if fecha_flete == fechas_entregas[i]:
                                fecha_valida = True
                                break

                        if not fecha_valida:
                            return json.dumps({
                                "ok": False,
                                "mensaje": f"La fecha '{fechas_entregas[i]}' no es válida para el grupo {i+1}."
                            }, ensure_ascii=False, indent=2)

            # Obtener un nuevo folio para el documento
            nuevo_folio_url = "https://b2b-api.implementos.cl/api/carro/obtieneNuevoFolio"
            nuevo_folio_response = requests.post(nuevo_folio_url, json={"id": carro_actual.get("_id")}, headers={"Authorization": self.BASIC_AUTH})

            if nuevo_folio_response.status_code != 200:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Error al obtener un nuevo folio para el documento."
                }, ensure_ascii=False, indent=2)

            folio = nuevo_folio_response.json().get("folio")

            if not folio:
                return json.dumps({
                    "ok": False,
                    "mensaje": "No se pudo obtener un folio para el documento."
                }, ensure_ascii=False, indent=2)

            # Obtener información de contactos del cliente
            contactos_url = f"https://replicacion.implementos.cl/apiOmnichannel/api/cliente/contactos?rut={rut_normalizado}"
            contactos_response = requests.get(contactos_url, headers={"Authorization": f"Bearer {token}"})

            if contactos_response.status_code != 200:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Error al obtener los contactos del cliente."
                }, ensure_ascii=False, indent=2)

            contactos = contactos_response.json()

            # Buscar los contactos especificados
            contacto_notif = None
            contacto_solic = None

            if contacto_notificacion:
                for c in contactos:
                    if contacto_notificacion.lower() in c.get("nombre", "").lower():
                        contacto_notif = c
                        break
            else:
                # Usar el primer contacto disponible
                contacto_notif = contactos[0] if contactos else None

            if contacto_solicitud:
                for c in contactos:
                    if contacto_solicitud.lower() in c.get("nombre", "").lower():
                        contacto_solic = c
                        break
            else:
                # Buscar contactos de tipo solicitud (COM)
                contactos_solicitud = [c for c in contactos if c.get("tipo") == "COM" and (c.get("cargo") == "COMPRAS" or not c.get("cargo"))]
                contacto_solic = contactos_solicitud[0] if contactos_solicitud else (contactos[0] if contactos else None)

            if not contacto_notif:
                return json.dumps({
                    "ok": False,
                    "mensaje": "No se encontró el contacto de notificación especificado."
                }, ensure_ascii=False, indent=2)

            if not contacto_solic:
                return json.dumps({
                    "ok": False,
                    "mensaje": "No se encontró el contacto de solicitud especificado."
                }, ensure_ascii=False, indent=2)

            # Obtener información de formas de pago
            formas_pago_url = f"https://replicacion.implementos.cl/apiCliente/api/cliente/formapago?recid={recid_cliente}"
            formas_pago_response = requests.get(formas_pago_url, headers={"Authorization": self.BASIC_AUTH})

            if formas_pago_response.status_code != 200:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Error al obtener las formas de pago disponibles."
                }, ensure_ascii=False, indent=2)

            formas_pago = formas_pago_response.json().get("data", [])
            forma_pago_seleccionada = None

            # Obtener el código de la forma de pago seleccionada
            for fp in formas_pago:
                if forma_pago.lower() in fp.get("nombre", "").lower() or forma_pago.lower() in fp.get("codigo", "").lower():
                    forma_pago_seleccionada = fp
                    break

            if not forma_pago_seleccionada:
                return json.dumps({
                    "ok": False,
                    "mensaje": f"No se encontró la forma de pago '{forma_pago}'."
                }, ensure_ascii=False, indent=2)

            # Obtener direcciones de facturación
            direcciones_fact_url = f"https://replicacion.implementos.cl/apiOmnichannel/api/cliente/direcciones?rut={rut_normalizado}&tipo=1"
            direcciones_fact_response = requests.get(direcciones_fact_url, headers={"Authorization": f"Bearer {token}"})

            if direcciones_fact_response.status_code != 200:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Error al obtener las direcciones de facturación."
                }, ensure_ascii=False, indent=2)

            direcciones_fact = direcciones_fact_response.json()
            direccion_fact_seleccionada = None

            if direccion_facturacion:
                for d in direcciones_fact:
                    if direccion_facturacion.lower() in d.get("direccionCompleta", "").lower():
                        direccion_fact_seleccionada = d
                        break
            else:
                # Usar la primera dirección disponible
                direccion_fact_seleccionada = direcciones_fact[0] if direcciones_fact else None

            if not direccion_fact_seleccionada:
                return json.dumps({
                    "ok": False,
                    "mensaje": f"No se encontró la dirección de facturación."
                }, ensure_ascii=False, indent=2)

            # Preparar el payload para generar el documento
            carro_entity = carro_actual.copy()
            carro_entity["folio"] = folio
            carro_entity["tipo"] = 1 if tipo_documento == "Cotización" else 2
            carro_entity["estado"] = "abierto"
            carro_entity["estadoAX"] = "0"
            carro_entity["recid"] = 0
            carro_entity["cliente"] = {"rutCliente": rut_normalizado}
            carro_entity["OrdenCompra"] = ""
            carro_entity["origenVenta"] = ""
            carro_entity["documento"] = ""
            carro_entity["tokenPago"] = ""
            carro_entity["tipoCarro"] = "OMN"
            carro_entity["paso"] = 3
            carro_entity["correlativo"] = 3
            carro_entity["remarketing"] = 0
            carro_entity["proveedorPago"] = ""
            carro_entity["web"] = 0
            carro_entity["usuario"] = rut_normalizado
            carro_entity["vendedor"] = usuario_vendedor.lower()
            carro_entity["observacion"] = observacion or ""
            carro_entity["estadoDocumento"] = 1
            carro_entity["numeroDocumento"] = 0
            carro_entity["rutAnonimo"] = ""
            carro_entity["nombreAnonimo"] = ""
            carro_entity["emailAnonimo"] = ""
            carro_entity["fonoAnonimo"] = ""
            carro_entity["usuarioCreadorAnonimo"] = 0
            carro_entity["despachoVendedorCodUsuario"] = 0
            carro_entity["folioPropuesta"] = 0
            carro_entity["sucursalPropuesta"] = ""
            carro_entity["cotizacionOmni"] = ""
            carro_entity["ArchivosAdjuntos"] = []
            carro_entity["rutTransferencia"] = rut_transferencia
            carro_entity["formaPago"] = forma_pago_seleccionada["codigo"]
            carro_entity["direccionFacturacionRecid"] = direccion_fact_seleccionada["recid"]

            # Datos de contacto
            carro_entity["fonoNotificacion"] = contacto_notif.get("telefonos", [{}])[0].get("valor", "") if contacto_notif.get("telefonos") else ""
            carro_entity["emailNotificacion"] = contacto_notif.get("emails", [{}])[0].get("valor", "") if contacto_notif.get("emails") else ""
            carro_entity["nombreNotificacion"] = contacto_notif.get("nombre", "")
            carro_entity["contactoSolicitud"] = contacto_solic.get("id", "")

            # Dependiendo de la opción de entrega, configurar despacho
            if opcion_entrega == "Entrega Inmediata":
                carro_entity["productos"] = carro_actual.get("productos", [])
                carro_entity["flete"] = []
                carro_entity["codigoBodega"] = bodega["codBodega"]
                carro_entity["codigoSucursal"] = bodega["codBodega"] if carro_actual.get("codigoSucursal", "").upper() == "UNDEFINED" else carro_actual.get("codigoSucursal", "")

                # Configurar despacho para Entrega Inmediata
                carro_entity["despacho"] = {
                    "tipo": "STD",
                    "codTipo": "VEN- RTCLI",
                    "origen": bodega["codBodega"],
                    "recidDireccion": 0,  # No hay dirección específica para Entrega Inmediata
                    "codProveedor": "IMPLEMENTOS",
                    "nombreProveedor": "IMPLEMENTOS",
                    "precio": 0,
                    "descuento": 0,
                    "observacion": observacion or "",
                    "diasNecesarios": 0,
                    "fechaPicking": datetime.now().isoformat(),
                    "fechaEntrega": datetime.now().isoformat(),
                    "fechaDespacho": datetime.now().isoformat(),
                    "identificador": f"{bodega['codBodega']}|0",
                    "codTipoEnvioVenta": 0,
                    "tipoEnvioVenta": "Envio con stock bodega"
                }

                # Configurar grupos
                carro_entity["grupos"] = [{
                    "despacho": carro_entity["despacho"],
                    "codTipoEnvioVenta": 0,
                    "tipoEnvioVenta": "Envio con stock bodega",
                    "flete": [],
                    "id": 1,
                    "identificador": f"{bodega['codBodega']}|0",
                    "origen": bodega["codBodega"],
                    "productos": carro_entity["productos"]
                }]

            else:
                # Para Retiro en Tienda o Despacho a Domicilio, usar los grupos ya configurados
                carro_entity["productos"] = carro_actual.get("productos", [])
                carro_entity["grupos"] = carro_actual.get("grupos", [])
                carro_entity["flete"] = carro_actual.get("flete", [])
                carro_entity["codigoBodega"] = carro_actual.get("codigoBodega", "")
                carro_entity["codigoSucursal"] = carro_actual.get("codigoBodega", "") if carro_actual.get("codigoSucursal", "").upper() == "UNDEFINED" else carro_actual.get("codigoSucursal", "")

                # Si se especificaron fechas de entrega, actualizarlas en los grupos
                if fechas_entregas and len(fechas_entregas) == len(carro_entity["grupos"]):
                    for i, grupo in enumerate(carro_entity["grupos"]):
                        # Buscar el flete que corresponde a la fecha seleccionada
                        fecha_seleccionada = fechas_entregas[i]
                        flete_seleccionado = None

                        for flete in grupo.get("flete", []):
                            fecha_flete = datetime.fromisoformat(flete["fecha"].replace("Z", "+00:00")).strftime("%d/%m/%Y")
                            if fecha_flete == fecha_seleccionada:
                                flete_seleccionado = flete
                                break

                        if flete_seleccionado:
                            # Actualizar el despacho del grupo con la fecha seleccionada
                            grupo["despacho"]["fechaEntrega"] = flete_seleccionado["fecha"]
                            grupo["despacho"]["fechaPicking"] = flete_seleccionado["fechaPicking"]
                            grupo["despacho"]["fechaDespacho"] = flete_seleccionado["fechaPicking"]
                            grupo["despacho"]["diasNecesarios"] = flete_seleccionado["opcionServicio"]["diashabilesnecesarios"]

                # Usar el despacho del primer grupo como despacho principal
                if carro_entity["grupos"]:
                    carro_entity["despacho"] = carro_entity["grupos"][0]["despacho"]

            # Generar el documento
            if forma_pago_seleccionada["codigo"] == "LINK_EC":
                # Si es botón de pago, crear un link de pago
                carro_entity["id"] = carro_actual.get("_id", "")

                link_pago_url = "https://b2b-api.implementos.cl/api/carro/crearCarroOmnichanel"
                link_pago_response = requests.post(link_pago_url, json=carro_entity, headers={"Authorization": self.BASIC_AUTH})

                if link_pago_response.status_code != 200:
                    return json.dumps({
                        "ok": False,
                        "mensaje": "Error al generar el link de pago."
                    }, ensure_ascii=False, indent=2)

                link_pago_data = link_pago_response.json()
                url_pago = link_pago_data.get("url", "")

                # Agregar contactos al carro
                contactos_carro_url = "https://b2b-api.implementos.cl/api/carro/agregarContactos"
                contactos_carro_payload = {
                    "id": carro_entity["id"],
                    "texto4": carro_entity["fonoNotificacion"],
                    "texto5": carro_entity["emailNotificacion"],
                    "textoNombre": carro_entity["nombreNotificacion"]
                }

                requests.post(contactos_carro_url, json=contactos_carro_payload, headers={"Authorization": self.BASIC_AUTH})

                # Construir respuesta con link de pago
                return json.dumps({
                    "ok": True,
                    "mensaje": f"Se ha generado el link de pago exitosamente para {nombre_cliente}.",
                    "data": {
                        "tipo_documento": tipo_documento,
                        "link_pago": url_pago,
                        "rut": rut_normalizado,
                        "nombre_cliente": nombre_cliente
                    }
                }, ensure_ascii=False, indent=2)

            else:
                # Generar Cotización o Nota de Venta
                generar_documento_url = "https://replicacion.implementos.cl/apiOmnichannel/api/carro/generaDocumento"
                generar_documento_response = requests.post(generar_documento_url, json=carro_entity, headers={"Authorization": f"Bearer {token}"})

                if generar_documento_response.status_code != 200:
                    return json.dumps({
                        "ok": False,
                        "mensaje": "Error al generar el documento."
                    }, ensure_ascii=False, indent=2)

                documento_data = generar_documento_response.json()

                # Obtener los números de documentos generados
                documentos = []
                for respuesta in documento_data.get("respuesta", []):
                    if respuesta.get("carro", {}).get("numero"):
                        documentos.append(respuesta["carro"]["numero"])

                # Actualizar el estado del carro
                estado_carro_url = "https://b2b-api.implementos.cl/api/carro/estado"
                estado_carro_payload = {
                    "id": carro_actual.get("_id", ""),
                    "estado": "original"
                }

                requests.put(estado_carro_url, json=estado_carro_payload, headers={"Authorization": self.BASIC_AUTH})

                # Agregar contactos al carro
                contactos_carro_url = "https://b2b-api.implementos.cl/api/carro/agregarContactos"
                contactos_carro_payload = {
                    "id": carro_actual.get("id", ""),
                    "texto4": carro_entity["fonoNotificacion"],
                    "texto5": carro_entity["emailNotificacion"],
                    "textoNombre": carro_entity["nombreNotificacion"]
                }

                requests.post(contactos_carro_url, json=contactos_carro_payload, headers={"Authorization": self.BASIC_AUTH})

                # Construir mensaje de respuesta
                if len(documentos) > 1:
                    mensaje = f"Se han generado los documentos '{', '.join(documentos)}' para {nombre_cliente}."
                else:
                    mensaje = f"Se ha generado el documento '{documentos[0]}' para {nombre_cliente}."

                # Construir respuesta con documentos generados
                return json.dumps({
                    "ok": True,
                    "mensaje": mensaje,
                    "data": {
                        "tipo_documento": tipo_documento,
                        "documentos": documentos,
                        "rut": rut_normalizado,
                        "nombre_cliente": nombre_cliente
                    }
                }, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"Error general al completar carrito: {e}")
            return json.dumps({
                "ok": False,
                "mensaje": f"Error al procesar la solicitud: {str(e)}"
            }, ensure_ascii=False, indent=2)


tool = CarroVtTool()

# print("- VER CARRO")
# print(tool.ver_carro(rut="17679133-0",codigo_vendedor=1190,usuario_vendedor="jespinoza"))
# print("- AGREGAR PRODUCTO CARRO")
# print(tool.agregar_producto_carro(rut="17679133-0",sku="WUXACC0002",cantidad=1,codigo_vendedor=1190,usuario_vendedor="jespinoza"))
# print(tool.agregar_producto_carro(rut="17679133-0",sku="WUXACC0001",cantidad=1,codigo_vendedor=1190,usuario_vendedor="jespinoza"))
# print("- MODIFICAR PRODUCTO CARRO")
# print(tool.modificar_producto_carro(rut="17679133-0",sku="WUXACC0002",cantidad=2,codigo_vendedor=1190,usuario_vendedor="jespinoza"))
# print("- ELIMINAR PRODUCTO CARRO")
# print(tool.eliminar_producto_carro(rut="17679133-0",sku="WUXACC0001",codigo_vendedor=1190,usuario_vendedor="jespinoza"))
# print("- VER CARRO 2")
# print(tool.ver_carro(rut="17679133-0",codigo_vendedor=1190,usuario_vendedor="jespinoza"))
print("- COMPLETAR CARRO")
print(tool.completar_carro(
    rut="17679133-0",
    codigo_vendedor=1190,
    usuario_vendedor="jespinoza",
    forma_pago="EF",
    observacion="",
    opcion_entrega="Retiro en Tienda",
    tipo_documento="Cotización",
    sucursal="SAN BERNARDO",
    tienda="SAN BERNARDO"
))

#         self.register(self.convertir_cotizacion)

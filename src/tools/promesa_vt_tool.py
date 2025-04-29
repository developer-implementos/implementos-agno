import json
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime
from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger
from config.config import Config

class PromesaVtTool(Toolkit):
    def __init__(self):
        super().__init__(name="promesa_vt_tool")
        # Registrar las funciones en el toolkit
        self.register(self.obtener_localidades_promesa)
        self.register(self.consultar_promesa_sku)
        self.register(self.consultar_promesa_carro)
        
        # Mapeo de nombres de tiendas a códigos
        self.tiendas_map = {
            "ALTO HOSPICIO": "ALT HOSPIC",
            "ANTOFAGASTA": "ANTOFGASTA",
            "ARICA": "ARICA",
            "CALAMA": "CALAMA",
            "CASTRO": "CASTRO",
            "CHILLAN": "CHILLAN",
            "CON CON": "CON CON",
            "CONCEPCION": "CONCEPCION",
            "COPIAPO": "COPIAPO",
            "COQUIMBO": "COQUIMBO",
            "CORONEL": "CORONEL",
            "CURICO": "CURICO",
            "ESTACION CENTRAL": "EST CNTRAL",
            "IQUIQUE": "IQUIQUE",
            "LAMPA": "LAMPA",
            "LINARES": "LINARES",
            "LOS ANGELES": "LS ANGELES",
            "MELIPILLA": "MELIPILLA",
            "OSORNO": "OSORNO",
            "PUERTO MONTT": "P MONTT2",
            "PLACILLA": "PLACILLA",
            "PUNTA ARENAS": "PTA ARENAS",
            "RANCAGUA": "RANCAGUA",
            "SAN BERNARDO": "SAN BRNRDO",
            "SAN FERNANDO": "SAN FERNAN",
            "TALCA": "TALCA",
            "TEMUCO": "TEMUCO",
            "VALDIVIA": "VALDIVIA",
            "COLINA": "COLINA",
            "RANCAGUA 2": "RANCAGUA 2",
            "TALCAHUANO": "TALCAHUANO"
        }
        
    def obtener_localidades_promesa(self) -> str:
        """
        Función para obtener las localidades disponibles para la promesa de entrega
        
        Returns:
            str: Lista de localidades en formato JSON
        """
        try:
            url = "https://b2b-api.implementos.cl/api/promesa-entrega/localidades"
            
            headers = {
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                localidades = result.get("data", [])
                
                # Formatear las localidades para incluir el campo 'full'
                for localidad in localidades:
                    localidad["full"] = f"{localidad.get('nombre', '')} {localidad.get('region', '')}"
                
                log_debug(f"Se encontraron {len(localidades)} localidades disponibles")
                return json.dumps(localidades, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error en la solicitud a la API: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al obtener localidades para promesa: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def consultar_promesa_sku(self, sku: str, cantidad: int, localidad: str) -> str:
        """
        Función para consultar la promesa de entrega para un SKU específico con despacho a domicilio
        
        Args:
            sku (str): SKU del producto
            cantidad (int): Cantidad del producto
            localidad (str): Localidad o comuna para el despacho
            
        Returns:
            str: Información de la promesa de entrega en formato JSON
        """
        try:
            if not sku:
                log_debug("No se proporcionó SKU para consultar promesa")
                return json.dumps({"error": "Necesitas indicar el SKU del producto"}, ensure_ascii=False, indent=2)
            
            if not localidad:
                log_debug("No se proporcionó localidad para consultar promesa")
                return json.dumps({"error": "Necesitas indicar la localidad o comuna para el despacho"}, ensure_ascii=False, indent=2)
            
            # Obtener las localidades disponibles
            localidades_json = self.obtener_localidades_promesa()
            localidades = json.loads(localidades_json)
            
            # Si hay un error en obtener las localidades
            if "error" in localidades:
                return localidades_json
            
            # Buscar la localidad más cercana
            localidad_encontrada = self._detectar_objeto_cercano(localidad, localidades, ["full", "nombre"])
            
            if not localidad_encontrada:
                log_debug(f"No se encontró la localidad {localidad}")
                return json.dumps({"error": f"No se encontró la localidad {localidad}"}, ensure_ascii=False, indent=2)
            
            # Consultar la promesa de entrega usando el formato exacto de la URL
            url = f"https://b2b-api.implementos.cl/api/promesa-entrega/domicilio/{localidad_encontrada.get('nombre', '')}|{localidad_encontrada.get('codRegion', '')}"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            payload = {
                "omni": False,
                "bypassStock": "0",
                "bodegaDesdeCodigo": "",
                "multiProveedor": False,
                "productos": [
                    {
                        "sku": sku,
                        "cantidad": cantidad or 1
                    }
                ],
                "proveedorCodigo": "",
                "rut": "0",
                "stockSeguridad": False,
                "usarStockAX": True
            }
            
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                sub_ordenes = result.get("respuesta", [{}])[0].get("subOrdenes", [])
                
                if not sub_ordenes:
                    log_debug(f"No se encontraron fechas de entrega para SKU {sku} en {localidad}")
                    return json.dumps({"error": "No hay fechas para ofrecer 😔"}, ensure_ascii=False, indent=2)
                
                # Formatear las sub órdenes
                formatted_sub_ordenes = []
                for orden in sub_ordenes:
                    formatted_orden = {
                        "bodega": orden.get("bodega", ""),
                        "encontrado": True,
                        "fletes": orden.get("fletes", []),
                        "envio": orden.get("envio", ""),
                        "identificador": orden.get("identificador", ""),
                        "paraCalculo": orden.get("paraCalculo", ""),
                        "pesoTotal": orden.get("pesoTotal", 0),
                        "productosDespachar": orden.get("productosDespachar", []),
                        "tipoEnvioVenta": orden.get("tipoEnvioVenta", "")
                    }
                    formatted_sub_ordenes.append(formatted_orden)
                
                log_debug(f"Se encontraron {len(formatted_sub_ordenes)} sub órdenes para SKU {sku} en {localidad}")
                return json.dumps(formatted_sub_ordenes, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error en la solicitud a la API: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al consultar promesa para SKU {sku}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def consultar_promesa_carro(self, productos: List[Dict[str, Any]], tipo_entrega: str, lugar_entrega: str) -> str:
        """
        Función para consultar la promesa de entrega para un carro de productos
        
        Args:
            productos (List[Dict[str, Any]]): Lista de productos con formato [{"sku": "ABC123", "cantidad": 1}, ...]
            tipo_entrega (str): Tipo de entrega ("despacho" o "retiro")
            lugar_entrega (str): Lugar de entrega (localidad para despacho o tienda para retiro)
            
        Returns:
            str: Información de la promesa de entrega en formato JSON
        """
        try:
            if not productos or len(productos) == 0:
                log_debug("No se proporcionaron productos para consultar promesa")
                return json.dumps({"error": "Necesitas indicar los productos para consultar la promesa"}, ensure_ascii=False, indent=2)
            
            if not tipo_entrega:
                log_debug("No se proporcionó tipo de entrega para consultar promesa")
                return json.dumps({"error": "Necesitas indicar el tipo de entrega (despacho o retiro)"}, ensure_ascii=False, indent=2)
            
            if not lugar_entrega:
                log_debug("No se proporcionó lugar de entrega para consultar promesa")
                return json.dumps({"error": "Necesitas indicar el lugar de entrega (localidad o tienda)"}, ensure_ascii=False, indent=2)
            
            # Validar el tipo de entrega
            tipo_entrega = tipo_entrega.lower()
            if tipo_entrega not in ["despacho", "retiro"]:
                log_debug(f"Tipo de entrega no válido: {tipo_entrega}")
                return json.dumps({"error": "El tipo de entrega debe ser 'despacho' o 'retiro'"}, ensure_ascii=False, indent=2)
            
            # Validar la estructura de los productos
            for producto in productos:
                if "sku" not in producto or "cantidad" not in producto:
                    log_debug(f"Estructura de producto no válida: {producto}")
                    return json.dumps({"error": "Los productos deben tener la estructura: {'sku': '...', 'cantidad': ...}"}, ensure_ascii=False, indent=2)
            
            # Preparar el payload común para ambos tipos de entrega
            payload = {
                "omni": False,
                "bypassStock": "0",
                "bodegaDesdeCodigo": "",
                "multiProveedor": False,
                "productos": productos,
                "proveedorCodigo": "",
                "rut": "0",
                "stockSeguridad": False,
                "usarStockAX": True
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            if tipo_entrega == "despacho":
                # Despacho a domicilio
                # Obtener las localidades disponibles
                localidades_json = self.obtener_localidades_promesa()
                localidades = json.loads(localidades_json)
                
                # Si hay un error en obtener las localidades
                if "error" in localidades:
                    return localidades_json
                
                # Buscar la localidad más cercana
                localidad_encontrada = self._detectar_objeto_cercano(lugar_entrega, localidades, ["full", "nombre"])
                
                if not localidad_encontrada:
                    log_debug(f"No se encontró la localidad {lugar_entrega}")
                    return json.dumps({"error": f"No se encontró la localidad {lugar_entrega}"}, ensure_ascii=False, indent=2)
                
                # Consultar la promesa de entrega usando el formato exacto de la URL
                nombre_localidad = localidad_encontrada.get("nombre", "")
                codigo_region = localidad_encontrada.get("codRegion", "")
                url = f"https://b2b-api.implementos.cl/api/promesa-entrega/domicilio/{nombre_localidad}|{codigo_region}"
                
            else:
                # Retiro en tienda
                # Buscar la tienda correspondiente
                lugar_entrega_upper = lugar_entrega.upper()
                codigo_tienda = None
                
                # Buscar por código o nombre
                for nombre, codigo in self.tiendas_map.items():
                    if nombre == lugar_entrega_upper or codigo == lugar_entrega_upper:
                        codigo_tienda = codigo
                        break
                
                if not codigo_tienda:
                    log_debug(f"No se encontró la tienda {lugar_entrega}")
                    return json.dumps({"error": f"No se encontró la tienda {lugar_entrega}. Debe ser una de las tiendas válidas."}, ensure_ascii=False, indent=2)
                
                # Consultar la promesa de entrega usando el formato exacto de la URL
                url = f"https://b2b-api.implementos.cl/api/promesa-entrega/retiroTienda/{codigo_tienda}|"
            
            # Realizar la solicitud para cualquiera de los dos tipos
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                sub_ordenes = result.get("respuesta", [{}])[0].get("subOrdenes", [])
                
                if not sub_ordenes:
                    log_debug(f"No se encontraron fechas de entrega para los productos en {lugar_entrega}")
                    return json.dumps({"error": "No hay fechas para ofrecer 😔"}, ensure_ascii=False, indent=2)
                
                # Formatear las sub órdenes
                formatted_sub_ordenes = []
                for orden in sub_ordenes:
                    formatted_orden = {
                        "bodega": orden.get("bodega", ""),
                        "encontrado": True,
                        "fletes": orden.get("fletes", []),
                        "envio": orden.get("envio", ""),
                        "identificador": orden.get("identificador", ""),
                        "paraCalculo": orden.get("paraCalculo", ""),
                        "pesoTotal": orden.get("pesoTotal", 0),
                        "productosDespachar": orden.get("productosDespachar", []),
                        "tipoEnvioVenta": orden.get("tipoEnvioVenta", "")
                    }
                    formatted_sub_ordenes.append(formatted_orden)
                
                log_debug(f"Se encontraron {len(formatted_sub_ordenes)} sub órdenes para los productos en {lugar_entrega}")
                return json.dumps(formatted_sub_ordenes, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error en la solicitud a la API: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al consultar promesa para carro: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def _detectar_objeto_cercano(self, texto: str, lista_objetos: List[Dict[str, Any]], campos: List[str]) -> Optional[Dict[str, Any]]:
        """
        Función auxiliar para detectar el objeto más cercano en una lista
        
        Args:
            texto (str): Texto a buscar
            lista_objetos (List[Dict[str, Any]]): Lista de objetos donde buscar
            campos (List[str]): Campos de los objetos donde buscar
            
        Returns:
            Optional[Dict[str, Any]]: Objeto encontrado o None si no se encontró
        """
        try:
            texto_lower = texto.lower()
            mejor_puntuacion = 0
            mejor_objeto = None
            
            for objeto in lista_objetos:
                for campo in campos:
                    if campo in objeto and objeto[campo]:
                        valor_campo = str(objeto[campo]).lower()
                        
                        # Si el texto está completo en el valor del campo
                        if texto_lower in valor_campo:
                            puntuacion = len(texto_lower) / len(valor_campo)
                            if puntuacion > mejor_puntuacion:
                                mejor_puntuacion = puntuacion
                                mejor_objeto = objeto
                        
                        # Si el valor del campo está en el texto
                        elif valor_campo in texto_lower:
                            puntuacion = len(valor_campo) / len(texto_lower)
                            if puntuacion > mejor_puntuacion:
                                mejor_puntuacion = puntuacion
                                mejor_objeto = objeto
            
            return mejor_objeto
        except Exception as e:
            logger.warning(f"Error al detectar objeto cercano: {e}")
            return None
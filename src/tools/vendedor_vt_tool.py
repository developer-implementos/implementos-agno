import json
import requests
from pymongo import MongoClient
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger
from config.config import Config

class VendedorVtTool(Toolkit):
    def __init__(self):
        super().__init__(name="vendedor_vt_tool")
        # Registrar las funciones en el toolkit
        self.register(self.obtener_informacion_usuario)
        self.register(self.cumplimiento_meta_vendedor)
        self.register(self.pedidos_pendientes_vendedor)

    def obtener_informacion_usuario(self, codigo_vendedor: int) -> str:
        """
        Obtiene la información completa del usuario/vendedor
        
        Args:
            codigo_vendedor (int): Código del vendedor
            
        Returns:
            str: Información del usuario en formato JSON
        """
        try:
            client = MongoClient(Config.MONGO_IA)
            db = client.get_default_database()
            auth_info = db.agent_auth_info.find_one({"codigo_empleado": codigo_vendedor})
            
            if not auth_info:
                logger.warning(f"No se encontró información para el vendedor {codigo_vendedor}")
                return json.dumps({
                    "ok": False,
                    "mensaje": f"No se encontró información para el vendedor con código {codigo_vendedor}"
                }, ensure_ascii=False, indent=2)
            
            # Extraer la información requerida, incluyendo campos adicionales
            usuario_info = {
                "ok": True,
                "data": {
                    "codigo_empleado": auth_info.get("codigo_empleado", ""),
                    "vendedor_recid": auth_info.get("vendedor_recid", ""),
                    "rut": auth_info.get("rut", ""),
                    "usuario": auth_info.get("usuario", ""),
                    "nombre": auth_info.get("nombre", ""),
                    "token": auth_info.get("token", ""),
                    "email": auth_info.get("email", ""),
                    "movil": auth_info.get("movil", ""),
                    "ultimo_ingreso": auth_info.get("ultimo_ingreso", "")
                }
            }
            
            return json.dumps(usuario_info, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error al obtener información del usuario: {str(e)}")
            return json.dumps({
                "ok": False,
                "mensaje": f"Error al obtener información del usuario: {str(e)}"
            }, ensure_ascii=False, indent=2)
    
    def cumplimiento_meta_vendedor(self, fecha: str) -> str:
        """
        Función para obtener el cumplimiento de meta de un vendedor en una fecha específica
        
        Args:
            fecha (str): Fecha en formato YYYY-MM-DD para consultar la meta
            
        Returns:
            str: Información del cumplimiento de meta en formato JSON
        """
        try:
            if not fecha:
                log_debug("No se proporcionó fecha para consultar la meta")
                return json.dumps({"error": "Necesitas indicar la fecha a consultar la meta (de hoy, de ayer, etc.)"}, ensure_ascii=False, indent=2)
            
            url = "https://b2b-api.implementos.cl/api/mobile/obtenerDetalleVendedor"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            payload = {
                "rutVendedor": Config.RUT_VENDEDOR, # Usando un valor de configuración
                "fechaDetalle": fecha
            }
            
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                response_data = result[0] if result and len(result) > 0 else None
                
                if not response_data:
                    log_debug(f"No se encontró información para la fecha {fecha}")
                    return json.dumps({"error": "Lo siento, no encontré ninguna información"}, ensure_ascii=False, indent=2)
                
                # Calcular el cumplimiento como porcentaje
                cumplimiento = (response_data.get("venta", 0) / response_data.get("meta", 1)) * 100
                
                data = [{
                    "meta_mensual": response_data.get("meta", 0),
                    "meta_acumulada": response_data.get("metaAcumulada", 0),
                    "venta_total": response_data.get("venta", 0),
                    "cumplimiento": round(cumplimiento, 2),
                    "venta_cartera_objetivo": response_data.get("ventaCO", 0),
                    "venta_cartera_abierta": response_data.get("ventaCA", 0),
                    "documentos_emitidos": response_data.get("documentos", 0),
                    "clientes_atendidos": response_data.get("clienteCO", 0),
                    "sku_distintos": response_data.get("cantidadSKU", 0)
                }]
                
                log_debug(f"Cumplimiento de meta para la fecha {fecha} consultado correctamente")
                return json.dumps(data, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error en la solicitud: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
        
        except Exception as e:
            error_message = f"Error al consultar cumplimiento de meta para la fecha {fecha}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
    
    def pedidos_pendientes_vendedor(self, rut_vendedor: str, estados_pedido: List[str] = None) -> str:
        """
        Función para obtener los pedidos pendientes de un vendedor
        
        Args:
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
            
            rut_vendedor_clean = rut_vendedor.replace(".", "")
            
            # Calcular fechas para el rango de consulta
            fecha_hasta = datetime.now()
            fecha_desde = None
            
            if fecha_hasta.month > 2:
                fecha_desde = fecha_hasta.replace(day=1, month=fecha_hasta.month-2)
            else:
                mes = 10 + fecha_hasta.month
                fecha_desde = fecha_hasta.replace(day=1, month=mes, year=fecha_hasta.year-1)
                
            desde = fecha_desde.strftime("%Y%m%d")
            hasta = fecha_hasta.strftime("%Y%m%d")
            
            # Importante: No enviar el parámetro rut en los ruts de clientes
            url = f"https://replicacion.implementos.cl/ApiVendedor/api/vendedor/consultar-pedidos?rutVendedor={rut_vendedor_clean}&rutsClientes=0&desde={desde}&hasta={hasta}&tipo=0"
            
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
                        "rut_cliente": pedido.get("rutCliente"),
                        "nombre_cliente": pedido.get("nombreCliente"),
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
                
                log_debug(f"Se encontraron {len(mapped_data)} pedidos pendientes para el vendedor con RUT {rut_vendedor}")
                return json.dumps(result_data, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error en la solicitud a la API: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al consultar pedidos pendientes para el vendedor con RUT {rut_vendedor}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)
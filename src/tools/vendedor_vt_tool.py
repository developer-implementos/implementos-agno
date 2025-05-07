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
        self.register(self.obtener_documentos_vendedor)
        self.register(self.obtener_ventas_por_uen)
        self.register(self.obtener_resumen_dia_vendedor)

    def obtener_informacion_usuario(self, codigo_vendedor: int) -> str:
        """
        Obtiene los siguientes campos del vendedor para ser usados en otra tool:
        - rut: RUT del vendedor
        - nombre: Nombre completo
        - email: Email de contacto
        - movil: Número de celular
        - usuario: Nombre de usuario (nombre_usuario_vendedor)
        - vendedor_recid: ID interno del sistema

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
                    # "codigo_empleado": auth_info.get("codigo_empleado", ""),
                    "vendedor_recid": auth_info.get("vendedor_recid", ""),
                    "rut": auth_info.get("rut", ""),
                    "usuario": auth_info.get("usuario", ""),
                    "nombre": auth_info.get("nombre", ""),
                    # "token": auth_info.get("token", ""),
                    "email": auth_info.get("email", ""),
                    "movil": auth_info.get("movil", ""),
                }
            }

            return json.dumps(usuario_info, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error al obtener información del usuario: {str(e)}")
            return json.dumps({
                "ok": False,
                "mensaje": f"Error al obtener información del usuario: {str(e)}"
            }, ensure_ascii=False, indent=2)

    def cumplimiento_meta_vendedor(self, rut_vendedor: str, fecha: str) -> str:
        """
        Función para obtener el cumplimiento de meta de un vendedor en una fecha específica

        Args:
            rut_vendedor (str): RUT del vendedor
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
                "rutVendedor": rut_vendedor,
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
            estados_pedido (List[str], optional): Lista de estados de pedido para filtrar (POR_FACTURAR, FACTURA_POR_SINCRONIZAR, POR_VENCER, POR_CONVERTIR)

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

    def obtener_documentos_vendedor(self, rut_vendedor: str, fecha_inicio: str, fecha_fin: str = None) -> str:
        """
        Obtiene los documentos (facturas, cotizaciones) de un vendedor en un rango de fechas

        Args:
            rut_vendedor (str): RUT del vendedor
            fecha_inicio (str): Fecha de inicio en formato YYYY-MM-DD
            fecha_fin (str, optional): Fecha de fin en formato YYYY-MM-DD. Si no se proporciona, se utilizará el final del mes de fecha_inicio

        Returns:
            str: Información de los documentos en formato JSON
        """
        try:
            # Convertir fechas al formato requerido por la API
            fecha_inicio_obj = datetime.strptime(fecha_inicio, "%Y-%m-%d")

            if not fecha_fin:
                # Si no se proporciona fecha_fin, usar el último día del mes de fecha_inicio
                if fecha_inicio_obj.month == 12:
                    ultimo_dia = datetime(fecha_inicio_obj.year + 1, 1, 1) - timedelta(days=1)
                else:
                    ultimo_dia = datetime(fecha_inicio_obj.year, fecha_inicio_obj.month + 1, 1) - timedelta(days=1)
                fecha_fin = ultimo_dia.strftime("%Y-%m-%d")

            fecha_fin_obj = datetime.strptime(fecha_fin, "%Y-%m-%d")

            # Formatear fechas para la API
            fecha_inicio_api = fecha_inicio_obj.strftime("%Y-%m-%dT04:00:00.000Z")
            fecha_fin_api = (fecha_fin_obj + timedelta(days=1)).strftime("%Y-%m-%dT03:59:59.999Z")

            url = "https://b2b-api.implementos.cl/api/mobile/obtenerDocumentos"

            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }

            payload = {
                "rutVendedor": rut_vendedor,
                "fechainicio": fecha_inicio_api,
                "fechafin": fecha_fin_api
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                result = response.json()
                data = result.get("data", {})
                facturas_dia = result.get("factura_dia", [])

                # Formato de respuesta
                response_data = {
                    "resumen": {
                        "total_documentos": data.get("total", 0),
                        "total_facturas": data.get("totalfac", 0),
                        "monto_facturas": data.get("montofac", 0),
                        "documentos_sin_factura": data.get("sinfactura", 0),
                        "monto_sin_factura": data.get("montoSinFactura", 0),
                        "cotizaciones": data.get("cotizacion", 0),
                        "monto_cotizaciones": data.get("montoCotizacion", 0),
                        "promedio_documentos_por_dia": float(data.get("promedio_dia", 0)),
                        "monto_promedio_mes": float(data.get("monto_promedio_mes", 0)),
                        "documentos_dia": data.get("documentodia", 0),
                        "monto_promedio_dia": float(data.get("monto_promedio_dia", 0))
                    },
                    "cantidad_facturas_dia": len(facturas_dia),
                    "facturas_dia": [
                        {
                            "rut_cliente": factura.get("RutCliente", ""),
                            "nombre_cliente": factura.get("NOMBRECLIENTE", ""),
                            "orden_venta": factura.get("OV", ""),
                            "fecha": factura.get("Fecha", "").split("T")[0] if factura.get("Fecha") else "",
                            "estado": factura.get("ESTADO", ""),
                            "total_neto": factura.get("TotalNeto", 0),
                            "total_bruto": factura.get("Totalbruto", 0),
                            "tipo_cartera": factura.get("tipoCartera", "")
                        }
                        for factura in facturas_dia
                    ]
                }

                log_debug(
                    f"Se consultaron documentos para el vendedor con RUT {rut_vendedor} desde {fecha_inicio} hasta {fecha_fin}")
                return json.dumps(response_data, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error en la solicitud a la API: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)

        except Exception as e:
            error_message = f"Error al consultar documentos para el vendedor con RUT {rut_vendedor}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)

    def obtener_ventas_por_uen(self, rut_vendedor: str, fecha: str = None) -> str:
        """
        Obtiene las ventas de un vendedor clasificadas por UEN (Unidad Estratégica de Negocio)

        Args:
            rut_vendedor (str): RUT del vendedor
            fecha (str, optional): Fecha en formato YYYY-MM-DD para consultar las ventas. Si no se proporciona, se utiliza la fecha actual

        Returns:
            str: Información de ventas por UEN en formato JSON
        """
        try:
            if not fecha:
                fecha = datetime.now().strftime("%Y-%m-%d")

            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d")
            fecha_api = fecha_obj.strftime("%Y-%m-%dT04:00:00.000Z")

            url = "https://b2b-api.implementos.cl/api/mobile/obtenerVentasVendedorUENmes"

            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }

            payload = {
                "rutVendedor": rut_vendedor,
                "fechaDetalle": fecha_api
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                result = response.json()

                # Calcular total de ventas
                total_ventas = sum(item.get("value", 0) for item in result)

                # Calcular porcentaje de cada UEN
                for item in result:
                    item["porcentaje"] = round((item.get("value", 0) / total_ventas * 100 if total_ventas > 0 else 0),
                                               2)

                # Ordenar por valor de venta (de mayor a menor)
                result.sort(key=lambda x: x.get("value", 0), reverse=True)

                response_data = {
                    "total_ventas": total_ventas,
                    "cantidad_uens": len(result),
                    "ventas_por_uen": [
                        {
                            "categoria": item.get("name", ""),
                            "monto": item.get("value", 0),
                            "porcentaje": item.get("porcentaje", 0)
                        }
                        for item in result
                    ]
                }

                log_debug(f"Se consultaron ventas por UEN para el vendedor con RUT {rut_vendedor} en la fecha {fecha}")
                return json.dumps(response_data, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error en la solicitud a la API: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)

        except Exception as e:
            error_message = f"Error al consultar ventas por UEN para el vendedor con RUT {rut_vendedor}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)

    def obtener_resumen_dia_vendedor(self, rut_vendedor: str, fecha: str = None) -> str:
        """
        Obtiene un informe resumido del desempeño de un vendedor en un día, incluyendo metas, ventas y otros indicadores

        Args:
            rut_vendedor (str): RUT del vendedor
            fecha (str, optional): Fecha en formato YYYY-MM-DD para consultar la información. Si no se proporciona, se utiliza la fecha actual

        Returns:
            str: Información detallada del vendedor en formato JSON
        """
        try:
            if not fecha:
                fecha = datetime.now().strftime("%Y-%m-%d")

            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d")
            fecha_api = fecha_obj.strftime("%Y-%m-%dT04:00:00.000Z")

            url = "https://b2b-api.implementos.cl/api/mobile/obtenerDetalleVendedor"

            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }

            payload = {
                "rutVendedor": rut_vendedor,
                "fechaDetalle": fecha_api
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                result = response.json()
                detalle = result[0] if result and len(result) > 0 else None

                if not detalle:
                    log_debug(f"No se encontró información para la fecha {fecha}")
                    return json.dumps({"error": "No se encontró información para la fecha especificada"},
                                      ensure_ascii=False, indent=2)

                # Calcular porcentajes de cumplimiento
                cumplimiento_mes = (detalle.get("venta", 0) / detalle.get("meta", 1)) * 100 if detalle.get("meta",
                                                                                                           0) > 0 else 0
                cumplimiento_dia = (detalle.get("ventaMetaDia", 0) / detalle.get("metaDia", 1)) * 100 if detalle.get(
                    "metaDia", 0) > 0 else 0
                cumplimiento_acumulado = (detalle.get("ventaMetaAcumulada", 0) / detalle.get("metaAcumulada",
                                                                                             1)) * 100 if detalle.get(
                    "metaAcumulada", 0) > 0 else 0

                response_data = {
                    "informacion_vendedor": {
                        "codigo": detalle.get("codVendedor", ""),
                        "rut": detalle.get("rutVendedor", ""),
                        "nombre": detalle.get("nombreVendedor", ""),
                        "zona": detalle.get("zona", "")
                    },
                    "periodo": {
                        "año": detalle.get("anno", 0),
                        "mes": detalle.get("mes", 0)
                    },
                    "metas": {
                        "meta_mensual": detalle.get("meta", 0),
                        "meta_diaria": detalle.get("metaDia", 0),
                        "meta_acumulada": detalle.get("metaAcumulada", 0)
                    },
                    "ventas": {
                        "venta_total": detalle.get("venta", 0),
                        "venta_cartera_objetivo": detalle.get("ventaCO", 0),
                        "venta_cartera_abierta": detalle.get("ventaCA", 0),
                        "venta_dia_cartera_objetivo": detalle.get("ventaDiaCO", 0),
                        "venta_dia_cartera_abierta": detalle.get("ventaDiaCA", 0),
                        "venta_meta_dia": detalle.get("ventaMetaDia", 0),
                        "venta_meta_acumulada": detalle.get("ventaMetaAcumulada", 0)
                    },
                    "cumplimiento": {
                        "cumplimiento_mensual": round(cumplimiento_mes, 2),
                        "cumplimiento_diario": round(cumplimiento_dia, 2),
                        "cumplimiento_acumulado": round(cumplimiento_acumulado, 2),
                        "diferencia_meta_dia": detalle.get("difMetaDia", 0)
                    },
                    "indicadores": {
                        "detalles": detalle.get("detalles", 0),
                        "detalles_promedio": detalle.get("detallesProm", 0),
                        "documentos": detalle.get("documentos", 0),
                        "documentos_dia": detalle.get("documentosDia", 0),
                        "documentos_sin_factura": detalle.get("documentosSinFact", 0),
                        "total_clientes_cartera_objetivo": detalle.get("totalCO", 0),
                        "clientes_dia": detalle.get("clienteDia", 0),
                        "clientes_cartera_objetivo": detalle.get("clienteCO", 0),
                        "clientes_cartera_objetivo_dia": detalle.get("clienteCODia", 0),
                        "cantidad_sku": detalle.get("cantidadSKU", 0)
                    },
                    "actividades": {
                        "visitas_creadas": detalle.get("VisitasCreadas", 0),
                        "visitas_creadas_mes": detalle.get("VisitasCreadasMes", 0),
                        "visitas_confirmadas": detalle.get("VisitasConfirmadas", 0),
                        "visitas_confirmadas_mes": detalle.get("VisitasConfirmadasMes", 0),
                        "cotizaciones_creadas": detalle.get("CotizacionesCreadas", 0),
                        "cotizaciones_creadas_mes": detalle.get("CotizacionesCreadasMes", 0),
                        "clientes_con_visita": detalle.get("ClientescVisita", 0)
                    }
                }

                log_debug(f"Se consultaron detalles para el vendedor con RUT {rut_vendedor} en la fecha {fecha}")
                return json.dumps(response_data, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error en la solicitud a la API: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)

        except Exception as e:
            error_message = f"Error al consultar detalles para el vendedor con RUT {rut_vendedor}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)

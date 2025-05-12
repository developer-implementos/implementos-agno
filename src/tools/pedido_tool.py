import json
import requests
from typing import List, Dict, Any, Optional, Union
from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger
from config.config import Config
import base64
from datetime import datetime
import re
from urllib.parse import quote

from utils.obtener_token_omni_vendedor import obtener_token_omni_vendedor


class PedidoTool(Toolkit):
    def __init__(self):
        super().__init__(name="pedido_tool")
        # Registrar las funciones en el toolkit
        self.register(self.obtener_informacion_pedido)
        self.register(self.obtener_contactos_correo)
        self.register(self.obtener_contactos_celular)
        self.register(self.enviar_pedido_notificacion)
        self.register(self.obtener_pdf_pedido)

        # Constante de autenticación
        self.BASIC_AUTH = "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"

        # Mapeo de tipos de documentos
        self.TIPOS_DOCUMENTOS = {
            "nota-venta": "OV",
            "cotizacion": "CO",
            "factura": "FEL",
            "boleta": "BEL",
            "nota-credito": "NCE",
            "nota-debito": "NDE",
            "guia": "GDEL"
        }

        # Mapeo inverso para nombres legibles
        self.TIPOS_NOMBRES = {
            "OV": "Nota de Venta",
            "CO": "Cotización",
            "FEL": "Factura",
            "BEL": "Boleta",
            "NCE": "Nota de Crédito",
            "NDE": "Nota de Débito",
            "GDEL": "Guía de Despacho"
        }

        # Mapeo de códigos para descarga de PDF
        self.FOLIOS_CODIGOS = {
            "FEL": 33,
            "BEL": 39,
            "GDEL": 52,
            "NCE": 61,
            "NDE": 56
        }

    def obtener_informacion_pedido(self, tipo: str, folio: str) -> str:
        """
        Obtiene la información detallada de un pedido

        Args:
            tipo (str): Tipo de documento (nota-venta, cotizacion, factura, boleta, nota-credito, guia)
            folio (str): Número de folio del documento

        Returns:
            str: Información del pedido en formato JSON
        """
        try:
            # Normalizar el folio según el tipo
            folio = self._normalizar_folio(folio, tipo)

            # Obtener el tipo en formato API
            tipo_api = self.TIPOS_DOCUMENTOS.get(tipo)
            if not tipo_api:
                return json.dumps({
                    "ok": False,
                    "mensaje": f"Tipo de documento no válido: {tipo}"
                }, ensure_ascii=False, indent=2)

            # Consultar datos del pedido
            datos_pedido = self._obtener_datos_pedido(folio, tipo_api)

            if not datos_pedido or not datos_pedido.get("folio"):
                return json.dumps({
                    "ok": False,
                    "mensaje": f"No se encontró el documento con folio {folio}"
                }, ensure_ascii=False, indent=2)

            # Construir la respuesta base
            result = {
                "ok": True,
                "tipo": self.TIPOS_NOMBRES.get(datos_pedido.get("tipo", tipo_api), "Documento"),
                "folio": datos_pedido.get("folio"),
                "rut_cliente": datos_pedido.get("rutCliente"),
                "nombre_cliente": datos_pedido.get("nombreCliente"),
                "fecha_documento": datos_pedido.get("fechaDocumento"),
                "estado": datos_pedido.get("estado"),
                "total_neto": datos_pedido.get("totalNeto"),
                "iva": datos_pedido.get("iva"),
                "total": datos_pedido.get("total"),
                "detalle": datos_pedido.get("detalle", []),
                "meta": {
                    "tipo": datos_pedido.get("tipo"),
                    "folio": datos_pedido.get("folio"),
                    "ov": datos_pedido.get("notaVentaAfectada"),
                    "tipo_afectado": datos_pedido.get("tipoAfectado"),
                    "folio_afectado": datos_pedido.get("folioAfectado")
                }
            }

            # Si es una nota de venta, obtener datos adicionales
            if tipo == "nota-venta" or tipo_api == "OV":
                datos_ov = self._obtener_datos_ov(folio)
                if datos_ov and not datos_ov.get("error"):
                    # Agregar información adicional de la OV
                    result.update({
                        "fecha_picking": datos_ov.get("FechaPicking"),
                        "fecha_compromiso": datos_ov.get("FechaCompromisoCliente"),
                        "canal": datos_ov.get("NombreCanal"),
                        "direccion_despacho": datos_ov.get("DireccionDespacho", "").replace("\n", " "),
                        "modo_entrega": datos_ov.get("modoEntregaNom"),
                        "formas_pago": [fp.get("FormaPagoNombre") for fp in datos_ov.get("FormasPagoReal", [])],
                        "origenes_stock": datos_ov.get("codigosSalida", []),
                        "rut_vendedor": datos_ov.get("RutVendedor"),
                        "vendedor": datos_ov.get("Venedor"),  # Mantiene el error de escritura del original
                        "transportista": datos_ov.get("transportista"),
                        "facturado_caja": any(x.get("PorCaja") for x in datos_ov.get("facturacionCaja", [])),
                        "estado_tracking": datos_ov.get("estadoOV"),
                        "estados": datos_ov.get("estados", []),
                        "notificaciones": datos_ov.get("notificaciones", [])
                    })

                    # Agregar documentos asociados a la meta
                    documentos = self._obtener_documentos_ov(datos_ov)
                    result["meta"]["documentos"] = documentos

            log_debug(f"Se obtuvo información para el documento {tipo_api}-{folio}")
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)

        except Exception as e:
            error_message = f"Error al obtener información del pedido: {e}"
            logger.warning(error_message)
            return json.dumps({
                "ok": False,
                "mensaje": error_message
            }, ensure_ascii=False, indent=2)

    def obtener_contactos_correo(self, rut: str, cod_vendedor: int) -> str:
        """
        Obtiene los contactos con correo electrónico de un cliente

        Args:
            rut (str): RUT del cliente
            cod_vendedor (int): Código del vendedor para autenticación

        Returns:
            str: Resultado de la operación en formato JSON con los contactos
        """
        try:
            # Obtener token de autenticación
            token = obtener_token_omni_vendedor(cod_vendedor=cod_vendedor)
            if not token:
                return json.dumps({
                    "ok": False,
                    "mensaje": "No se pudo obtener la autenticación del vendedor."
                }, ensure_ascii=False, indent=2)

            # Obtener todos los contactos del cliente
            contactos_cliente = self._obtener_contactos_cliente(rut, token)
            if not contactos_cliente or len(contactos_cliente) == 0:
                return json.dumps({
                    "ok": False,
                    "mensaje": f"No se encontraron contactos para el cliente con RUT {rut}"
                }, ensure_ascii=False, indent=2)

            # Filtrar contactos con correo electrónico
            contactos_correo = [c for c in contactos_cliente if c.get("emails") and len(c.get("emails", [])) > 0]
            if not contactos_correo or len(contactos_correo) == 0:
                return json.dumps({
                    "ok": False,
                    "mensaje": f"No se encontraron contactos con correo electrónico para el cliente con RUT {rut}"
                }, ensure_ascii=False, indent=2)

            # Formatear la respuesta
            contactos_formateados = []
            for contacto in contactos_correo:
                emails = []
                for email in contacto.get("emails", []):
                    emails.append({
                        "valor": email.get("valor", ""),
                        "tipo": email.get("tipo", ""),
                        "principal": email.get("principal", False)
                    })

                contactos_formateados.append({
                    "id": contacto.get("id", ""),
                    "nombre": contacto.get("nombre", ""),
                    "cargo": contacto.get("cargo", ""),
                    "tipo": contacto.get("tipo", ""),
                    "departamento": contacto.get("departamento", ""),
                    "emails": emails
                })

            log_debug(f"Se obtuvieron {len(contactos_formateados)} contactos con correo para el cliente {rut}")
            return json.dumps({
                "ok": True,
                "mensaje": f"Contactos con correo obtenidos correctamente para el cliente {rut}",
                "data": {
                    "rut_cliente": rut,
                    "contactos": contactos_formateados
                }
            }, ensure_ascii=False, indent=2)

        except Exception as e:
            error_message = f"Error al obtener contactos con correo: {e}"
            logger.warning(error_message)
            return json.dumps({
                "ok": False,
                "mensaje": error_message
            }, ensure_ascii=False, indent=2)

    def obtener_contactos_celular(self, rut: str, cod_vendedor: int) -> str:
        """
        Obtiene los contactos con número de celular de un cliente

        Args:
            rut (str): RUT del cliente
            cod_vendedor (int): Código del vendedor para autenticación

        Returns:
            str: Resultado de la operación en formato JSON con los contactos
        """
        try:
            # Obtener token de autenticación
            token = obtener_token_omni_vendedor(cod_vendedor=cod_vendedor)
            if not token:
                return json.dumps({
                    "ok": False,
                    "mensaje": "No se pudo obtener la autenticación del vendedor."
                }, ensure_ascii=False, indent=2)

            # Obtener todos los contactos del cliente
            contactos_cliente = self._obtener_contactos_cliente(rut, token)
            if not contactos_cliente or len(contactos_cliente) == 0:
                return json.dumps({
                    "ok": False,
                    "mensaje": f"No se encontraron contactos para el cliente con RUT {rut}"
                }, ensure_ascii=False, indent=2)

            # Filtrar contactos con teléfono celular
            contactos_celular = [c for c in contactos_cliente if c.get("telefonos") and len(c.get("telefonos", [])) > 0]
            if not contactos_celular or len(contactos_celular) == 0:
                return json.dumps({
                    "ok": False,
                    "mensaje": f"No se encontraron contactos con número de celular para el cliente con RUT {rut}"
                }, ensure_ascii=False, indent=2)

            # Formatear la respuesta
            contactos_formateados = []
            for contacto in contactos_celular:
                telefonos = []
                for telefono in contacto.get("telefonos", []):
                    telefonos.append({
                        "valor": telefono.get("valor", ""),
                        "tipo": telefono.get("tipo", ""),
                        "principal": telefono.get("principal", False)
                    })

                contactos_formateados.append({
                    "id": contacto.get("id", ""),
                    "nombre": contacto.get("nombre", ""),
                    "cargo": contacto.get("cargo", ""),
                    "tipo": contacto.get("tipo", ""),
                    "departamento": contacto.get("departamento", ""),
                    "telefonos": telefonos
                })

            log_debug(f"Se obtuvieron {len(contactos_formateados)} contactos con celular para el cliente {rut}")
            return json.dumps({
                "ok": True,
                "mensaje": f"Contactos con celular obtenidos correctamente para el cliente {rut}",
                "data": {
                    "rut_cliente": rut,
                    "contactos": contactos_formateados
                }
            }, ensure_ascii=False, indent=2)

        except Exception as e:
            error_message = f"Error al obtener contactos con celular: {e}"
            logger.warning(error_message)
            return json.dumps({
                "ok": False,
                "mensaje": error_message
            }, ensure_ascii=False, indent=2)

    def enviar_pedido_notificacion(
        self,
        tipo: str,
        folio: str,
        canal: str,
        contactos: List[str],
        cod_vendedor: int
    ) -> str:
        """
        Envía una notificación de un pedido por correo o WhatsApp

        Args:
            tipo (str): Tipo de documento (nota-venta, cotizacion)
            folio (str): Número de folio del documento
            canal (str): Canal de notificación (correo, whatsapp)
            contactos (List[str]): Lista de identificadores de contactos o descripciones
            cod_vendedor (int): Código del vendedor

        Returns:
            str: Resultado de la operación en formato JSON
        """
        try:
            token = obtener_token_omni_vendedor(cod_vendedor=cod_vendedor)
            # Validar tipo de documento
            if tipo not in ["nota-venta", "cotizacion"]:
                return json.dumps({
                    "ok": False,
                    "mensaje": "Solo se pueden enviar notificaciones de notas de venta y cotizaciones"
                }, ensure_ascii=False, indent=2)

            # Validar canal
            if canal not in ["correo", "whatsapp"]:
                return json.dumps({
                    "ok": False,
                    "mensaje": "El canal debe ser 'correo' o 'whatsapp'"
                }, ensure_ascii=False, indent=2)

            # Normalizar el folio
            folio = self._normalizar_folio(folio, tipo)

            # Obtener el tipo en formato API
            tipo_api = self.TIPOS_DOCUMENTOS.get(tipo)

            # Consultar datos del pedido para obtener información del cliente
            datos_pedido = self._obtener_datos_pedido(folio, tipo_api)

            if not datos_pedido or not datos_pedido.get("folio"):
                return json.dumps({
                    "ok": False,
                    "mensaje": f"No se encontró el documento con folio {folio}"
                }, ensure_ascii=False, indent=2)

            # Obtener contactos del cliente
            rut_cliente = datos_pedido.get("rutCliente")
            contactos_cliente = self._obtener_contactos_cliente(rut_cliente, token)

            if not contactos_cliente or len(contactos_cliente) == 0:
                return json.dumps({
                    "ok": False,
                    "mensaje": f"No se encontraron contactos para el cliente con RUT {rut_cliente}"
                }, ensure_ascii=False, indent=2)

            # Filtrar contactos según el canal
            if canal == "correo":
                contactos_disponibles = [c for c in contactos_cliente if c.get("emails") and len(c.get("emails", [])) > 0]
            else:  # whatsapp
                contactos_disponibles = [c for c in contactos_cliente if c.get("telefonos") and len(c.get("telefonos", [])) > 0]

            if not contactos_disponibles or len(contactos_disponibles) == 0:
                return json.dumps({
                    "ok": False,
                    "mensaje": f"No se encontraron contactos con {canal} para el cliente con RUT {rut_cliente}"
                }, ensure_ascii=False, indent=2)

            # Seleccionar contactos para notificar
            contactos_notificar = []
            for contacto_desc in contactos:
                contacto_encontrado = self._encontrar_contacto(contacto_desc, contactos_disponibles)
                if contacto_encontrado:
                    contactos_notificar.append(contacto_encontrado)

            if not contactos_notificar or len(contactos_notificar) == 0:
                return json.dumps({
                    "ok": False,
                    "mensaje": "No se pudieron identificar los contactos proporcionados"
                }, ensure_ascii=False, indent=2)

            # Preparar destinatarios
            if canal == "correo":
                destinatarios = [c.get("emails", [{}])[0].get("valor") for c in contactos_notificar if c.get("emails")]
            else:  # whatsapp
                destinatarios = [c.get("telefonos", [{}])[0].get("valor") for c in contactos_notificar if c.get("telefonos")]

            # Eliminar duplicados
            destinatarios = list(set(destinatarios))

            # Obtener IDs de contactos
            id_contactos = [c.get("id") for c in contactos_notificar]

            # Enviar notificación
            url = f"https://b2b-api.implementos.cl/api/carro/mailWhatsappNotificacionOmni/{folio}/{canal}"

            headers = {
                "Content-Type": "application/json",
                "Authorization": self.BASIC_AUTH
            }

            payload = {
                "destinatarios": ",".join(destinatarios),
                "idContactos": id_contactos,
                "cc": "",
                "vendedor": {
                    "rut": "",
                    "codEmpleado": 0,
                    "codUsuario": 0,
                    "nombre": "",
                    "correo": "",
                    "telefono": ""
                }
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                log_debug(f"Notificación enviada exitosamente para {folio} por {canal}")
                return json.dumps({
                    "ok": True,
                    "mensaje": f"{folio} enviado exitosamente por {canal}",
                    "meta": {
                        "folio": folio,
                        "canal": canal,
                        "destinatarios": ",".join(destinatarios),
                        "id_contactos": id_contactos
                    }
                }, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error al enviar notificación: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({
                    "ok": False,
                    "mensaje": error_message
                }, ensure_ascii=False, indent=2)

        except Exception as e:
            error_message = f"Error al enviar notificación del pedido: {e}"
            logger.warning(error_message)
            return json.dumps({
                "ok": False,
                "mensaje": error_message
            }, ensure_ascii=False, indent=2)

    def obtener_pdf_pedido(self, tipo: str, folio: str) -> str:
        """
        Obtiene el PDF de un pedido

        Args:
            tipo (str): Tipo de documento (nota-venta, cotizacion, factura, boleta, nota-credito, guia)
            folio (str): Número de folio del documento

        Returns:
            str: URL y nombre del archivo
        """
        try:
            # Normalizar el folio
            folio = self._normalizar_folio(folio, tipo)

            # Obtener el tipo en formato API
            tipo_api = self.TIPOS_DOCUMENTOS.get(tipo)
            if not tipo_api:
                return json.dumps({
                    "ok": False,
                    "mensaje": f"Tipo de documento no válido: {tipo}"
                }, ensure_ascii=False, indent=2)

            # Construir URL según el tipo de documento
            url = None
            if tipo_api in ["OV", "CO"]:
                url = f"https://b2b-api.implementos.cl/api/carro/documentos/documentoOVPDF/{self._generar_codigo_documento(folio)}"
            else:
                codigo_tipo = self.FOLIOS_CODIGOS.get(tipo_api)
                if not codigo_tipo:
                    return json.dumps({
                        "ok": False,
                        "mensaje": f"No se puede generar PDF para el tipo de documento {tipo}"
                    }, ensure_ascii=False, indent=2)

                url = f"https://b2b-api.implementos.cl/api/carro/documentos/documentoClientePDF/{self._generar_codigo_documento(folio, codigo_tipo)}"

            filename = f"{folio}.pdf"

            result = {
                "url": url,
                "filename": filename
            }

            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            error_message = f"Error al obtener PDF del pedido: {e}"
            logger.warning(error_message)
            return json.dumps({
                "ok": False,
                "mensaje": error_message
            }, ensure_ascii=False, indent=2)

    def _normalizar_folio(self, folio: str, tipo: str) -> str:
        """
        Normaliza el formato del folio según el tipo de documento

        Args:
            folio (str): Folio original
            tipo (str): Tipo de documento

        Returns:
            str: Folio normalizado
        """
        folio = str(folio).upper()

        if tipo == "nota-venta" and not folio.startswith("OV"):
            return f"OV-{folio}"
        elif tipo == "cotizacion" and not folio.startswith("CO"):
            return f"CO-{folio}"
        elif tipo in ["factura", "boleta", "nota-credito", "nota-debito", "guia"]:
            # Remover prefijos si existen
            return folio.replace("FEL-", "").replace("BEL-", "").replace("NCE-", "").replace("NDE-", "").replace("GDEL-", "")

        return folio

    def _obtener_datos_pedido(self, folio: str, tipo: str) -> Dict[str, Any]:
        """
        Obtiene los datos de un pedido desde la API

        Args:
            folio (str): Folio del documento
            tipo (str): Tipo de documento en formato API

        Returns:
            Dict[str, Any]: Datos del pedido o None si no se encuentra
        """
        url = f"https://replicacion.implementos.cl/ApiVendedor/api/vendedor/consultar-pedido?folio={folio}&tipo={tipo}"

        try:
            response = requests.get(url)

            if response.status_code == 200:
                result = response.json()
                return result.get("data", {})
            else:
                logger.warning(f"Error al obtener datos del pedido: {response.status_code} - {response.text}")
                return {}
        except Exception as e:
            logger.warning(f"Error en la petición de datos del pedido: {e}")
            return {}

    def _obtener_datos_ov(self, folio: str) -> Dict[str, Any]:
        """
        Obtiene datos adicionales de una orden de venta

        Args:
            folio (str): Folio de la OV

        Returns:
            Dict[str, Any]: Datos adicionales de la OV
        """
        if not folio.startswith("OV"):
            folio = f"OV-{folio}"

        url = f"https://b2b-api.implementos.cl/api/oms/ordenes-venta/listadoFiltrado/{folio}"

        try:
            response = requests.get(url, headers={"Authorization": self.BASIC_AUTH})

            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Error al obtener datos adicionales de la OV: {response.status_code} - {response.text}")
                return {}
        except Exception as e:
            logger.warning(f"Error en la petición de datos adicionales de la OV: {e}")
            return {}

    def _obtener_contactos_cliente(self, rut: str, token: str) -> List[Dict[str, Any]]:
        """
        Obtiene los contactos de un cliente

        Args:
            rut (str): RUT del cliente
            token (str): Token de autenticación

        Returns:
            List[Dict[str, Any]]: Lista de contactos del cliente
        """
        url = f"https://replicacion.implementos.cl/apiOmnichannel/api/cliente/contactos?rut={rut}"

        try:
            response = requests.get(url, headers={"Authorization": f"Bearer {token}"})

            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Error al obtener contactos del cliente: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            logger.warning(f"Error en la petición de contactos del cliente: {e}")
            return []

    def _encontrar_contacto(self, descripcion: str, contactos: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Busca un contacto por su descripción en la lista de contactos

        Args:
            descripcion (str): Descripción del contacto (nombre, cargo, email, etc.)
            contactos (List[Dict[str, Any]]): Lista de contactos disponibles

        Returns:
            Optional[Dict[str, Any]]: Contacto encontrado o None
        """
        descripcion = descripcion.lower()

        # Primero buscar coincidencia exacta por ID
        for contacto in contactos:
            if contacto.get("id") == descripcion:
                return contacto

        # Buscar coincidencia por nombre
        for contacto in contactos:
            nombre = contacto.get("nombre", "").lower()
            if descripcion in nombre or nombre in descripcion:
                return contacto

            # Buscar en email
            for email in contacto.get("emails", []):
                if descripcion in email.get("valor", "").lower():
                    return contacto

            # Buscar en teléfono
            for telefono in contacto.get("telefonos", []):
                if descripcion in telefono.get("valor", "").lower():
                    return contacto

            # Buscar en cargo
            cargo = contacto.get("cargo", "").lower()
            if descripcion in cargo or cargo in descripcion:
                return contacto

        # Si no hay coincidencias, devolver el primer contacto como fallback
        return contactos[0] if contactos else None

    def _obtener_documentos_ov(self, datos_ov: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extrae los documentos asociados a una OV

        Args:
            datos_ov (Dict[str, Any]): Datos de la OV

        Returns:
            List[Dict[str, Any]]: Lista de documentos asociados
        """
        documentos = []

        # Extraer guías de despacho de los estados
        guias = [e for e in datos_ov.get("estados", []) if "GUIA" in e.get("SubEstado", "") and e.get("CodigoSeguimiento") == 11]
        for guia in guias:
            if guia.get("FolioDoc"):
                documentos.append({
                    "tipo": "GDEL",
                    "tipo_nombre": "Guía de Despacho",
                    "folio": guia.get("FolioDoc")
                })

        # Extraer facturas/boletas de facturacionCaja
        for factura in datos_ov.get("facturacionCaja", []):
            documentos.append({
                "tipo": factura.get("Tipo"),
                "tipo_nombre": self.TIPOS_NOMBRES.get(factura.get("Tipo"), factura.get("Tipo")),
                "folio": factura.get("Documento")
            })

        # Extraer notas de crédito
        for nc in datos_ov.get("notasCredito", []):
            if nc.get("FolioNc"):
                documentos.append({
                    "tipo": "NCE",
                    "tipo_nombre": "Nota de Crédito",
                    "folio": nc.get("FolioNc")
                })

        # Extraer cotizaciones
        cotizaciones = [doc for doc in datos_ov.get("documentos", []) if doc.get("tipo") == "COTIZACION"]
        for co in cotizaciones:
            if co.get("folio"):
                documentos.append({
                    "tipo": "CO",
                    "tipo_nombre": "Cotización",
                    "folio": co.get("folio")
                })

        # Extraer estados con documentos (como facturas)
        estados_factura = [e for e in datos_ov.get("estados", []) if e.get("FolioDoc") and "FACTURA" in e.get("SubEstado", "") and e.get("CodigoSeguimiento") == 13]
        for estado in estados_factura:
            # Verificar si ya existe para evitar duplicados
            if not any(doc.get("tipo") == "FEL" and doc.get("folio") == estado.get("FolioDoc") for doc in documentos):
                documentos.append({
                    "tipo": "FEL",
                    "tipo_nombre": "Factura",
                    "folio": estado.get("FolioDoc")
                })

        return documentos

    def _generar_codigo_documento(self, folio: str, codigo_tipo: Optional[int] = None) -> str:
        """
        Genera el código para la URL de descarga de un documento

        Args:
            folio (str): Folio del documento
            codigo_tipo (Optional[int]): Código del tipo de documento

        Returns:
            str: Código codificado en base64
        """
        if codigo_tipo:
            codigo = f"@{folio}@{codigo_tipo}@"
        else:
            codigo = f"@{folio}@"

        # Codificar en base64
        codigo_b64 = base64.b64encode(codigo.encode('utf-8')).decode('utf-8')

        # URL encode
        return quote(codigo_b64)

    def _get_filename_from_header(self, header: Optional[str]) -> Optional[str]:
        """
        Extrae el nombre del archivo de la cabecera Content-Disposition

        Args:
            header (Optional[str]): Cabecera Content-Disposition

        Returns:
            Optional[str]: Nombre del archivo o None si no se encuentra
        """
        if not header:
            return None

        filename_match = re.search(r'filename[^;=\n]*=(([\'"]).*?\2|[^;\n]*)', header)
        if filename_match and filename_match.group(1):
            return filename_match.group(1).replace('"', '').replace("'", "")

        return None

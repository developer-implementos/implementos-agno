import json
import requests
from urllib.parse import quote
from typing import List, Dict, Any, Optional, Union
from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger
from config.config import Config
from pymongo import MongoClient
import io
import base64
from datetime import datetime
from models.propuesta_model import ObtenerProductosPropuestaResponse, Articulo, PropuestaCliente

class PropuestaTool(Toolkit):
    def __init__(self):
        super().__init__(name="propuesta_tool")
        # Registrar las funciones en el toolkit
        self.register(self.obtener_propuestas)
        self.register(self.obtener_propuesta)
        self.register(self.generar_propuesta)
        self.register(self.generar_catalogo_propuesta)
        self.register(self.obtener_pdf_catalogo)

        # Constante de autenticación
        self.BASIC_AUTH = "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"

    def obtener_propuestas(self, rut: str, page: int, limit: int, sort: str) -> str:
        """
        Obtiene las propuestas de un cliente

        Args:
            rut (str): RUT del cliente
            page (int): Número de página
            limit (int): Límite de registros por página
            sort (str): Ordenamiento (formato: "folio|-1")

        Returns:
            str: Respuesta en formato JSON
        """
        try:
            url = "https://b2b-api.implementos.cl/api/cliente/propuestasCRM"

            headers = {
                "Content-Type": "application/json",
                "Authorization": self.BASIC_AUTH
            }

            payload = {
                "rut": rut,
                "page": page,
                "limit": limit,
                "sort": sort
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                result = response.json()
                log_debug(f"Se obtuvieron {result.get('found', 0)} propuestas para el cliente {rut}")
                return json.dumps(result, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error en la solicitud a la API: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({"error": True, "msg": error_message}, ensure_ascii=False, indent=2)

        except Exception as e:
            error_message = f"Error al obtener propuestas para el cliente {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": True, "msg": error_message}, ensure_ascii=False, indent=2)

    def obtener_propuesta(self, folio: int) -> str:
        """
        Obtiene una propuesta específica por su folio

        Args:
            folio (int): Folio de la propuesta

        Returns:
            str: Respuesta en formato JSON
        """
        try:
            url = "https://b2b-api.implementos.cl/api/catalogo/propuesta"

            headers = {
                "Content-Type": "application/json",
                "Authorization": self.BASIC_AUTH
            }

            payload = {
                "folio": folio
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                result = response.json()
                log_debug(f"Se obtuvo la propuesta con folio {folio}")
                return json.dumps(result, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error en la solicitud a la API: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({"error": True, "msg": error_message}, ensure_ascii=False, indent=2)

        except Exception as e:
            error_message = f"Error al obtener la propuesta con folio {folio}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": True, "msg": error_message}, ensure_ascii=False, indent=2)

    def generar_propuesta(
        self,
        codigo_vendedor: int,
        rut_cliente: str,
        tipos_propuesta: Optional[List[str]] = None,
        uens: Optional[List[str]] = None,
        codigo_sucursal: str = 'SAN BRNRDO',
        cantidad_propuesta: int = 50,
    ) -> str:
        """
        Genera una nueva propuesta

        Args:
            codigo_vendedor(int): Código del vendedor
            rut_cliente(str): Rut del cliente
            tipos_propuesta(Optional[List[str]]): Tipo de propuesta: RECOMMENDED (Recomendados para ti), STOPPED_PURCHASING (Productos Fugados), VEHICLE_FLEET (Flota). Por defecto ninguno para incluir todos.
            uens(Optional[List[str]]): Listado de UENs a incluir en la propuesta (Ejemplo: BATERIAS). Por defecto ninguno para incluir todas.
            codigo_sucursal(str): Código de sucursal para aplicar precios de la propuesta. Defecto SAN BRNRDO
            cantidad_propuesta(int): Cantidad de productos a contener en la propuesta. Defecto 50
        """
        try:
            client = MongoClient(Config.MONGO_NUBE)
            db = client.get_default_database()
            usuarioAX = db.usuariosAX.find_one({"codEmpleado": codigo_vendedor})
            cliente = db.clientes.find_one({"rut": rut_cliente}, {"_id": 0, "nombre": 1})
            bodega = db.imp_bodegas.find_one({"codigo": codigo_sucursal}, {"_id": 0, "nombre": 1})

            vendedor = {
                "rut": usuarioAX.get("rut"),
                "codEmpleado": int(usuarioAX.get("codEmpleado")),
                "codUsuario": int(usuarioAX.get("codUsuario")),
                "cuenta": usuarioAX.get("usuario").lower(),
                "email": usuarioAX.get("email"),
                "movil": usuarioAX.get("movil"),
                "nombre": usuarioAX.get("nombre"),
            }

            productosResponse = self._obtener_productos_propuesta(rut_cliente, codigo_sucursal, cantidad_propuesta, uens, tipos_propuesta)

            if not productosResponse or productosResponse.error or not productosResponse.data or len(productosResponse.data) == 0:
                logger.warning(f"No se encontraron productos a incluir en la propuesta")
                return json.dumps({"ok": False, "mensaje": f"Ningún producto encontrado para incluir en la propuesta"}, ensure_ascii=False, indent=2)

            articulos = []
            for x in productosResponse.data:
                for p in x.articulos:
                    # Creamos una nueva instancia de Articulo desde ArticuloFull
                    articulo = Articulo(
                        sku=p.sku,
                        nombre=p.nombre,
                        cantidad=1,
                        origenPropuesta=p.origenPropuesta,
                        estado=p.estado,
                        precio=p.precio
                    )

                    if articulo.precio.precioCliente is None:
                        articulo.precio.precioCliente = articulo.precio.precio

                    articulos.append(articulo)

            articulos_dict = [articulo.model_dump() for articulo in articulos]

            url = "https://b2b-api.implementos.cl/api/catalogo/propuestaCliente"
            data = {
                "cliente": {
                    "rut": rut_cliente,
                    "nombre": cliente.get("nombre"),
                },
                "sucursal": {
                    "codigo": codigo_sucursal,
                    "nombre": bodega.get("nombre"),
                },
                "tipo": 'especifica',
                "tipoEntrega": 'RETIRO',
                "vendedor": vendedor,
                "articulos": articulos_dict,
            }

            headers = {
                "Authorization": self.BASIC_AUTH
            }

            response = requests.post(url, headers=headers, json=data)
            propuesta_json = response.json()
            propuesta_json_str = json.dumps(propuesta_json)

            propuesta = PropuestaCliente.model_validate_json(propuesta_json_str,strict=False)

            respuesta = {
                "folio_propuesta": propuesta.folio
            }

            return json.dumps(respuesta, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error al obtener información del usuario: {str(e)}")
            return json.dumps({
                "ok": False,
                "mensaje": f"Error al generar propuesta de cliente: {str(e)}"
            }, ensure_ascii=False, indent=2)

    def _obtener_productos_propuesta(
        self,
        rut_cliente: str,
        sucursal: str,
        limite: int,
        uens: Optional[List[str]] = None,
        tipos_propuesta: Optional[List[str]] = None,
    ) -> ObtenerProductosPropuestaResponse:
        url = "https://b2b-api.implementos.cl/api/catalogo/propuestaCliente/especifica"

        headers = {
            "Authorization": self.BASIC_AUTH,
        }

        files = {
            "rut": (None, rut_cliente),
            "sucursal": (None, sucursal),
            "limite": (None, str(limite)),
            "uensOptions": (None, ""),
            "originOptions": (None, ""),
            "additionalOptions": (None, "INCLUDE_MATRIX"),
        }

        if uens:
            files["uensOptions"] = (None, ",".join(uens))
        if tipos_propuesta:
            files["originOptions"] = (None, ",".join(tipos_propuesta))

        response = requests.post(url, headers=headers, files=files)
        response_data = response.json()
        response_data_str = json.dumps(response_data)
        return ObtenerProductosPropuestaResponse.model_validate_json(response_data_str,strict=False)

    def generar_catalogo_propuesta(self, folio: int) -> str:
        """
        Genera un catálogo para una propuesta

        Args:
            folio (int): Folio de la propuesta

        Returns:
            str: Respuesta en formato JSON
        """
        try:
            url = "https://b2b-api.implementos.cl/api/catalogo/catalogoPropuesta"

            headers = {
                "Content-Type": "application/json",
                "Authorization": self.BASIC_AUTH
            }

            payload = {
                "folio": folio
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                result = response.json()
                log_debug(f"Se generó el catálogo para la propuesta con folio {folio}")
                json_response = {
                    "url": result["data"]["url"],
                }
                return json.dumps(json_response, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error en la solicitud a la API: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({"error": True, "msg": error_message}, ensure_ascii=False, indent=2)

        except Exception as e:
            error_message = f"Error al generar catálogo para la propuesta con folio {folio}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": True, "msg": error_message}, ensure_ascii=False, indent=2)

    def obtener_pdf_catalogo(self, folio: int, branch_code: str) -> str:
        """
        Obtiene el PDF de un catálogo de propuesta

        Args:
            folio (int): Folio de la propuesta
            branch_code (str): Código de la sucursal. Por defecto: SAN BRNRDO

        Returns:
            str: URL y nombre del archivo
        """
        try:
            branch_code_encoded = quote(branch_code)
            url = f"https://b2b-api.implementos.cl/api/catalogo/proposal-catalogue/pdf/{folio}?branchCode={branch_code_encoded}"
            filename = f"Propuesta-{folio}.pdf"

            result = {
                "url": url,
                "filename": filename,
            }

            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            error_message = f"Error al obtener PDF del catálogo para la propuesta con folio {folio}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": True, "msg": error_message}, ensure_ascii=False, indent=2)

    def _get_filename_from_header(self, header: Optional[str]) -> str:
        """
        Obtiene el nombre del archivo a partir de la cabecera Content-Disposition

        Args:
            header (Optional[str]): Cabecera Content-Disposition

        Returns:
            str: Nombre del archivo
        """
        if not header:
            return f"catalogo-{int(datetime.now().timestamp())}.pdf"

        import re
        filename_match = re.search(r'filename[^;=\n]*=(([\'"]).*?\2|[^;\n]*)', header)
        if filename_match and filename_match.group(1):
            return filename_match.group(1).replace('"', '').replace("'", "")

        return f"catalogo-{int(datetime.now().timestamp())}.pdf"

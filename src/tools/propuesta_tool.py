import json
import requests
from typing import List, Dict, Any, Optional, Union
from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger
from config.config import Config
import io
import base64
from datetime import datetime

class PropuestaTool(Toolkit):
    def __init__(self):
        super().__init__(name="propuesta_tool")
        # Registrar las funciones en el toolkit
        self.register(self.obtener_propuestas)
        self.register(self.obtener_propuesta)
        self.register(self.obtener_productos_propuesta)
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
    
    def obtener_productos_propuesta(
        self, 
        rut: str, 
        sucursal: str, 
        limite: int, 
        uens_options: Optional[str] = None, 
        origin_options: Optional[str] = None, 
        marca_flota: Optional[str] = None, 
        modelo_flota: Optional[str] = None, 
        tipo_flota: Optional[str] = None, 
        additional_options: Optional[str] = None
    ) -> str:
        """
        Obtiene los productos de una propuesta
        
        Args:
            rut (str): RUT del cliente
            sucursal (str): Código de la sucursal
            limite (int): Límite de productos a obtener
            uens_options (Optional[str]): Opciones de UEN (ej: "BATERIAS,AGROINSUMOS")
            origin_options (Optional[str]): Opciones de origen (ej: "RECOMMENDED,STOPPED_PURCHASING,VEHICLE_FLEET")
            marca_flota (Optional[str]): Marca de la flota
            modelo_flota (Optional[str]): Modelo de la flota
            tipo_flota (Optional[str]): Tipo de flota
            additional_options (Optional[str]): Opciones adicionales (ej: "INCLUDE_MATRIX")
            
        Returns:
            str: Respuesta en formato JSON
        """
        try:
            url = "https://b2b-api.implementos.cl/api/catalogo/propuestaCliente/especifica"
            
            headers = {
                "Authorization": self.BASIC_AUTH
            }
            
            # Crear formulario multipart
            data = {
                'rut': rut,
                'sucursal': sucursal,
                'limite': str(limite)
            }
            
            # Añadir campos opcionales si existen
            if uens_options:
                data['uensOptions'] = uens_options
            if origin_options:
                data['originOptions'] = origin_options
            if marca_flota:
                data['marcaFlota'] = marca_flota
            if modelo_flota:
                data['modeloFlota'] = modelo_flota
            if tipo_flota:
                data['tipoFlota'] = tipo_flota
            if additional_options:
                data['additionalOptions'] = additional_options
            
            response = requests.post(url, headers=headers, data=data)
            
            if response.status_code == 200:
                result = response.json()
                log_debug(f"Se obtuvieron {result.get('cantidad', 0)} productos para la propuesta del cliente {rut}")
                return json.dumps(result, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error en la solicitud a la API: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({"error": True, "msg": error_message}, ensure_ascii=False, indent=2)
                
        except Exception as e:
            error_message = f"Error al obtener productos para la propuesta del cliente {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": True, "msg": error_message}, ensure_ascii=False, indent=2)
    
    def generar_propuesta(
        self, 
        tipo: str, 
        tipo_entrega: str, 
        sucursal: Dict[str, str], 
        cliente: Dict[str, str], 
        vendedor: Dict[str, Any], 
        articulos: List[Dict[str, Any]]
    ) -> str:
        """
        Genera una nueva propuesta
        
        Args:
            tipo (str): Tipo de propuesta
            tipo_entrega (str): Tipo de entrega
            sucursal (Dict[str, str]): Información de la sucursal {"codigo": "...", "nombre": "..."}
            cliente (Dict[str, str]): Información del cliente {"rut": "...", "nombre": "..."}
            vendedor (Dict[str, Any]): Información del vendedor
            articulos (List[Dict[str, Any]]): Lista de artículos
            
        Returns:
            str: Respuesta en formato JSON
        """
        try:
            url = "https://b2b-api.implementos.cl/api/catalogo/propuestaCliente"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": self.BASIC_AUTH
            }
            
            payload = {
                "tipo": tipo,
                "tipoEntrega": tipo_entrega,
                "sucursal": sucursal,
                "cliente": cliente,
                "vendedor": vendedor,
                "articulos": articulos
            }
            
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                log_debug(f"Se generó la propuesta para el cliente {cliente.get('rut', '')}")
                return json.dumps(result, ensure_ascii=False, indent=2)
            else:
                error_message = f"Error en la solicitud a la API: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({"error": True, "msg": error_message}, ensure_ascii=False, indent=2)
                
        except Exception as e:
            error_message = f"Error al generar propuesta para el cliente {cliente.get('rut', '')}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": True, "msg": error_message}, ensure_ascii=False, indent=2)
    
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
                return json.dumps(result, ensure_ascii=False, indent=2)
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
            branch_code (str): Código de la sucursal
            
        Returns:
            str: Respuesta en formato JSON con el contenido del PDF en base64
        """
        try:
            branch_code_encoded = requests.utils.quote(branch_code)
            url = f"https://b2b-api.implementos.cl/api/catalogo/proposal-catalogue/pdf/{folio}?branchCode={branch_code_encoded}"
            
            headers = {
                "Authorization": self.BASIC_AUTH
            }
            
            response = requests.get(url, headers=headers, stream=True)
            
            if response.status_code == 200:
                # Obtener el tipo de contenido
                content_type = response.headers.get("content-type", "application/pdf")
                
                # Obtener el nombre del archivo de las cabeceras
                filename = self._get_filename_from_header(response.headers.get("content-disposition"))
                
                # Convertir a base64
                pdf_data = base64.b64encode(response.content).decode('utf-8')
                
                result = {
                    "error": False,
                    "msg": "PDF obtenido correctamente",
                    "data": {
                        "content_type": content_type,
                        "filename": filename,
                        "pdf_data": pdf_data
                    }
                }
                
                log_debug(f"Se obtuvo el PDF del catálogo para la propuesta con folio {folio}")
                return json.dumps(result, ensure_ascii=False)
            else:
                error_message = f"Error en la solicitud a la API: {response.status_code} - {response.text}"
                logger.warning(error_message)
                return json.dumps({"error": True, "msg": error_message}, ensure_ascii=False, indent=2)
                
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
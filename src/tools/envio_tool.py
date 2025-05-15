import json
import requests
from typing import List
from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger

class EnvioTool(Toolkit):
    def __init__(self):
        super().__init__(name="envio_tool")
        # Registrar las funciones en el toolkit para que sean accesibles dinámicamente
        self.register(self.fecha_retiro)
        self.register(self.fecha_despacho)

    def fecha_retiro(self, sucursal: str, productos: List[dict]) -> str:
        """
        Valida disponibilidad y fechas de retiro disponible de un listado de productos para un código de sucursal/tienda válido
        
        Args:
            sucursal (str): código de sucursal de tienda
            productos (List[dict]): lista de productos del carro abierto del cliente
                            donde cada producto es un diccionario con las claves 'sku' (str) y 'cantidad' (int).
                            Ejemplo: [{'sku': '123456', 'cantidad': 2}, {'sku': '789012', 'cantidad': 1}]
                            
        Returns:
            str: Resultado de fechas disponibles en formato JSON.
        """
        try:
            log_debug(f"Consultando fechas de retiro para sucursal {sucursal.upper()}")
            
            # URL de la API
            api_url = f"https://b2b-api.implementos.cl/api/promesa-entrega/retiroTienda/{sucursal.upper()}"
            
            # Configurar los headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            # El formato correcto para el body parece ser "productosCarro", no "productos"
            body_despacho = {
                "omni": False,
                "stockSeguridad": False,
                "multiProveedor": False,
                "usarStockAX": True,
                "productos": productos  # Cambio aquí de "productos" a "productosCarro"
            }
            
            log_debug(f"Request body: {json.dumps(body_despacho)}")
            
            # Realizar la solicitud POST
            response = requests.post(api_url, headers=headers, json=body_despacho)
            
            # Verificar si la solicitud fue exitosa
            if response.status_code == 200:
                # Convertir la respuesta a JSON
                result = response.json()
                
                # Basado en la estructura del JSON de ejemplo, necesitamos extraer las fechas del campo "fletes"
                delivery_options = []
                
                # Verificar si hay respuestas en el resultado
                if result.get('status') == 'success' and 'respuesta' in result.get('data', {}):
                    for respuesta in result['data']['respuesta']:
                        # Verificar si hay subórdenes
                        if 'subOrdenes' in respuesta:
                            for subOrden in respuesta['subOrdenes']:
                                # Extraer fechas de los fletes
                                if 'fletes' in subOrden:
                                    for flete in subOrden['fletes']:
                                        fecha = flete.get('fecha', '').split('T')[0] if flete.get('fecha') else ''
                                        delivery_options.append({
                                            'precio': flete.get('valor', 0),
                                            'fecha': fecha,
                                            'dia': flete.get('fechaDia', ''),
                                            'tienda': sucursal.upper(),
                                            'servicio': flete.get('opcionServicio', {}).get('tser_nomb', 'RETIRO EN TIENDA')
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
        Valida Disponibilidad y fechas de despacho a domicilio disponibles de un listado de productos para una comuna, ciudad o localidad
        
        Args:
            comuna (str): localidad de destino de despacho (comuna, ciudad, localidad)
            productos (List[dict]): lista de productos del carro abierto del cliente
                            donde cada producto es un diccionario con las claves 'sku' (str) y 'cantidad' (int).
                            Ejemplo: [{'sku': '123456', 'cantidad': 2}, {'sku': '789012', 'cantidad': 1}]
                            
        Returns:
            str: Resultado de fechas disponibles para un despacho a domicilio en formato JSON.
        """
        try:
            log_debug(f"Consultando fechas de despacho para comuna {comuna.upper()}")
            
            # URL de la API
            api_url = f"https://b2b-api.implementos.cl/api/promesa-entrega/domicilio/{comuna.upper()}"
            
            # El formato correcto para el body parece ser "productosCarro", no "productos"
            body = {
                "omni": False,
                "stockSeguridad": False,
                "multiProveedor": False,
                "usarStockAX": True,
                "productos": productos  # Cambio aquí de "productos" a "productosCarro"
            }
            
            # Configurar los headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            log_debug(f"Request body: {json.dumps(body)}")
            
            # Realizar la solicitud POST
            response = requests.post(api_url, headers=headers, json=body)
            
            # Verificar si la solicitud fue exitosa
            if response.status_code == 200:
                # Convertir la respuesta a JSON
                result = response.json()
                
                # Basado en la estructura del JSON de ejemplo, procesamos las fechas de los fletes
                delivery_options = []
                
                # Verificar si hay respuestas en el resultado
                if result.get('status') == 'success' and 'respuesta' in result.get('data', {}):
                    for respuesta in result['data']['respuesta']:
                        # Verificar si hay subórdenes
                        if 'subOrdenes' in respuesta:
                            for subOrden in respuesta['subOrdenes']:
                                # Extraer fechas de los fletes
                                if 'fletes' in subOrden:
                                    for flete in subOrden['fletes']:
                                        fecha = flete.get('fecha', '').split('T')[0] if flete.get('fecha') else ''
                                        delivery_options.append({
                                            'precio': flete.get('valor', 0),
                                            'fecha': fecha,
                                            'dia': flete.get('fechaDia', ''),
                                            'comuna': comuna.upper(),
                                            'servicio': flete.get('opcionServicio', {}).get('tser_nomb', 'DESPACHO A DOMICILIO')
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
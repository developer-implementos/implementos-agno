import json
import requests
from typing import List
from datetime import datetime
from pymongo import MongoClient
from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger
from bson.json_util import dumps
from config.config import Config

class ClientesEcommerceTool(Toolkit):
    def __init__(self):
        super().__init__(name="clientes_ecommerce_tool")
        # Registrar las funciones en el toolkit para que sean accesibles dinámicamente.
        self.register(self.clientes_informacion)
        self.register(self.estado_pedidos)
    def clientes_informacion(self, rut: str) -> str:
        """
        buscar un cliente por su RUT y direcciones util para despachos
        
        Args:
            rut (str): RUT del cliente a buscar
        
        Returns:
            str: Información del cliente en formato JSON si se encuentra, error en caso contrario
        """
        try:
            client = MongoClient(Config.MONGO_NUBE)
            db = client.Implenet
            clientes = db.clientes
            
            campos = {
                "rut": 1,
                "apellido": 1,
                "nombre": 1,
                "direcciones":1,
                "_id": 0  # Excluir el campo _id
            }
            
            # Buscar cliente por RUT incluyendo solo los campos especificados
            cliente = clientes.find_one({"rut": rut}, projection=campos)
            
            # Cerrar la conexión
            client.close()
            
            # Filtrar campos adicionales en las direcciones
            if cliente and 'direcciones' in cliente:
                direcciones_filtradas = []
                for direccion in cliente['direcciones']:
                    direccion_filtrada = {
                        'calle': direccion.get('calle', ''),
                        'numero': direccion.get('numero', ''),
                        'comuna': direccion.get('comuna', ''),
                        'direccionCompleta': direccion.get('direccionCompleta', ''),
                        'tipo': direccion.get('tipo', ''),
                        'localidad': direccion.get('localidad', '')
                    }
                    direcciones_filtradas.append(direccion_filtrada)
                cliente['direcciones'] = direcciones_filtradas
                
            if cliente:
                cliente_json = json.dumps(cliente, ensure_ascii=False, indent=2)
                log_debug(f"Cliente con RUT {rut} encontrado correctamente")
                return cliente_json
            
            log_debug(f"No se encontró cliente con el RUT: {rut}")
            return json.dumps({"error": f"No se encontró cliente con el RUT: {rut}"}, ensure_ascii=False, indent=2)
        
        except Exception as e:
            error_message = f"Error al buscar cliente con RUT {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)

    def estado_pedidos(self, rut: str, ov: str) -> str:
        """
        Función para conocer el estado de entrega de un pedido
        
        Args:
            rut (str): RUT de cliente a buscar
            ov (str): ID de orden de venta formato OV-1234567
        
        Returns:
            str: respuesta de estado de pedido
        """
        try:
            # Establecer conexión con la API
            api_url = f"https://b2b-api.implementos.cl/ecommerce/api/v1/oms/order/tracking/{ov}"
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Basic c2VydmljZXM6MC49ajNEMnNzMS53Mjkt"
            }
            
            # Realizar la solicitud GET
            response = requests.get(api_url, headers=headers)
            data = response.json()
            
            
            
            # Convertir a JSON
            return json.dumps(data, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_message = f"Error al buscar pedido {ov} para cliente {rut}: {e}"
            logger.warning(error_message)
            return json.dumps({"error": error_message}, ensure_ascii=False, indent=2)

import json
import requests
from agno.tools import Toolkit
from typing import List, Dict
from agno.utils.log import log_debug, log_info, logger
from databases.clickhouse_client import config

class WhatsappTools(Toolkit):
    def __init__(self):
        super().__init__(name="whatsapp_tools")
        # Registrar las funciones en el toolkit para que sean accesibles dinámicamente
        self.register(self.enviar_productos)
        self.register(self.mensaje_espera)
        self.register(self.enviar_imagenes_producto)
        
    def enviar_productos(self, productos: List[dict], whatsapp: str) -> str:
        """
        Envía múltiples productos por whatsapp al cliente, un mensaje por cada producto
        
        Parámetros:
        - productos (List[dict]: Lista de productos donde cada producto es un diccionario con:
          {
            "url_imagen": URL de la imagen a enviar,
            "informacion": informacion de producto (nombre, descripcion, marca)formateada para envio por whatsapp,
            "precio": precio producto
            "sku": id de producto
          }
        - whatsapp: numero de whatsapp del usuario sin @c.us
        
        Retorna:
        - La respuesta de la API
        """
        numero = whatsapp.split('@')[0] if '@' in whatsapp else whatsapp
        # URL de la API con el token ya incluido
        api_url = "https://api.1msg.io/LOK09150983/sendFile?token=xH6C6nrsDAz7ewdlFGHwhsgwcWGwAIi4"
        
        responses = []
        
        for producto in productos:
            url_imagen = producto.get("url_imagen", "")
            informacion = "*SKU*:"+producto.get("sku", "")+"\n*Precio*: $ "+str(producto.get("precio", ""))+"\n"+producto.get("informacion", "")
            sku = producto.get("sku", "")
            
            # Preparar los datos para la solicitud
            payload = {
                'body': url_imagen,  # URL de la imagen
                'filename': sku+'.jpg',  # Nombre predeterminado para la imagen
                'caption': informacion,    # Texto que acompañará a la imagen
                'phone': numero      # Número de teléfono del destinatario
            }
            
            # Realizar la solicitud POST a la API
            response = requests.post(api_url, data=payload)
            responses.append(response.json())
        
        return "productos enviados"   
    def mensaje_espera(self, mensaje: str, whatsapp: str) -> str:
        """
        Envio de mensaje de espera en procesos largos formateada para whatsapp
        
        Parámetros:
            - mensaje: informacion formateada para envio por whatsapp
            - whatsapp: numero de whatsapp del usuario sin @c.us
        
        Retorna:
        - La respuesta de la API
        """
        numero = whatsapp.split('@')[0] if '@' in whatsapp else whatsapp
        # URL de la API con el token ya incluido
        api_url = "https://api.1msg.io/LOK09150983/sendMessage?token=xH6C6nrsDAz7ewdlFGHwhsgwcWGwAIi4"
        
        # Preparar los datos para la solicitud
        payload = {
            'body': mensaje,  # URL de la imagen
            'phone': numero      # Número de teléfono del destinatario
        }
        
        # Realizar la solicitud POST a la API
        response = requests.post(api_url, data=payload)
        return "mensaje de espera enviado"
    def enviar_imagenes_producto(self, producto: Dict, whatsapp: str) -> str:
            """
            Envía una imagenes de un producto particular por WhatsApp
            
            Parámetros:
            - producto (Dict): Diccionario con la información del producto:
            {
                "sku": id del producto,
                "nombre": nombre del producto,
                "descripcion": descripción detallada del producto,
                "precio": precio del producto,
                "atributos": diccionario de atributos del producto (ej: {"color": "rojo", "tamaño": "grande"}),
                "imagenes": lista de URLs de imágenes del producto
            }
            - whatsapp: número de WhatsApp del usuario sin @c.us
            
            Retorna:
            - La respuesta imagenes de producto
            """
            numero = whatsapp.split('@')[0] if '@' in whatsapp else whatsapp
            api_url_imagen = "https://api.1msg.io/LOK09150983/sendFile?token=xH6C6nrsDAz7ewdlFGHwhsgwcWGwAIi4"           
            responses = []
            
            # 1. Enviar las imágenes del producto
            imagenes = producto.get("imagenes", [])
            sku = producto.get("sku", "")
            
            for i, url_imagen in enumerate(imagenes):
                # Preparar los datos para la solicitud de imagen
                payload = {
                    'body': url_imagen,
                    'filename': f"{sku}_imagen_{i+1}.jpg",
                    'caption': f"Imagen {i+1} de {len(imagenes)} - {producto.get('nombre', '')}",
                    'phone': numero
                }
                
                # Realizar la solicitud POST para enviar la imagen
                response = requests.post(api_url_imagen, data=payload)
                responses.append(response.json())                                 

            return "imagenes de producto enviada"    
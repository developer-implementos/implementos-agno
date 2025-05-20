from agno.tools import Toolkit
from google.cloud import storage
import os
from io import BytesIO
from markdown_pdf import MarkdownPdf
from markdown_pdf import Section
from datetime import datetime


class PdfTool(Toolkit):
    def __init__(self):
        super().__init__(name="PdfTool")
        self.register(self.markdown_pdf)

    def markdown_pdf(self,
                     markdown_content: str,
                     title: str = "Informe",
                     filename: str = None,
                     upload_to_cloud: bool = True
                     ) -> str:
        """
        Convierte datos markdown a PDF y opcionalmente lo sube a Google Cloud Storage

        Args:
            markdown_content (str): datos completos en markdown
            title (str): título del documento PDF
            filename (str, optional): nombre del archivo PDF. Si es None, se genera automáticamente.
            upload_to_cloud (bool): Si es True, sube el archivo a GCS en lugar de guardarlo localmente

        Returns:
            str: URL pública del PDF en GCS o ruta local del archivo PDF
        """
        try:
            # Generar nombre de archivo si no se proporciona
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_title = title.replace(' ', '_').replace('/', '-')
                filename = f"{safe_title}_{timestamp}.pdf"
            elif not filename.endswith('.pdf'):
                filename += '.pdf'

            custom_css = """
        @page {
            size: A4 landscape; /* Formato apaisado para mayor ancho */
            margin: 1.5cm; /* Márgenes uniformes */
        }

        body {
            font-family: 'Helvetica', 'Arial', sans-serif;
            font-size: 11pt; /* Tamaño de letra ligeramente reducido para mejor ajuste */
            line-height: 1.4;
            color: #333;
        }

        /* Estilos para títulos */
        h1, h2, h3, h4, h5, h6 {
            page-break-after: avoid; /* Evita saltos de página después de títulos */
            page-break-inside: avoid; /* Evita que un título se divida entre páginas */
        }

        h1 {
            font-size: 20pt;
            color: #1a5276;
            margin-top: 15pt;
            margin-bottom: 10pt;
        }

        h2 {
            font-size: 16pt;
            color: #2874a6;
            margin-top: 12pt;
            margin-bottom: 8pt;
        }

        /* Estilos para tablas optimizados */
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 10pt 0;
            page-break-inside: avoid; /* Intenta evitar que las tablas se corten entre páginas */
            font-size: 8pt; /* Texto más pequeño en tablas para mejor ajuste */
        }

        th {
            background-color: #f2f2f2;
            font-weight: bold;
            text-align: left;
            padding: 3pt;
            border: 1pt solid #ddd;
        }

        td {
            padding: 3pt;
            border: 1pt solid #ddd;
            word-wrap: break-word; /* Permite que el texto se ajuste dentro de las celdas */
            max-width: 250pt; /* Limita el ancho máximo de las celdas */
        }

        tr:nth-child(even) {
            background-color: #f9f9f9;
        }

        /* Otros elementos */
        p {
            margin-bottom: 8pt;
        }

        ul, ol {
            margin-left: 15pt;
            margin-bottom: 8pt;
            page-break-inside: avoid; /* Evita que las listas se corten entre páginas */
        }

        li {
            margin-bottom: 4pt;
        }

        a {
            color: #3498db;
            text-decoration: underline;
        }

        /* Evitar que las imágenes se corten */
        img {
            max-width: 100%;
            page-break-inside: avoid;
        }

        /* Ajuste para códigos y bloques de texto */
        pre, code {
            white-space: pre-wrap; /* Permite que el código se ajuste */
            word-wrap: break-word;
            font-size: 9pt;
        }

        /* Estilos para separadores horizontales */
        hr {
            border: none;
            height: 1pt;
            background-color: #ddd;
            margin: 10pt 0;
            page-break-after: avoid;
        }
        """

            # Crear el documento PDF
            pdf = MarkdownPdf(toc_level=2)

            # Configurar metadatos del documento
            pdf.meta["title"] = title

            # Crear una sección con configuración personalizada
            section = Section(
                text=markdown_content,
                toc=True,
                paper_size="A4",  # Tamaño del papel
                borders=(50, 50, -50, -50)  # Márgenes más amplios para mejor legibilidad
            )

            # Añadir la sección al PDF con el CSS personalizado
            pdf.add_section(section, user_css=custom_css)
            # Añadir la sección con contenido markdown

            if upload_to_cloud:
                # Crear un buffer en memoria para el PDF
                pdf_buffer = BytesIO()
                pdf.save(pdf_buffer)
                pdf_buffer.seek(0)

                # Subir el PDF a Google Cloud Storage
                public_url = self.upload_to_gcs(pdf_buffer.getvalue(), filename)
                return public_url
            else:
                # Guardar el PDF localmente
                save_path = "./pdfs"
                os.makedirs(save_path, exist_ok=True)
                file_path = os.path.join(save_path, filename)
                pdf.save(file_path)
                return str(file_path)

        except Exception as e:
            print(f"Error al generar o subir el PDF: {str(e)}")
            return f"Error: {str(e)}"

    def upload_to_gcs(self, pdf_buffer, file_name):
        """
        Sube un archivo PDF a Google Cloud Storage.

        Args:
            pdf_buffer (bytes): Contenido del PDF en bytes
            file_name (str): Nombre del archivo a guardar en GCS

        Returns:
            str: URL pública del archivo subido
        """
        try:
            # Configurar el cliente de almacenamiento
            storage_client = storage.Client.from_service_account_json(
                os.path.join(os.path.dirname(__file__), 'key-storage.json')
            )

            # Definir el nombre del bucket
            bucket_name = 'imagenes_catalogo_publico'

            # Obtener el bucket
            bucket = storage_client.bucket(bucket_name)

            # Crear el objeto blob (archivo) en el bucket
            blob = bucket.blob(file_name)

            # Configurar metadatos del archivo
            blob.content_type = 'application/pdf'
            blob.cache_control = 'no-cache'

            # Subir el contenido del archivo
            blob.upload_from_string(
                pdf_buffer,
                content_type='application/pdf'
            )

            # Generar URL pública
            public_url = f"https://storage.googleapis.com/{bucket_name}/{file_name}"
            return public_url

        except Exception as e:
            print(f"Error al subir el archivo: {str(e)}")
            raise e



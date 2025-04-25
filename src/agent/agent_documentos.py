from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.knowledge.combined import CombinedKnowledgeBase
from agno.knowledge.pdf import PDFKnowledgeBase
from agno.knowledge.csv import CSVKnowledgeBase
from agno.knowledge.docx import DocxKnowledgeBase
from agno.knowledge.json import JSONKnowledgeBase
from agno.knowledge.text import TextKnowledgeBase
from agno.vectordb.qdrant import Qdrant
from config.config import Config

knowledge_base = CombinedKnowledgeBase(
    sources=[
        PDFKnowledgeBase(
            vector_db=Qdrant(
            collection="recipes_pdf",
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY,           
        ),
             path=""
        ),
        CSVKnowledgeBase(
            vector_db=Qdrant(
            collection="recipes_csv",
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY
            ),
            path=""
        ),
        DocxKnowledgeBase(
            vector_db=Qdrant(
            collection="recipes_docx",
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY
            ),
            path=""
        ),
        JSONKnowledgeBase(
            vector_db=Qdrant(
            collection="recipes_json",
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY
            ),
            path=""
        ),
        TextKnowledgeBase(
           vector_db=Qdrant(
            collection="recipes_txt",
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY
            ),
            path=""
        ),
    ],
    vector_db=Qdrant(
            collection="recipes_combined",
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY
            ),
)

Agente_Documentos = Agent(
    name="Agente Análisis de Documentos",
    agent_id="documentos_01",
    role="Responde a preguntas de documentos cargados.",
    model=OpenAIChat(id="gpt-4o-mini", api_key=Config.OPENAI_API_KEY),
    knowledge=knowledge_base,
    show_tool_calls=True,
    markdown=True,
    stream=True,
    stream_intermediate_steps=True,
    system_message="Usa formato markdown para todas tus respuestas. Formatea citas y referencias de forma clara. Utiliza cabeceras, listas, tablas y otros elementos de markdown cuando sea apropiado.",
    perfiles=["1", "5"]
)
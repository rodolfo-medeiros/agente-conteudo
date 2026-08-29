import os
import re
import time
import glob
_cache_system_prompt = None

# Bibliotecas do LangChain e Gemini
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_chroma import Chroma
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate


# Bibliotecas Oficiais da API do Google Drive
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as OAuth2Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload, MediaFileUpload
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError

from utils import config


# ============================================================
# HELPERS DE TEXTO / PDF
# ============================================================

_PADRAO_EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF"   # Pictogramas diversos
    "\U00002600-\U000027BF"   # Símbolos diversos (✅ ☀ ⭐ etc.)
    "\U0001F000-\U0001F02F"   # Mahjong
    "\U0001F0A0-\U0001F0FF"   # Cartas
    "\U0001F1E6-\U0001F1FF"   # Bandeiras
    "\U0001F680-\U0001F6FF"   # Transporte
    "\U0001F900-\U0001F9FF"   # Símbolos suplementares
    "\U0000200D"              # Zero-width joiner
    "\U0000FE0F"              # Variation selector
    "]+"
)


def _escape_markdown(texto):
    """Converte markdown básico (**negrito**, *itálico*) para markup do reportlab e remove emojis."""
    texto = _PADRAO_EMOJI.sub("", texto)
    # Escapa caracteres XML primeiro
    texto = texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Converte **negrito**
    texto = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", texto, flags=re.DOTALL)
    # Converte *itálico*
    texto = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<i>\1</i>", texto)
    return texto


def extrair_semanas(resumo):
    """
    Extrai as seções de cada semana do resumo gerado pela IA.

    Aceita formatos como:
      - '## 📅 Semana 1 (01/08 a 07/08): Título'
      - '#### **Semana 1: Título**'
      - '### Semana 1 - Título'
      - '#### Semana 1: Título'

    Retorna lista de dicts: {'numero': int, 'titulo': str, 'conteudo': str}
    """
    padrao = re.compile(
        r"^#{1,6}\s*(?:📅\s*)?(?:\*\*)?Semana\s+(?P<numero>\d+)[^\n]*\n(?P<corpo>.*?)"
        r"(?=^#{1,6}\s*(?:📅\s*)?(?:\*\*)?Semana\s+\d+|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )

    semanas = []
    for match in padrao.finditer(resumo):
        inicio_heading = match.start()
        fim_linha = resumo.find("\n", inicio_heading)
        header = (
            resumo[inicio_heading:fim_linha].strip()
            if fim_linha != -1
            else resumo[inicio_heading:].strip()
        )
        corpo = match.group("corpo").strip()

        try:
            numero = int(match.group("numero"))
        except ValueError:
            continue

        # Remove negrito ** do título, se houver
        titulo = header.replace("**", "").strip()
        if ":" in titulo:
            titulo = titulo.split(":", 1)[1].strip()

        semanas.append(
            {
                "numero": numero,
                "titulo": titulo or f"Semana {numero}",
                "conteudo": f"{header}\n\n{corpo}",
            }
        )

    semanas.sort(key=lambda s: s["numero"])
    return semanas


def gerar_pdf_semana(titulo, conteudo, caminho_saida):
    """Gera um PDF de conteúdo contínuo (estilo documento) com reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    os.makedirs(os.path.dirname(caminho_saida) or ".", exist_ok=True)

    doc = SimpleDocTemplate(
        caminho_saida,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=titulo,
        author="Agente de Conteúdo Token",
    )

    estilos = getSampleStyleSheet()

    estilo_titulo = ParagraphStyle(
        "TituloSemana",
        parent=estilos["Title"],
        fontSize=18,
        leading=22,
        spaceAfter=16,
        textColor=colors.HexColor("#1a1a2e"),
    )
    estilo_h2 = ParagraphStyle(
        "H2Semana",
        parent=estilos["Heading2"],
        fontSize=14,
        leading=18,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.HexColor("#16213e"),
    )
    estilo_h3 = ParagraphStyle(
        "H3Semana",
        parent=estilos["Heading3"],
        fontSize=12,
        leading=16,
        spaceBefore=10,
        spaceAfter=5,
        textColor=colors.HexColor("#0f3460"),
    )
    estilo_h4 = ParagraphStyle(
        "H4Semana",
        parent=estilos["Heading4"],
        fontSize=11,
        leading=15,
        spaceBefore=8,
        spaceAfter=4,
        textColor=colors.HexColor("#333333"),
    )
    estilo_corpo = ParagraphStyle(
        "CorpoSemana",
        parent=estilos["BodyText"],
        fontSize=10.5,
        leading=14,
        spaceAfter=6,
    )
    estilo_bullet = ParagraphStyle(
        "BulletSemana",
        parent=estilos["BodyText"],
        fontSize=10.5,
        leading=14,
        leftIndent=16,
        bulletIndent=6,
        spaceAfter=4,
    )

    elementos = [
        Paragraph(_escape_markdown(titulo), estilo_titulo),
        Spacer(1, 0.3 * cm),
    ]

    for linha in conteudo.splitlines():
        linha_limpa = linha.strip()

        if not linha_limpa:
            elementos.append(Spacer(1, 0.2 * cm))
            continue

        if linha_limpa.startswith("#### "):
            elementos.append(Paragraph(_escape_markdown(linha_limpa[5:]), estilo_h4))
        elif linha_limpa.startswith("### "):
            elementos.append(Paragraph(_escape_markdown(linha_limpa[4:]), estilo_h3))
        elif linha_limpa.startswith("## "):
            elementos.append(Paragraph(_escape_markdown(linha_limpa[3:]), estilo_h2))
        elif linha_limpa.startswith("# "):
            elementos.append(Paragraph(_escape_markdown(linha_limpa[2:]), estilo_h2))
        elif linha_limpa.startswith(("- ", "* ")):
            texto_bullet = linha_limpa[2:]
            elementos.append(
                Paragraph(_escape_markdown(texto_bullet), estilo_bullet, bulletText="•")
            )
        elif linha_limpa == "---":
            elementos.append(Spacer(1, 0.3 * cm))
        else:
            elementos.append(Paragraph(_escape_markdown(linha_limpa), estilo_corpo))

    doc.build(elementos)
    print(f"PDF gerado: {caminho_saida}")
    return caminho_saida


# ============================================================
# GOOGLE DRIVE
# ============================================================

def conectar_google_drive():
    """Autentica na API do google drive usando OAuth2 (conta pessoal)."""
    credentials = None

    # 1. Carrega token salvo em cache (se existir)
    if os.path.exists(config.TOKEN_CACHE):
        try:
            credentials = OAuth2Credentials.from_authorized_user_file(
                config.TOKEN_CACHE, config.SCOPES
            )
        except Exception as e:
            print(f"⚠️ Cache de token inválido, refazendo login: {e}")
            credentials = None

    # 2. Tenta renovar o token (com proteção contra expiração/revogação)
    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except RefreshError:
            print("⚠️ Token expirado/revogado. Refazendo login...")
            credentials = None
            # Remove o cache corrompido para não travar em tentativas futuras
            if os.path.exists(config.TOKEN_CACHE):
                os.remove(config.TOKEN_CACHE)

    # 3. Se não houver credencial válida, faz novo login interativo
    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            config.OAUTH_CREDENTIALS, config.SCOPES
        )
        credentials = flow.run_local_server(port=0)

        # Salva o novo token para próximas vezes
        with open(config.TOKEN_CACHE, "w") as token:
            token.write(credentials.to_json())

    # 4. Conecta ao serviço do Drive
    try:
        service = build("drive", "v3", credentials=credentials)
        print("✅ Autenticado no Google Drive com sua conta pessoal!")
        return service
    except Exception as e:
        print(f"Erro ao conectar ao Google Drive: {e}")
        return None


def criar_pasta_drive(service, nome_pasta, id_pasta_pai=None):
    """Cria uma pasta no Google Drive."""
    print(f"Criando pasta '{nome_pasta}' no Google Drive...")

    # No google Drive pastas são arquivos com mimeType específico
    metadata_pasta = {
        'name': nome_pasta,
        'mimeType': 'application/vnd.google-apps.folder'
    }

    # Informado a pasta pai, a nova pasta será criada dentro dela
    if id_pasta_pai:
        metadata_pasta['parents'] = [id_pasta_pai]

    try:
        pasta = service.files().create(body=metadata_pasta, fields='id').execute()
        id_pasta = pasta.get('id')
        print(f"Pasta {nome_pasta} criada com sucesso! ID: {id_pasta}")
        return id_pasta
    except HttpError as e:
        print(f"Erro ao criar pasta: {e}")
        return None


def criar_documento_resumo(service, nome_arquivo, conteudo_texto, id_pasta_destino):
    """Cria um documento de texto no Google Drive com o conteúdo fornecido."""
    print(f"Criando documento '{nome_arquivo}' no Google Drive...")

    metadata_arquivo = {
        'name': nome_arquivo,
        # 'application/vnd.google-apps.document' converte o texto para o formato nativo do Google Docs!
        'mimeType': 'application/vnd.google-apps.document',
        'parents': [id_pasta_destino]
    }

    # prepara o conteúdo em texto plano para upload
    media = MediaInMemoryUpload(conteudo_texto.encode('utf-8'), mimetype='text/plain')

    try:
        arquivo = service.files().create(
            body=metadata_arquivo,
            media_body=media,
            fields='id, webViewLink'
        ).execute()

        print(f"Arquivo salvo com sucesso")
        print(f"Link de acesso: {arquivo.get('webViewLink')}")
        return arquivo.get('id')
    except HttpError as e:
        print(f"Erro ao salvar documento: {e}")
        return None


def upload_arquivo_drive(service, caminho_local, nome_arquivo, mime_type, id_pasta_destino):
    """Faz upload de um arquivo local (ex: PDF) para uma pasta do Google Drive."""
    metadata_arquivo = {
        'name': nome_arquivo,
        'parents': [id_pasta_destino],
    }

    media = MediaFileUpload(caminho_local, mimetype=mime_type, resumable=False)

    try:
        arquivo = service.files().create(
            body=metadata_arquivo,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        print(f"Arquivo '{nome_arquivo}' enviado com sucesso!")
        print(f"Link de acesso: {arquivo.get('webViewLink')}")
        return arquivo.get('id')
    except HttpError as e:
        print(f"Erro ao enviar arquivo: {e}")
        return None


# ============================================================
# INGESTÃO E PROCESSAMENTO COM RAG (Lang Chain + Gemini)
# ============================================================

def obter_ou_criar_vectorstore(caminho_pasta="knowledge_base"):
    """
    OTIMIZAÇÃO CRUCIAL: Verifica se o ChromaDB já existe no disco.
    Se sim, carrega os vetores existentes (R$ 0 em API e 0s de espera).
    Se não, processa o PDF e salva no disco.
    """
    embeddings = GoogleGenerativeAIEmbeddings(model=obter_modelo_embedding())

    # Se a pasta do ChromaDB existir e não estiver vazia, carrega do disco
    if os.path.exists(config.PASTA_CHROMA) and os.listdir(config.PASTA_CHROMA):
        print("Carregando banco vetorial do disco...")
        return Chroma(
            persist_directory=config.PASTA_CHROMA,
            embedding_function=embeddings
        )

    # processa todos os pdf´s na pasta
    pdfs = glob.glob(os.path.join(caminho_pasta, "*.pdf"))
    print(f"Encontrados {len(pdfs)} arquivos PDF na pasta '{caminho_pasta}' para processamento.")

    todos_chunks = []

    for caminho_pdf in pdfs:
        nome_arquivo = os.path.basename(caminho_pdf)
        print(f"Processando: {nome_arquivo}")

        loader = PyMuPDFLoader(caminho_pdf)
        documentos = loader.load()

        for doc in documentos:
            doc.metadata["source_pdf"] = nome_arquivo  # Adiciona o nome do PDF como metadado

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP
        )
        chunks = text_splitter.split_documents(documentos)
        todos_chunks.extend(chunks)

    print("Gerando embeddings e salvando no banco vetorial...")
    vector_store = Chroma.from_documents(
        documents=todos_chunks,
        embedding=embeddings,
        persist_directory=config.PASTA_CHROMA
    )
    return vector_store


def carregar_system_prompt(caminho=None):
    """Carrega o system prompt do arquivo markdown."""
    global _cache_system_prompt
    if _cache_system_prompt is not None:
        return _cache_system_prompt

    caminho = caminho or config.SYSTEM_PROMPT_PATH
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as f:
            _cache_system_prompt = f.read().strip()
            print(f"System prompt carregado de '{caminho}' ({len(_cache_system_prompt)} chars)")
            return _cache_system_prompt
    else:
        raise FileNotFoundError(
            f"Arquivo de system prompt não encontrado: {caminho}"
            "Crie o arquivo com o conteúdo desejado."
        )


def obter_modelo_embedding():
    """Retorna o modelo de embedding atualizado e compatível com a API do Gemini."""
    modelo_config = config.GOOGLE_EMBEDDING_MODEL.strip()

    # Garantimos que não haja o prefixo 'models/' duplicado
    if modelo_config.startswith("models/"):
        modelo_config = modelo_config.replace("models/", "")

    return modelo_config


def obter_modelo_chat():
    """Normaliza o modelo de chat para um valor compativel com Gemini API."""
    modelo_config = config.GOOGLE_CHAT_MODEL.strip()
    if modelo_config.startswith("models/"):
        modelo_config = modelo_config.replace("models/", "")

    return modelo_config

def consultar_IA_com_retry(
        vector_store, pergunta, tentativas_maximas=3, espera_segundos=5
    ):
    """Consulta o Gemini com mecanismo de tentativa automática caso ocorra erro 429."""
    llm = ChatGoogleGenerativeAI(
        model=obter_modelo_chat(),
        temperature=0.1,
        max_retries=3,  # O próprio LangChain tentará refazer a requisição em caso de erro temporário!
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", carregar_system_prompt()),
            ("system", "Contexto: \n{context}"),
            ("human", "{input}"),
        ])

    question_answer_chain = create_stuff_documents_chain(llm, prompt)
    retriever = vector_store.as_retriever(search_kwargs={"k": config.RETRIEVAL_K})
    rag_chain = create_retrieval_chain(retriever, question_answer_chain)

    for tentativa in range(1, tentativas_maximas + 1):
        try:
            print(
                f"🤖 Consultando IA (Tentativa {tentativa}/{tentativas_maximas})..."
            )
            resposta = rag_chain.invoke({"input": pergunta})
            return resposta["answer"]
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print(
                    f"⚠️ Limite de cota atingido. Aguardando"
                    f" {espera_segundos}s para tentar novamente..."
                )
                time.sleep(espera_segundos)
            else:
                # Se for outro erro diferente de cota, interrompe
                raise e

    raise RuntimeError(
        "Não foi possível obter resposta da IA após várias tentativas."
    )

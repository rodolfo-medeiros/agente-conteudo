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
    def buscar_pasta_drive(service, nome_pasta, id_pasta_pai=None):
        """Busca uma pasta pelo nome dentro da pasta pai (retorna o ID ou None)."""
        query = "mimeType='application/vnd.google-apps.folder' and trashed=false"
        if id_pasta_pai:
            query += f" and '{id_pasta_pai}' in parents"
        query += f" and name = '{nome_pasta}'"
        try:
            resposta = (
                service.files()
                .list(q=query, fields="files(id, name)", pageSize=1)
                .execute()
            )
            arquivos = resposta.get("files", [])
            if arquivos:
                return arquivos[0]["id"]
        except HttpError as e:
            print(f"Erro ao buscar pasta: {e}")
        return None

    """Cria uma pasta no Google Drive."""
    print(f"Criando pasta '{nome_pasta}' no Google Drive...")



    # Reaproveita a pasta se ela já existir (evita duplicatas em re-execuções)
    id_existente = buscar_pasta_drive(service, nome_pasta, id_pasta_pai)
    if id_existente:
        print(f"Pasta '{nome_pasta}' já existe; reaproveitando (ID: {id_existente}).")
        return id_existente



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


def upload_arquivo_drive(service, caminho_local, nome_arquivo, mime_type, id_pasta_destino):
    """Faz upload de um arquivo local (ex: PSD do carrossel) para uma pasta do Google Drive."""

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



# ============================================================
# INGESTÃO E PROCESSAMENTO COM RAG (Lang Chain + Gemini)
# ============================================================

def obter_ou_criar_vectorstore(caminho_pasta="knowledge_base"):
    """Carrega o banco vetorial sincronizando com os PDFs da knowledge_base.

    - Banco inexistente/vazio -> indexa todos os PDFs da pasta.
    - Banco existente -> sincroniza: remove PDFs apagados, reindexa
      alterados (por hash de conteúdo) e mantém os inalterados sem custo.
    """
    embeddings = GoogleGenerativeAIEmbeddings(model=obter_modelo_embedding())

    pdfs_atuais = {
        os.path.basename(caminho): caminho
        for caminho in glob.glob(os.path.join(caminho_pasta, "*.pdf"))
    }

    banco_existe = os.path.exists(config.PASTA_CHROMA) and os.listdir(config.PASTA_CHROMA)

    if not banco_existe:
        print("Banco vetorial não encontrado. Indexando a knowledge_base...")
        vector_store = Chroma(
            embedding_function=embeddings,
            persist_directory=config.PASTA_CHROMA,
        )
        for nome, caminho in sorted(pdfs_atuais.items()):
            _indexar_pdf(vector_store, caminho, nome, _hash_arquivo(caminho))
        print("✅ Banco vetorial criado com sucesso!")
        return vector_store

    print("Carregando banco vetorial do disco e sincronizando com a pasta...")
    vector_store = Chroma(
        persist_directory=config.PASTA_CHROMA,
        embedding_function=embeddings,
    )

    # O que já está indexado: {nome_do_pdf: hash_do_conteudo}
    indexados = {}
    registro = vector_store.get(include=["metadatas"])
    for meta in registro.get("metadatas") or []:
        if meta and meta.get("source_pdf"):
            indexados[meta["source_pdf"]] = meta.get("file_hash")

    # 1) PDFs que saíram da pasta -> apaga do índice
    for nome in sorted(set(indexados) - set(pdfs_atuais)):
        print(f"🗑️ PDF removido da base, apagando do banco vetorial: {nome}")
        _apagar_pdf_do_indice(vector_store, nome)

    # 2) PDFs novos ou alterados -> (re)indexa
    for nome, caminho in sorted(pdfs_atuais.items()):
        hash_atual = _hash_arquivo(caminho)
        if indexados.get(nome) == hash_atual:
            continue  # inalterado: zero custo de embedding
        if nome in indexados:
            print(f"♻️ PDF alterado, reindexando: {nome}")
            _apagar_pdf_do_indice(vector_store, nome)
        else:
            print(f"🆕 Novo PDF, indexando: {nome}")
        _indexar_pdf(vector_store, caminho, nome, hash_atual)

    return vector_store


def _hash_arquivo(caminho):
    """MD5 do conteúdo (detecta alterações mesmo mantendo o mesmo nome)."""
    import hashlib
    h = hashlib.md5()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _apagar_pdf_do_indice(vector_store, nome_pdf):
    """Apaga todos os chunks de um PDF do banco vetorial."""
    ids = vector_store.get(where={"source_pdf": nome_pdf}).get("ids", [])
    if ids:
        vector_store.delete(ids)


def _indexar_pdf(vector_store, caminho_pdf, nome_arquivo, hash_arquivo):
    """Carrega, fatia e indexa um PDF com metadados de controle."""
    loader = PyMuPDFLoader(caminho_pdf)
    documentos = loader.load()

    for doc in documentos:
        doc.metadata["source_pdf"] = nome_arquivo
        doc.metadata["file_hash"] = hash_arquivo

    chunks = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP
    ).split_documents(documentos)

    vector_store.add_documents(chunks)
    print(f"   📄 {nome_arquivo}: {len(chunks)} trechos indexados.")



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

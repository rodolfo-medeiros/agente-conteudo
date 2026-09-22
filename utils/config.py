import os 
from dotenv import load_dotenv

load_dotenv()

#API KEYS

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

# Modelos
GOOGLE_EMBEDDING_MODEL = os.getenv("GOOGLE_EMBEDDING_MODEL", "")
GOOGLE_CHAT_MODEL = os.getenv("GOOGLE_CHAT_MODEL", "")
GOOGLE_ROTEIRO_MODEL = os.getenv("GOOGLE_ROTEIRO_MODEL", "")

# Modelo de reserva dos roteiros (quando o principal estiver sobrecarregado).
# Vazio = usa o GOOGLE_CHAT_MODEL.
GOOGLE_ROTEIRO_MODEL_FALLBACK = os.getenv("GOOGLE_ROTEIRO_MODEL_FALLBACK", "")

# Caminhos
PASTA_CHROMA = "./chroma_db_gemini"
SYSTEM_PROMPT_PATH = "system_prompt_token.md"

# Google Drive
OAUTH_CREDENTIALS = "oauth_credentials.json"
TOKEN_CACHE = ".token_cache.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# RAG
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
RETRIEVAL_K = 3
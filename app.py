"""Painel de controle do Agente de Conteúdo Token.

Interface Streamlit que gerencia a base de conhecimento, o system prompt
e os modelos — e executa o main.py como subprocesso (o pipeline continua
idêntico ao do terminal).

Como rodar:
    venv\\Scripts\\streamlit run app.py
"""

import os 
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).parent
PASTA_KB = RAIZ / "knowledge_base"
ARQ_PROMPT = RAIZ / "system_prompt_token.md"
ARQ_ENV = RAIZ / ".env"
PYTHON = RAIZ / "venv" / "Scripts" / "python.exe"
LOCKFILE = RAIZ / ".pipeline_em_execucao.lock"

st.set_page_config(
    page_title="Agente de Conteúdo Token",
    page_icon="🚀",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def pipeline_em_execucao():
    """True se já existe uma execução em andamento (lockfile vivo)."""
    if not LOCKFILE.exists():
        return False
    try:
        pid = int(LOCKFILE.read_text().strip() or "0")
        os.kill(pid,0) # levanta exceção se o processo não existe
        return True
    except(ValueError,PermissionError):
        return True
    except (ProcessLookupError, OSError):
        LOCKFILE.unlink(missing_ok=True)
        return False



def ler_env():
    """Lê o .env como dicionário ordenado (sem expor valores completos)."""
    dados = {}
    if ARQ_ENV.exists():
        for linha in ARQ_ENV.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                chave, _, valor = linha.partition("=")
                dados[chave.strip()] = valor.strip().strip('"')
    return dados

def salvar_env(atualizacoes):
    """Atualiza chaves específicas do .env preservando o restante do arquivo."""
    if ARQ_ENV.exists():
        linhas = ARQ_ENV.read_text(encoding="utf-8").splitlines()
    else:
        linhas = []
    feitas = set()
    novas = []
    for linha in linhas:
        chave = linha.partition("=")[0].strip()
        if chave in atualizacoes:
            novas.append(f"{chave}={atualizacoes[chave]}")
            feitas.add(chave)
        else:
            novas.append(linha)
    for chave, valor in atualizacoes.items():
        if chave not in feitas:
            novas.append(f"{chave}={valor}")
    ARQ_ENV.write_text("\n".join(novas) + "\n", encoding="utf-8")
    st.cache_data.clear()


def validar_conteudo_prompt(texto):
    """Verifica se os elementos obrigatórios do contrato com os parsers estão presentes."""
    obrigatorios = [
        "## 📅 Semana 1", "### Conteúdo",
        "Título", "Ideia de conteúdo", "Fio condutor",
    ]
    return [item for item in obrigatorios if item not in texto]

# ---------------------------------------------------------------------------
# Preview de sincronização (lógica espelhada de utils/functions.py)
# ---------------------------------------------------------------------------

def hash_arquivo(caminho):
    import hashlib
    h = hashlib.md5()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()



@st.cache_data(ttl=30)
def preview_sincronizacao():
    """Compara knowledge_base/ com o registro no ChromaDB (metadados file_hash)."""
    import chromadb
    persist = RAIZ / "chroma_db_gemini"
    pdfs = {p.name: hash_arquivo(p) for p in PASTA_KB.glob("*.pdf")}

    indexados = {}
    if persist.exists() and any(persist.iterdir()):
        try:
            cliente = chromadb.PersistentClient(path=str(persist))
            colecao = cliente.get_collection("langchain")
            registro = colecao.get(include=["metadatas"])
            for meta in registro.get("metadatas") or []:
                if meta and meta.get("source_pdf"):
                    indexados[meta["source_pdf"]] = meta.get("file_hash")
        except Exception:
            pass  # banco vazio/corrompido: tudo será considerado novo


    novos = [n for n in pdfs if n not in indexados]
    alterados = [n for n in pdfs if n in indexados and indexados[n] != pdfs[n]]
    removidos = [n for n in indexados if n not in pdfs]
    iguais = [n for n in pdfs if n in indexados and indexados[n] == pdfs[n]]
    return {"novos": novos, "alterados": alterados,
            "removidos": removidos, "iguais": iguais}

# ---------------------------------------------------------------------------
# Execução do pipeline (subprocesso + leitor em thread)
# ---------------------------------------------------------------------------

def iniciar_pipeline():
    """Dispara o main.py em subprocesso e devolve (processo, leitor de log)."""
    if pipeline_em_execucao():
        return None, "Já existe uma execução em andamento."

    env = os.environ.copy()
    if instrucoes_mes.strip():
        env["INSTRUCOES_DO_MES"] = instrucoes_mes.strip():


    processo = subprocess.Popen(
        [str(PYTHON), str(RAIZ / "main.py")],
        cwd=str(RAIZ),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    LOCKFILE.write_text(str(processo.pid), encoding="utf-8")

    linhas = []
    done = threading.Event()

    def _ler():
        for linha in processo.stdout:
            linhas.append(linha.rstrip())
        done.set()

    threading.Thread(target=_ler, daemon=True).start()
    return processo, (linhas,done)


# ---------------------------------------------------------------------------
# Sidebar — navegação
# ---------------------------------------------------------------------------

aba = st.sidebar.radio(
    "Navegação",
    ["📚 Base de conhecimento", "📝 Instruções", "▶️ Agente", "⚙️ Modelos"]

)
st.sidebar.caption("Token Brand - ENGINE CRIATIVA")

# ===========================================================================
# ABA 1 — BASE DE CONHECIMENTO
# ===========================================================================
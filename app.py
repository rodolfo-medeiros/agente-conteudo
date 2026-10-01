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
import ctypes
from datetime import datetime
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).parent
PASTA_KB = RAIZ / "knowledge_base"
ARQ_PROMPT = RAIZ / "system_prompt_token.md"
ARQ_ENV = RAIZ / ".env"
PYTHON = RAIZ / "venv" / "Scripts" / "python.exe"
LOCKFILE = RAIZ / ".pipeline_em_execucao.lock"
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259

st.set_page_config(
    page_title="Agente de Conteúdo Token",
    page_icon="🚀",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def _info_processo(pid):
    """(vivo, eh_python) para o pid — via API do Windows, sem efeito colateral."""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False, False  # pid não existe mais
    try:
        codigo = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(codigo))
        vivo = codigo.value == _STILL_ACTIVE

        tamanho = ctypes.c_ulong(512)
        buffer = ctypes.create_unicode_buffer(512)
        kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(tamanho))
        eh_python = buffer.value.lower().endswith("python.exe")
        return vivo, eh_python
    finally:
        kernel32.CloseHandle(handle)


def pipeline_em_execucao():
    """True se já existe uma execução do pipeline em andamento.
    """
    if not LOCKFILE.exists():
        return False
    try:
        pid = int(LOCKFILE.read_text().strip() or "0")
    except ValueError:
        LOCKFILE.unlink(missing_ok=True)
        return False

    vivo, eh_python = _info_processo(pid)
    if vivo and eh_python:  # vivo E é um python nosso -> execução real em curso
        return True

    LOCKFILE.unlink(missing_ok=True)  # lock stale (processo morto/pid reciclado)
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

def iniciar_pipeline(instrucoes_mes):
    """Dispara o main.py em subprocesso e devolve (processo, leitor de log)."""
    if pipeline_em_execucao():
        return None, "Já existe uma execução em andamento."

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"  # subprocesso imprime em UTF-8 (evita cp1252)
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"            # modo UTF-8 global do Python filho
    if instrucoes_mes.strip():
        env["INSTRUCOES_DO_MES"] = instrucoes_mes.strip()


    processo = subprocess.Popen(
        [str(PYTHON), "-u", str(RAIZ / "main.py")],
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

if aba == "📚 Base de conhecimento":
    st.header("📚 Base de conhecimento")
    st.caption(
        "Os PDFs desta pasta alimentam a agenda via RAG. A sincronização com o "
        "banco vetorial acontece no próximo play (por hash de conteúdo)."
    )

    PASTA_KB.mkdir(exist_ok=True)
    pdfs = sorted(PASTA_KB.glob("*pdf"))
    sinc = preview_sincronizacao()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🆕 Novos", len(sinc["novos"]))
    c2.metric("♻️ Alterados", len(sinc["alterados"]))
    c3.metric("🗑️ A remover", len(sinc["removidos"]))
    c4.metric("✅ Inalterados", len(sinc["iguais"]))

    st.subheader("Arquivos")
    if not pdfs:
        st.into("Nenhum pdf na abse. Envie pelo menos um.")
    for pdf in pdfs:
        col_a, col_b = st.columns([4,1])
        col_a.write(f"📄 **{pdf.name}** — {pdf.stat().st_size / 1024:.0f} KB")
        if col_b.button("Remover", key=f"rm_{pdf.name}"):
            pdf.unlink()
            st.cache_data.clear()
            st.rerun()

    st.subheader("Enviar novos PDF´s")
    updloads = st.file_uploader("Selecione (pode enviar vários)", type = "pdf",
                                accept_multiple_files=True)
    if updloads and st.button("Adicionar a base"):
        for up in updloads:
            destino = PASTA_KB / up.name.replace("/","_")
            destino.write_bytes(up.getbuffer())
        st.cache_data.clear()
        st.success(f"{len(updloads)} arquivos(s) adicionados (s)!")

# ===========================================================================
# ABA 2 — INSTRUÇÕES (system prompt)
# ===========================================================================

elif aba == "📝 Instruções":
    st.header("📝 Instruções do agente (system prompt)")
    st.warning(
        "⚠️ A **seção 10 (formato de saída)** é o contrato entre a IA e o código. "
        "Alterar cabeçalhos, rótulos ou distribuição ali **quebra os parsers**.",
        icon="🚨",
    )

    if not ARQ_PROMPT.exists():
        st.error("system_prompt_token.md não encontrado na raiz")
        st.stop()

    texto = st.text_area(
        "Conteúdo do system_prompt_token.md",
        value= ARQ_PROMPT.read_text(encoding="utf-8"),
        height=560,
    )

    if st.button("💾 Salvar (com backup da versão atual)"):
        faltando = validar_conteudo_prompt(texto)
        if faltando:
            st.error(
                "Salvamento bloqueado - elementos obrigatórios ausentes: "
                + ", ".join(f"`{f}`" for f in faltando)

            )
        else:
            backup = RAIZ / (
                "system_prompt_token.bak_"
                + datetime.now().strftime("%Y-%m-%d-%H%M") + ".md"

            )
            shutil.copy2(ARQ_PROMPT,backup)
            ARQ_PROMPT.write_text(texto, encoding="utf-8")
            st.success(f"Salvo! Backup anterior em `{backup.name}`.")



# ===========================================================================
# ABA 3 — AGENTE (play)
# ===========================================================================    

elif aba == "▶️ Agente":
    st.header("▶️ Executar o agente")

    if pipeline_em_execucao():
        st.info("⏳ O pipeline está em execução (ou o Photoshop está aberto). "
                "Aguarde a finalização antes de rodar novamente.")
    instrucoes_mes = st.text_area(
         "📝 Instruções do mês (opcional)",
        placeholder="Ex.: 'agosto tem o evento X no dia 15; priorize cafeterias "
                    "e o case do cliente Y no fundo de funil'",
        height=90,

    )

    col_play, col_status = st.columns([1,3])
    if col_play.button("▶️ GERAR AGENDA DO MÊS", type="primary",
                        disabled=pipeline_em_execucao()):
        processo, resultado = iniciar_pipeline(instrucoes_mes)
        if processo is None:
            col_status.error(resultado)
        else:
            st.session_state["log"] = resultado[0]
            st.session_state["done"] = resultado[1]
            st.session_state["processo"] = processo
            col_status.success("Pipeline iniciado! Acompanhe o log abaixo.")

    log = st.session_state.get("log")
    if log is not None:
        done = st.session_state["done"]
        st.subheader("📜 Log em tempo real")
        st.code("\n".join(log[-200:]) or "Aguardando saída...", language=None)
        if done.is_set():
            codigo = st.session_state["processo"].returncode
            if codigo == 0:
                st.success("✅ Pipeline finalizado com sucesso!")
            else:
                st.error(f"❌ Pipeline encerrou com código {codigo}. "
                         "Veja o final do log acima.")
            LOCKFILE.unlink(missing_ok=True)
        else:
            import time
            time.sleep(2)
            st.rerun()


# ===========================================================================
# ABA 4 — MODELOS
# ===========================================================================
else:

    st.header("⚙️ Modelos do Gemini")
    st.caption("Consulta os modelos disponíveis na sua chave e grava a escolha "
               "no .env - evita o erro 404 de modelo aposentado.")
    env = ler_env()

    if st.button("🔄 Listar modelos disponíveis"):
        try:
            import requests
            resposta = requests.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": env.get("GOOGLE_API_KEY", ""), "pageSize": 1000},
                timeout=30,
            ).json()
            disponiveis = sorted(
                m["name"].replace("models/", "")
                for m in resposta.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
                and m["name"].startswith("models/gemini")
            )
            st.session_state["disponiveis"] = disponiveis
        except Exception as e:
            st.error(f"Não foi possível listar: {e}")


    disponiveis = st.session_state.get("disponiveis", [])
    if disponiveis:
        st.info(f"{len(disponiveis)} modelos com generateContent encontrados.")

    def _seletor(label, chave_env, ajuda):
        opcoes = disponiveis or [env.get(chave_env, "")]
        atual = env.get(chave_env, "")
        indice = opcoes.index(atual) if atual in opcoes else 0
        return st.selectbox(label, opcoes, index=indice, help=ajuda)

    st.text_input("Embedding (não altere sem necessidade)",
                  value=env.get("GOOGLE_EMBEDDING_MODEL", ""), disabled=True)
    m_agenda = _seletor("Modelo da AGENDA (GOOGLE_CHAT_MODEL)",
                        "GOOGLE_CHAT_MODEL", "Usado também pelos roteiros "
                        "se o dedicado estiver vazio")
    m_roteiro = _seletor("Modelo dos ROTEIROS (GOOGLE_ROTEIRO_MODEL; "
                         "opcional)", "GOOGLE_ROTEIRO_MODEL",
                         "Vazio = usa o modelo da agenda")
    m_reserva = _seletor("Modelo de RESERVA (GOOGLE_ROTEIRO_MODEL_FALLBACK; "
                         "opcional)", "GOOGLE_ROTEIRO_MODEL_FALLBACK",
                         "Usado em 503/429; vazio = modelo da agenda")

    if st.button("💾 Salvar modelos no .env"):
        salvar_env({
            "GOOGLE_CHAT_MODEL": m_agenda,
            "GOOGLE_ROTEIRO_MODEL": m_roteiro,
            "GOOGLE_ROTEIRO_MODEL_FALLBACK": m_reserva,
        })
        st.success("Modelos gravados no .env! (valem na próxima execução)")



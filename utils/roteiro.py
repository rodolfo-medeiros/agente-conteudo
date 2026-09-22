"""Geração dos roteiros de carrossel (5 slides) a partir da agenda mensal.

Cada semana da agenda contém 3 conteúdos; cada conteúdo vira UM carrossel
de 5 slides — 12 carrosséis por mês.
"""

import re
import time
import unicodedata

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from utils import config
from utils.functions import carregar_system_prompt, obter_modelo_chat

NUM_SLIDES_ESPERADO = 5

# ---------------------------------------------------------------------------
# Instruções do agente (estrutura fixa do roteiro)
# ---------------------------------------------------------------------------

ESTRUTURA_ROTEIRO = """\
Slide 1: Capa (O Gancho)
Título: [título de impacto do carrossel]
Subtítulo: [pergunta ou frase que aprofunda o gancho]

Slide 2: O Problema (O Contexto)
Título: [título sobre o problema/contexto]
Texto: [contexto curto do problema]

Slide 3: O Exemplo (Conexão Cultural)
Título: [título do exemplo cultural]
Texto: [exemplo cultural conectado ao tema]

Slide 4: A Reflexão (O Twist/Insight)
Título: [título da reflexão]
Texto: [insight ou verdade desconfortável]

Slide 5: Fechamento (CTA)
Título: [título do fechamento]
Texto: [fechamento com posicionamento de mercado]
CTA: [chamada para ação objetiva]"""

INSTRUCOES_ROTEIRO = (
    "Você é roteirista de conteúdo para carrosséis de Instagram da Token Brand.\n"
    "ATENÇÃO: esta tarefa NÃO é uma agenda mensal. Ignore o formato de agenda "
    "(seção 10) do prompt de sistema e responda APENAS com o roteiro em slides "
    "conforme a estrutura abaixo.\n\n"
    "Com base no BLOCO DE CONTEÚDO abaixo, crie o roteiro de UM carrossel com "
    "EXATAMENTE 5 slides, seguindo a ESTRUTURA OBRIGATÓRIA.\n\n"
    "REGRAS:\n"
    "- Responda APENAS com o roteiro no formato exato da estrutura (sem introdução, "
    "sem conclusão, sem comentários, sem markdown).\n"
    "- Não use markdown: nada de '#', '**', '-', nem emojis nos rótulos.\n"
    "- Use exatamente os rótulos 'Slide N:', 'Título:', 'Subtítulo:', 'Texto:' e 'CTA:' "
    "no início de suas linhas, sem negrito e sem numeração extra.\n"
    "- O carrossel deve traduzir fielmente ESTE conteúdo: mantenha o gancho cultural "
    "e a Editoria do bloco; não misture outros conteúdos.\n"
    "- Textos curtos e escaneáveis, no estilo carrossel (cada slide = uma ideia).\n\n"
    "- Todos os 5 slides têm 'Título:' — e os slides 2 a 5 também têm 'Texto:'; "
    "nenhum slide pode ficar sem Título.\n"

    "ESTRUTURA OBRIGATÓRIA:\n"
    f"{ESTRUTURA_ROTEIRO}\n\n"
    "BLOCO DE CONTEÚDO:\n{conteudo}"
)

# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

_PADRAO_SLIDE = re.compile(
    r"^Slide\s*(\d+)\s*[:\-–—.]\s*(.*)$", re.MULTILINE | re.IGNORECASE
)
_PADRAO_CAMPOS = re.compile(
    r"^(T[íi]tulo|Subt[íi]tulo|Texto|CTA)\s*:\s*",
    re.MULTILINE | re.IGNORECASE,
)
_PADRAO_CONTEUDO = re.compile(
    r"^#{1,6}\s*(?:\*\*)?Conteúdo\s+(\d+)(?:\s*[—–-]\s*([^\n]+))?",
    re.MULTILINE | re.IGNORECASE,
)


def _limpar(texto):
    """Remove resíduos de markdown (**, #) e espaços extras."""
    return (texto or "").replace("**", "").replace("#", "").strip()

def _reparar_mojibake(texto):
    """Repara caracteres duplamente codificados.

    Caso real: o modelo emite 'SubtÃ­tulo' (o 'í' virou 'Ã' + caractere
    invisível) e o parser não reconhece o rótulo. Aqui decodificamos cada
    par 'Ã + byte' de volta para o acento original.
    """
    if "\u00c3" not in texto:
        return texto

    def _decodificar_par(m):
        try:
            return bytes([ord(m.group(1)), ord(m.group(2))]).decode("utf-8")
        except Exception:
            return m.group(0)

    return re.sub("([\u00c3])([\u0080-\u00bf])", _decodificar_par, texto)



def _normalizar_roteiro(texto):
    """Normaliza a saída do modelo antes do parse.

    - Repara mojibake ('SubtÃ­tulo' -> 'Subtítulo');
    - Aplica NFC (acentos decompostos viram precompostos, resolve o caso
      do 'Título' em NFD);
    - Remove negrito, bullets, cabeçalhos markdown e espaços extras.
    """
    if not texto:
        return ""

    texto = _reparar_mojibake(texto)
    texto = unicodedata.normalize("NFC", texto)

    linhas = []
    for linha in texto.splitlines():
        l = linha.strip()
        l = l.replace("**", "").replace("__", "")
        l = re.sub(r"^#+\s*", "", l)       # cabeçalhos markdown
        l = re.sub(r"^[-*•>]+\s*", "", l)  # bullets/citações
        if l:
            linhas.append(l)
    return "\n".join(linhas)


def extrair_slides(roteiro_texto):
    """Converte o texto do roteiro em lista de slides estruturados.

    Retorna lista de dicts: {numero, rotulo, titulo, subtitulo, texto, cta}
    """
    texto = _normalizar_roteiro(roteiro_texto)
    slides = []
    cabecalhos = list(_PADRAO_SLIDE.finditer(texto))

    for i, cabecalho in enumerate(cabecalhos):
        inicio = cabecalho.end()
        fim = cabecalhos[i + 1].start() if i + 1 < len(cabecalhos) else len(texto)
        bloco = texto[inicio:fim]

        campos = {}
        matches = list(_PADRAO_CAMPOS.finditer(bloco))
        for j, m in enumerate(matches):
            # 'Título' -> 'titulo' | 'Subtítulo' -> 'subtitulo'
            chave = m.group(1).lower().replace("í", "i")
            c_inicio = m.end()
            c_fim = matches[j + 1].start() if j + 1 < len(matches) else len(bloco)
            campos[chave] = _limpar(bloco[c_inicio:c_fim])

        slides.append(
            {
                "numero": int(cabecalho.group(1)),
                "rotulo": _limpar(cabecalho.group(2)),
                "titulo": campos.get("titulo", ""),
                "subtitulo": campos.get("subtitulo", ""),
                "texto": campos.get("texto", ""),
                "cta": campos.get("cta", ""),
            }
        )

    return slides


def extrair_conteudos(conteudo_semana):
    """Extrai os blocos '### Conteúdo N — Editoria' de uma semana.

    Retorna lista de dicts: {numero, editoria, texto}
    """
    conteudos = []
    cabecalhos = list(_PADRAO_CONTEUDO.finditer(conteudo_semana or ""))

    for i, cabecalho in enumerate(cabecalhos):
        inicio = cabecalho.start()
        fim = (
            cabecalhos[i + 1].start()
            if i + 1 < len(cabecalhos)
            else len(conteudo_semana)
        )
        conteudos.append(
            {
                "numero": int(cabecalho.group(1)),
                "editoria": _limpar(cabecalho.group(2) or ""),
                "texto": conteudo_semana[inicio:fim].strip(),
            }
        )

    return conteudos


def formatar_secao_roteiro(roteiro_texto, numero_conteudo=None, editoria=None):
    """Formata a seção do roteiro de um conteúdo para Docs/arquivo local."""
    cabecalho = "## 📱 Roteiro do Carrossel"
    if numero_conteudo:
        cabecalho += f" — Conteúdo {numero_conteudo}"
        if editoria:
            cabecalho += f" ({editoria})"
    return f"{cabecalho}\n\n{_limpar(roteiro_texto)}"


def _extrair_texto_resposta(resposta):
    """Extrai o texto da resposta do modelo (str ou lista de blocos de conteúdo)."""
    conteudo = resposta.content

    if isinstance(conteudo, str):
        return conteudo.strip()

    if isinstance(conteudo, list):
        partes = []
        for bloco in conteudo:
            if isinstance(bloco, str):
                partes.append(bloco)
            elif isinstance(bloco, dict) and isinstance(bloco.get("text"), str):
                partes.append(bloco["text"])
            elif hasattr(bloco, "text") and isinstance(getattr(bloco, "text"), str):
                partes.append(bloco.text)
        return "\n".join(partes).strip()

    return str(conteudo).strip()


def _registrar_erro_formato(numero_conteudo, texto, motivo):
    """Salva a resposta bruta do modelo para diagnóstico quando o formato falha."""
    try:
        with open("debug_roteiros_com_erro.txt", "a", encoding="utf-8") as f:
            f.write(
                f"\n{'=' * 70}\nConteúdo {numero_conteudo} — {motivo}\n"
                f"{'-' * 70}\n{texto}\n"
            )
        print(f"   🐛 Resposta salva em debug_roteiros_com_erro.txt ({motivo})")
    except Exception:
        pass


def _obter_modelo_roteiro():
    """Modelo de roteiro: usa GOOGLE_ROTEIRO_MODEL (se definido no .env),
    senão cai no GOOGLE_CHAT_MODEL."""
    modelo = (getattr(config, "GOOGLE_ROTEIRO_MODEL", "") or config.GOOGLE_CHAT_MODEL)
    modelo = modelo.strip()
    if modelo.startswith("models/"):
        modelo = modelo.replace("models/", "")
    return modelo


def _obter_modelo_fallback():
    """Modelo de reserva quando o principal estiver sobrecarregado/indisponível.
    Padrão: GOOGLE_CHAT_MODEL (o mesmo da agenda, que já funciona)."""
    modelo = (
        getattr(config, "GOOGLE_ROTEIRO_MODEL_FALLBACK", "")
        or config.GOOGLE_CHAT_MODEL
    )
    modelo = modelo.strip()
    if modelo.startswith("models/"):
        modelo = modelo.replace("models/", "")
    return modelo


_ERROS_TRANSITORIOS = (
    "429", "RESOURCE_EXHAUSTED",        # cota
    "500", "503", "UNAVAILABLE",        # sobrecarga/indisponibilidade
    "OVERLOADED", "overloaded", "high demand", "DEADLINE_EXCEEDED",
)


def _eh_erro_transitorio(erro):
    """True para erros que valem nova tentativa (cota, sobrecarga, timeout)."""
    texto = str(erro)
    return any(termo in texto for termo in _ERROS_TRANSITORIOS)


# ---------------------------------------------------------------------------
# Geração via Gemini
# ---------------------------------------------------------------------------

def gerar_roteiro_conteudo(
    numero_conteudo,
    editoria,
    texto_conteudo,
    vector_store=None,
    tentativas_maximas=3,
    espera_segundos=5,
):
    """Gera o roteiro do carrossel de UM conteúdo da agenda.

    Estratégia: tenta o modelo principal; em caso de sobrecarga (503 etc.),
    formato inválido ou cota, repete com backoff progressivo e, se esgotar,
    troca automaticamente para o modelo de reserva.

    Retorna a tupla (roteiro_texto, slides).
    """
    print(f"🎬 Gerando roteiro do Conteúdo {numero_conteudo}...")

    bloco = f"Conteúdo {numero_conteudo}"
    if editoria:
        bloco += f" — {editoria}"
    bloco += f"\n\n{texto_conteudo}"

    instrucoes = INSTRUCOES_ROTEIRO.format(conteudo=bloco)

    # Contexto adicional da base de conhecimento (RAG), se disponível
    if vector_store is not None:
        try:
            docs = vector_store.as_retriever(
                search_kwargs={"k": config.RETRIEVAL_K}
            ).invoke(texto_conteudo[:500])
            contexto = "\n\n".join(d.page_content for d in docs)
            if contexto.strip():
                instrucoes += f"\n\nCONTEXTO ADICIONAL DA MARCA:\n{contexto}"
        except Exception as e:
            print(f"⚠️ Não foi possível usar a base de conhecimento como contexto: {e}")

    mensagens = [
        SystemMessage(content=carregar_system_prompt()),
        HumanMessage(content=instrucoes),
    ]

    # Cadeia de modelos: principal -> reserva (se diferente)
    modelos = [_obter_modelo_roteiro()]
    modelo_reserva = _obter_modelo_fallback()
    if modelo_reserva and modelo_reserva not in modelos:
        modelos.append(modelo_reserva)

    ultimo_erro = None

    for indice, nome_modelo in enumerate(modelos):
        llm = ChatGoogleGenerativeAI(model=nome_modelo, max_retries=2)

        for tentativa in range(1, tentativas_maximas + 1):
            try:
                print(
                    f"🤖 Gerando roteiro com '{nome_modelo}' "
                    f"(Tentativa {tentativa}/{tentativas_maximas})..."
                )
                resposta = llm.invoke(mensagens)
                resposta_bruta = _extrair_texto_resposta(resposta)
                roteiro_texto = _normalizar_roteiro(_extrair_texto_resposta(resposta))

                slides = extrair_slides(roteiro_texto)
                if len(slides) != NUM_SLIDES_ESPERADO:
                    motivo = f"{len(slides)} slides (esperados 5)"
                    _registrar_erro_formato(numero_conteudo, resposta_bruta, motivo)
                    raise ValueError(
                        f"O roteiro veio com {motivo}. Início da resposta: "
                        f"\"{roteiro_texto[:300]}\""
                    )

                # Validação mínima dos campos por tipo de slide
                faltando = [
                    s["numero"]
                    for s in slides
                    if not s["titulo"]
                    or (s["numero"] == 1 and not s["subtitulo"])
                    or (s["numero"] in (2, 3, 4) and not s["texto"])
                    or (s["numero"] == 5 and not (s["texto"] or s["cta"]))
                ]
                if faltando:
                    motivo = f"campos faltando nos slides {faltando}"
                    _registrar_erro_formato(numero_conteudo, resposta_bruta, motivo)
                    raise ValueError(
                        f"{motivo}. Início da resposta: \"{roteiro_texto[:300]}\""
                    )

                return roteiro_texto, slides

            except Exception as e:
                ultimo_erro = e
                transitorio = _eh_erro_transitorio(e)

                if transitorio or isinstance(e, ValueError):
                    if transitorio:
                        motivo = "Serviço sobrecarregado/indisponível"
                        espera = espera_segundos * tentativa  # backoff progressivo
                    else:
                        motivo = "Formato inválido"
                        espera = espera_segundos
                    print(
                        f"⚠️ {motivo} ('{nome_modelo}'); aguardando {espera}s e "
                        f"tentando novamente ({tentativa}/{tentativas_maximas})..."
                    )
                    time.sleep(espera)
                else:
                    raise  # erro permanente (chave inválida, permissão etc.)

        if indice + 1 < len(modelos):
            print(f"🔁 '{nome_modelo}' falhou; trocando para o modelo de reserva...")

    raise RuntimeError(
        "Não foi possível gerar o roteiro após várias tentativas. "
        f"Último erro: {ultimo_erro}"
    )

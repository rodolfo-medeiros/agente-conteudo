"""Geração do roteiro de carrossel (5 slides) para cada semana da agenda.

Estrutura fixa do carrossel:
    Slide 1: Capa (O Gancho)              -> Título + Subtítulo
    Slide 2: O Problema (O Contexto)      -> Título + Texto
    Slide 3: O Exemplo (Conexão Cultural) -> Título + Texto
    Slide 4: A Reflexão (O Twist/Insight) -> Título + Texto
    Slide 5: Fechamento (CTA)             -> Título + Texto + CTA
"""

import re
import time

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
Texto: [exemplo cultural conectado ao tema da semana]

Slide 4: A Reflexão (O Twist/Insight)
Título: [título da reflexão]
Texto: [insight ou verdade desconfortável]

Slide 5: Fechamento (CTA)
Título: [título do fechamento]
Texto: [fechamento com posicionamento de mercado]
CTA: [chamada para ação objetiva]"""

INSTRUCOES_ROTEIRO = (
    "Você é roteirista de conteúdo para carrosséis de Instagram da Token Brand.\n"
    "Com base no CONTEÚDO DA SEMANA abaixo, crie o roteiro de UM carrossel com "
    "EXATAMENTE 5 slides, seguindo a ESTRUTURA OBRIGATÓRIA.\n\n"
    "REGRAS:\n"
    "- Responda APENAS com o roteiro no formato exato da estrutura (sem introdução, "
    "sem conclusão, sem comentários).\n"
    "- Não use markdown: nada de '#', '**', '-', nem emojis nos rótulos.\n"
    "- Use exatamente os rótulos 'Slide N:', 'Título:', 'Subtítulo:', 'Texto:' e 'CTA:'.\n"
    "- Textos curtos e escaneáveis, no estilo carrossel (cada slide = uma ideia).\n\n"
    "ESTRUTURA OBRIGATÓRIA:\n"
    f"{ESTRUTURA_ROTEIRO}\n\n"
    "CONTEÚDO DA SEMANA:\n{conteudo_semana}"
)

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_PADRAO_SLIDE = re.compile(
    r"^Slide\s*(\d+)\s*:\s*(.*)$", re.MULTILINE | re.IGNORECASE
)
_PADRAO_CAMPOS = re.compile(
    r"^(T[íi]tulo|Subt[íi]tulo|Texto|CTA)\s*:\s*",
    re.MULTILINE | re.IGNORECASE,
)


def _limpar(texto):
    """Remove resíduos de markdown (**, #) e espaços extras."""
    return (texto or "").replace("**", "").replace("#", "").strip()


def extrair_slides(roteiro_texto):
    """Converte o texto do roteiro em lista de slides estruturados.

    Retorna lista de dicts:
        {numero, rotulo, titulo, subtitulo, texto, cta}
    """
    slides = []
    cabecalhos = list(_PADRAO_SLIDE.finditer(roteiro_texto or ""))

    for i, cabecalho in enumerate(cabecalhos):
        inicio = cabecalho.end()
        fim = (
            cabecalhos[i + 1].start()
            if i + 1 < len(cabecalhos)
            else len(roteiro_texto)
        )
        bloco = roteiro_texto[inicio:fim]

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


def formatar_secao_roteiro(roteiro_texto):
    """Formata a seção do roteiro para inserir nos documentos/arquivo local."""
    return f"## 📱 Roteiro do Carrossel\n\n{_limpar(roteiro_texto)}"


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





# ---------------------------------------------------------------------------
# Geração via Gemini
# ---------------------------------------------------------------------------

def gerar_roteiro_semana(
    conteudo_semana, vector_store=None, tentativas_maximas=3, espera_segundos=5
):
    """Gera o roteiro do carrossel de uma semana.

    Retorna a tupla (roteiro_texto, slides):
        roteiro_texto: texto bruto no formato fixo (para Docs/arquivo local)
        slides: lista estruturada (para o gerador de PSD)
    """
    print("🎬 Gerando roteiro do carrossel...")

    instrucoes = INSTRUCOES_ROTEIRO.format(conteudo_semana=conteudo_semana)

    # Contexto adicional da base de conhecimento (RAG), se disponível
    if vector_store is not None:
        try:
            docs = vector_store.as_retriever(
                search_kwargs={"k": config.RETRIEVAL_K}
            ).invoke(conteudo_semana[:500])
            contexto = "\n\n".join(d.page_content for d in docs)
            if contexto.strip():
                instrucoes += f"\n\nCONTEXTO ADICIONAL DA MARCA:\n{contexto}"
        except Exception as e:
            print(f"⚠️ Não foi possível usar a base de conhecimento como contexto: {e}")

    llm = ChatGoogleGenerativeAI(
        model=obter_modelo_chat(),
        temperature=0.4,
        max_retries=2,
    )

    mensagens = [
        SystemMessage(content=carregar_system_prompt()),
        HumanMessage(content=instrucoes),
    ]

    for tentativa in range(1, tentativas_maximas + 1):
        try:
            print(f"🤖 Gerando roteiro (Tentativa {tentativa}/{tentativas_maximas})...")
            resposta = llm.invoke(mensagens)
            roteiro_texto = _extrair_texto_resposta(resposta)

            slides = extrair_slides(roteiro_texto)
            if len(slides) != NUM_SLIDES_ESPERADO:
                raise ValueError(
                    f"O roteiro veio com {len(slides)} slides; esperados 5."
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
                raise ValueError(f"Campos faltando nos slides: {faltando}")

            return roteiro_texto, slides
        except Exception as e:
            erro_cota = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            if erro_cota or isinstance(e, ValueError):
                motivo = "Cota atingida" if erro_cota else "Formato inválido"
                print(
                    f"⚠️ {motivo}; aguardando {espera_segundos}s e tentando "
                    f"novamente ({tentativa}/{tentativas_maximas})..."
                )
                time.sleep(espera_segundos)
            else:
                raise

    raise RuntimeError("Não foi possível gerar o roteiro após várias tentativas.")
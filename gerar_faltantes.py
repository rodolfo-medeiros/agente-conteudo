"""Recupera roteiros/PSDs faltantes a partir do resumo local.

- Reaproveita do resumo os roteiros que já vieram bons;
- Gera (via Gemini) apenas os que falharam;
- Cria os PSDs que ainda não existem localmente;
- Não refaz a agenda e não publica nada no Drive.

Como rodar:
    venv\\Scripts\\python gerar_faltantes.py
"""

import glob
import os
import re

from utils.roteiro import extrair_conteudos, extrair_slides, gerar_roteiro_conteudo
from utils.gerador_psd import gerar_psd_carrossel

ARQUIVO_RESUMO = ""   # vazio = usa o resumo mais recente da raiz
PASTA_SAIDA = ""      # vazio = output_psd/MM-AAAA do resumo


def _resumo_mais_recente():
    resumos = sorted(glob.glob("resumo_IA_*.txt"))
    return resumos[-1] if resumos else None


ARQUIVO_RESUMO = ARQUIVO_RESUMO or _resumo_mais_recente()
if not ARQUIVO_RESUMO:
    raise SystemExit("❌ Nenhum resumo_IA_*.txt encontrado na raiz.")

m = re.search(r"resumo_IA_(\d{4})-(\d{2})-\d{2}", ARQUIVO_RESUMO)
if not PASTA_SAIDA:
    PASTA_SAIDA = os.path.join("output_psd", f"{m.group(2)}-{m.group(1)}")

print(f"📄 Resumo: {ARQUIVO_RESUMO} | Saída: {PASTA_SAIDA}")

texto = open(ARQUIVO_RESUMO, encoding="utf-8").read()

# Separa a agenda das seções de roteiro
marcador = "## 📱 Roteiro do Carrossel"
agenda, _, resto = texto.partition(marcador)

# Roteiros já gerados: {numero_conteudo: texto}
roteiros_salvos = {}
for parte in (marcador + resto).split(marcador)[1:]:
    corte = re.search(r"^## ", parte, re.MULTILINE)
    trecho = (parte[: corte.start()] if corte else parte).strip()
    mm = re.match(r"\s*[—–-]?\s*Conteúdo\s+(\d+)", trecho)
    if mm:
        roteiros_salvos[int(mm.group(1))] = trecho

# Conteúdos da agenda (blocos '### Conteúdo N — editoria')
conteudos = []
semanas_txt = re.split(
    r"^#{1,6}\s*(?:📅\s*)?Semana\s+\d+.*$", agenda,
    flags=re.MULTILINE | re.IGNORECASE,
)[1:]
for semana_txt in semanas_txt:
    conteudos.extend(extrair_conteudos(semana_txt))

# Base vetorial opcional (contexto para os roteiros que precisarem gerar)
vectorstore = None
try:
    from utils import config
    from utils.functions import obter_ou_criar_vectorstore
    if os.path.exists(config.PASTA_CHROMA) and os.listdir(config.PASTA_CHROMA):
        vectorstore = obter_ou_criar_vectorstore()
except Exception as e:
    print(f"(sem base vetorial para contexto: {e})")

os.makedirs(PASTA_SAIDA, exist_ok=True)

falhas = []
for conteudo in conteudos:
    numero = conteudo["numero"]

    if numero in roteiros_salvos:
        slides = extrair_slides(roteiros_salvos[numero])
        origem = "reaproveitado do resumo"
    else:
        print(f"\n🎬 Conteúdo {numero} sem roteiro — gerando agora...")
        try:
            roteiro_texto, slides = gerar_roteiro_conteudo(
                numero, conteudo["editoria"], conteudo["texto"], vectorstore
            )
        except Exception as e:
            print(f"❌ Conteúdo {numero}: {e}")
            falhas.append(numero)
            continue
        origem = "gerado agora"
        with open(ARQUIVO_RESUMO, "a", encoding="utf-8") as f:
            cab = f"## 📱 Roteiro do Carrossel — Conteúdo {numero}"
            if conteudo["editoria"]:
                cab += f" ({conteudo['editoria']})"
            f.write(f"\n\n{cab}\n\n{roteiro_texto}")

    if len(slides) != 5:
        print(f"⚠️ Conteúdo {numero}: {len(slides)} slides inválidos; PSD pulado.")
        falhas.append(numero)
        continue

    caminho_psd = os.path.join(PASTA_SAIDA, f"Conteudo {numero:02d}.psd")
    if os.path.exists(caminho_psd):
        print(f"✅ Conteúdo {numero}: PSD já existe; pulando ({origem}).")
        continue
    try:
        gerar_psd_carrossel(slides, caminho_psd, f"Carrossel Conteudo {numero}")
    except Exception as e:
        print(f"❌ PSD do Conteúdo {numero}: {e}")
        falhas.append(numero)

print("\n🏁 Recuperação concluída!"
      + (f" Faltantes remanescentes: {falhas}" if falhas else ""))
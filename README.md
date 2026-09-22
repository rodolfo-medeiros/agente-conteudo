# 📄 `README.md` — Agente de Conteúdo Token

```markdown

# 🚀 Agente de Conteúdo Token — ENGINE CRIATIVA

Sistema de **automação de conteúdo** para a **Token Brand**: a partir de uma base
de conhecimento em PDFs, ele gera a **agenda mensal** (12 conteúdos), cria os
**roteiros de carrossel** (12 carrosséis de 5 slides), publica tudo no
**Google Drive** e monta os **PSDs editáveis no Photoshop** — prontos para o
time de design finalizar e postar no Instagram.

---

## ⚙️ O pipeline (um comando, 5 etapas)

```
python main.py
   │
   ├─ 1. AGENDA ────── RAG (ChromaDB + embeddings Gemini) → agenda mensal:
   │                    12 conteúdos (10 topo de funil + 2 fundo), divididos
   │                    em 4 semanas (3 + 3 + 3 + 3)
   │
   ├─ 2. ROTEIROS ──── 1 roteiro de carrossel (5 slides) por conteúdo
   │                    = 12 roteiros/mês
   │
   ├─ 3. GOOGLE DRIVE ─ pasta do mês com "Resumo Completo" + Doc por semana
   │                    (agenda + roteiros) — somente Google Docs
   │
   ├─ 4. PSDs ────────── 12 arquivos 5400×1350 px (5 quadrantes de 1080×1350,
   │                    formato carrossel Instagram 4:5) gerados no Photoshop,
   │                    com guias e camadas de TEXTO editáveis
   │
   └─ 5. UPLOAD ──────── PSDs enviados para a subpasta "MM-AAAA-CARROSEIS"
```

Depois disso entra o **trabalho humano**: revisão dos Docs no Drive e
finalização do design dos PSDs no Photoshop.

---

## 🧰 Stack

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3 (Windows) |
| RAG / LLM | LangChain + Google Gemini (agenda, roteiros e embeddings) |
| Vector Store | ChromaDB persistente (com sincronização automática por hash) |
| PDFs | PyMuPDF (parser) |
| Google Drive | Google API (`google-api-python-client`, OAuth2 conta pessoal) |
| Photoshop | `photoshop-python-api` (COM — requer Photoshop instalado) |
| Config | `python-dotenv` |

---

## 📂 Estrutura do projeto

```
.
├── main.py                     # Orquestrador (5 etapas)
├── requirements.txt
├── .env.example                # Modelo das variáveis de ambiente
├── system_prompt_token.md      # Prompt do Estrategista (voz da marca) — ignorado
├── knowledge_base/             # PDFs de conhecimento — ignorado
├── chroma_db_gemini/           # Banco vetorial — ignorado (regenerável)
├── output_psd/MM-AAAA/         # PSDs gerados — ignorado
├── sessoes/, tests/            # Ignorados
├── debug_roteiros_com_erro.txt # Diagnóstico de falhas de formato — ignorado
└── utils/
    ├── config.py               # Modelos, caminhos, RAG (via .env)
    ├── functions.py            # RAG/ChromaDB, OAuth2, pastas, Docs, upload
    ├── roteiro.py              # Parsers, geração de roteiros, resiliência
    └── gerador_psd.py          # PSD via Photoshop COM
```

---

## 🚀 Como rodar

### 1. Pré-requisitos

- **Windows** + **Adobe Photoshop instalado e licenciado** (testado na v27.10 —
  a versão é detectada automaticamente pelo registro)
- Python 3.9+
- Chave da **API do Gemini** e pasta no **Google Drive** para a saída

### 2. Instalação

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configuração (`.env`)

Copie `.env.example` para `.env` e preencha:

```env
GOOGLE_API_KEY=sua_chave_gemini_aqui
GOOGLE_DRIVE_FOLDER_ID=id_da_pasta_pai_no_drive

# Modelos (os nomes mudam com o tempo — veja a seção "Modelos do Gemini")
GOOGLE_EMBEDDING_MODEL=gemini-embedding-001
GOOGLE_CHAT_MODEL=gemini-3.5-flash-lite

# Opcionais — roteiros com modelo dedicado e reserva automática
GOOGLE_ROTEIRO_MODEL=
GOOGLE_ROTEIRO_MODEL_FALLBACK=
```

- `GOOGLE_CHAT_MODEL` → agenda + roteiros (se `GOOGLE_ROTEIRO_MODEL` estiver vazio)
- `GOOGLE_ROTEIRO_MODEL` → modelo exclusivo dos roteiros (vazio = usa o da agenda)
- `GOOGLE_ROTEIRO_MODEL_FALLBACK` → reserva automática em caso de sobrecarga
  (503) ou cota (429); vazio = usa o `GOOGLE_CHAT_MODEL`

### 4. Google Drive (OAuth2)

1. Crie credenciais OAuth2 no [Google Cloud Console](https://console.cloud.google.com/) → *APIs & Services* → *Credentials* (escopo do Drive).
2. Salve o JSON como `oauth_credentials.json` na raiz.
3. Na primeira execução o navegador abre para autorizar; o token fica em
   `.token_cache.json` (refresh automático; se expirar/revogar, refaz o login).

### 5. Base de conhecimento

- Coloque os PDFs em `knowledge_base/`.
- O banco vetorial **se sincroniza sozinho**: PDFs removidos saem do índice,
  alterados são reindexados (detectados por hash MD5) e inalterados são
  ignorados — **não é preciso apagar o ChromaDB manualmente**.

### 6. Executar

```bash
python main.py
```

---

## 📁 Saída gerada

**Local:**
- `resumo_IA_AAAA-MM-DD.txt` — backup da agenda + 12 roteiros
- `output_psd/MM-AAAA/Conteudo 01.psd ... Conteudo 12.psd`

**Google Drive:**
```
MM-AAAA/
├── Resumo Completo/resumo_AAAA-MM-DD   ← Doc: agenda + 12 roteiros
├── Primeira Semana/Semana 1            ← Doc: agenda + 3 roteiros
├── Segunda Semana/Semana 2             ← Doc: agenda + 3 roteiros
├── Terceira Semana/Semana 3            ← Doc: agenda + 3 roteiros
├── Quarta Semana/Semana 4              ← Doc: agenda + 3 roteiros
└── MM-AAAA-CARROSEIS/Conteudo 01.psd ... 12.psd
```

Pastas com o mesmo nome na mesma posição são **reaproveitadas** (re-execuções
não criam duplicatas de pastas).

---

## 🛠️ Solução de problemas e recuperação

| Situação | O que acontece / fazer |
|---|---|
| Erro 429 (cota) ou 503 (sobrecarga) | Retry automático com backoff + troca para o modelo de reserva |
| Roteiro fora do formato | Tentativas extras; a resposta bruta vai para `debug_roteiros_com_erro.txt` (apagar o arquivo quando quiser) |
| Erro 404 no modelo | O nome foi aposentado pela Google — liste os disponíveis e atualize o `.env` (aliases `gemini-*-latest` reduzem esse risco) |
| Token do Drive expirado | Re-login automático no navegador |
| Slide sem `Título:` | Validação tolera; o PSD usa título de reserva (1ª frase do texto) |

---

## 🤖 Notas sobre os modelos do Gemini

- Os nomes de modelo mudam com o tempo (ex.: `gemini-2.0-flash` foi aposentado).
  Para listar os disponíveis na sua chave:

```python
import os, requests
from dotenv import load_dotenv
load_dotenv()
r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                 params={"key": os.getenv("GOOGLE_API_KEY"), "pageSize": 1000})
for m in r.json().get("models", []):
    if "generateContent" in m.get("supportedGenerationMethods", []):
        print(m["name"])
```

- Modelos `*-lite` são mais baratos, porém piores em seguir formato estrito.
- Modelos `*-flash-lite` podem ignorar o parâmetro `temperature` (aviso inofensivo).

---

## ⚙️ Personalização

- **Voz da marca / metodologia**: edite `system_prompt_token.md`.
  ⚠️ A **seção 10 (formato de saída)** é o contrato entre a IA e o código —
  os parsers de `utils/functions.py` e `utils/roteiro.py` dependem dela.
- **Parâmetros RAG**: `CHUNK_SIZE`, `CHUNK_OVERLAP`, `RETRIEVAL_K` em `utils/config.py`.
- **Visual dos PSDs**: `ESTILOS` e `COR_FUNDO` em `utils/gerador_psd.py`
  (fontes, tamanhos, cores — tudo editável depois no Photoshop).
- **Estrutura da pasta do mês**: `nomes_subpastas` no `main.py`.

---

## 🔐 Segurança

O `.gitignore` protege todos os arquivos sensíveis e proprietários:

| Arquivo | Motivo |
|---|---|
| `.env` | Chave da API e ID da pasta |
| `oauth_credentials.json` / `credentials.json` | Credenciais Google |
| `.token_cache.json` | Token OAuth |
| `system_prompt_token.md` / `knowledge_base/` | Conteúdo proprietário da marca |
| `chroma_db_gemini/`, `venv/`, `__pycache__` | Regeneráveis / ambiente |
| `resumo_IA_*.txt`, `output_psd/`, `tests/`, `debug_roteiros_com_erro.txt` | Saídas e utilitários locais |



---

## ⚠️ Limitações conhecidas

- Requer Photoshop no Windows (COM) — a geração abre o aplicativo.
- Os Docs no Drive são convertidos de texto plano: a marcação markdown
  aparece literal no documento (comportamento da API).
- O parágrafo "Fio condutor do mês" entra ao final do Doc da Semana 4.
- O projeto residindo no OneDrive, cada execução sincroniza ~36 MB de PSDs.

---

## 📄 Licença

Uso interno / proprietário da Token Brand — ENGINE CRIATIVA.

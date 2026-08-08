# 📄 `README.md` — Agente de Conteúdo Token

```markdown
# 🚀 Agente de Conteúdo Token — ENGINE CRIATIVA

Sistema de **automação de conteúdo** para a **Token Brand**. Ele usa **RAG**
(Retrieval-Augmented Generation) com **Google Gemini** para gerar agendas mensais
de conteúdo a partir de uma base de conhecimento em PDFs, e publica o resultado
estruturado no **Google Drive** (resumo completo + uma pasta por semana, com
Google Doc e PDF).

---

## ✨ Funcionalidades

- 🤖 **Geração de agenda mensal** via IA (Gemini) com base na base de conhecimento.
- 🧠 **RAG** com **ChromaDB** (banco vetorial persistente — evita re-processar PDFs).
- 📁 **Publicação organizada no Google Drive**:
  - Pasta do mês (ex: `08-2026`)
  - `Resumo Completo/` → Google Doc com o resumo integral
  - `Primeira/Segunda/Terceira/Quarta Semana/` → cada uma com:
    - Google Doc com o texto da semana
    - PDF (conteúdo contínuo) gerado via `reportlab`
- 💾 **Backup local** do resumo em `resumo_IA_AAAA-MM-DD.txt`.
- 🔐 **OAuth2** com tratamento de token expirado/revogado (refaz login automaticamente).

---

## 🧰 Stack

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3 |
| RAG / LLM | LangChain + Google Gemini (`gemini-embedding-001`, `gemini-2.0-flash`) |
| Vector Store | ChromaDB (persistente em disco) |
| PDFs | PyMuPDF (parser) + ReportLab (geração) |
| Google Drive | Google API (`google-api-python-client`) |
| Config | `python-dotenv` |

---

## 📂 Estrutura do Projeto

```
.
├── main.py                        # Orquestrador principal
├── requirements.txt               # Dependências
├── .env.example                   # Modelo das variáveis de ambiente
├── utils/
│   ├── config.py                  # Configurações (modelos, caminhos, RAG)
│   └── functions.py               # RAG, ChromaDB, Google Drive, PDFs
├── knowledge_base/                # PDFs de conteúdo (ignorado no git)
├── system_prompt_token.md         # Diretrizes da marca (ignorado no git)
├── chroma_db_gemini/              # Banco vetorial (ignorado no git)
└── resumo_IA_*.txt                # Resumos locais (ignorado no git)
```

---

## 🚀 Como rodar

### 1. Pré-requisitos

- Python 3.9+
- Conta Google com acesso à API Gemini e Google Drive

### 2. Instalação

```bash
# Clonar o repositório
git clone <URL_DO_REPO>
cd agente-conteudo

# Criar ambiente virtual
python -m venv .venv

# Ativar (Windows)
.venv\Scripts\activate

# Ativar (Linux/Mac)
source .venv/bin/activate

# Instalar dependências
pip install -r requirements.txt
```

### 3. Configuração

Copie o `.env.example` para `.env` e preencha os valores:

```bash
cp .env.example .env   # Linux/Mac
copy .env.example .env  # Windows
```

```env
GOOGLE_API_KEY=sua_chave_gemini_aqui
GOOGLE_DRIVE_FOLDER_ID=id_da_pasta_pai_no_drive
GOOGLE_EMBEDDING_MODEL=gemini-embedding-001
GOOGLE_CHAT_MODEL=gemini-2.0-flash
```

**Google Drive (OAuth2):**
1. Crie credenciais OAuth2 em [Google Cloud Console](https://console.cloud.google.com/) → *APIs & Services* → *Credentials*.
2. Baixe o JSON como `oauth_credentials.json` (na raiz do projeto).
3. Na primeira execução, o navegador abrirá para autorizar o acesso. O token é salvo em `.token_cache.json` (ignorado no git).

**Base de conhecimento:**
- Coloque os PDFs de conteúdo em `knowledge_base/`.
- Na primeira execução sem banco, os PDFs são processados e indexados no ChromaDB.

### 4. Executar

```bash
python main.py
```

O script irá:
1. Carregar/criar o banco vetorial.
2. Gerar a agenda do mês via Gemini.
3. Salvar o resumo localmente.
4. Criar no Drive a estrutura `08-2026/` com as 5 subpastas e os arquivos.

---

## 🔐 Segurança

O `.gitignore` protege os arquivos sensíveis:

| Arquivo | Motivo |
|---|---|
| `.env` | Chave da API e ID da pasta |
| `credentials.json` / `oauth_credentials.json` | Credenciais do Google |
| `.token_cache.json` | Token de acesso |
| `.venv` / `__pycache__` | Ambiente e cache |
| `chroma_db_gemini/` | Banco vetorial local (regenerável) |
| `resumo_IA_*.txt` | Saídas geradas |
| `system_prompt_token.md` / `knowledge_base/` | Conteúdo proprietário da marca |

> ⚠️ Se o repositório for **público**, garanta que `system_prompt_token.md` e `knowledge_base/` não contenham conteúdo confidencial — eles estão no `.gitignore` por padrão.

---

## ⚙️ Personalização

- **System Prompt:** edite `system_prompt_token.md` para ajustar o tom de voz, diretrizes da marca e formato de saída.
- **Parâmetros RAG:** ajuste `CHUNK_SIZE`, `CHUNK_OVERLAP` e `RETRIEVAL_K` em `utils/config.py`.
- **Modelos:** altere via `.env` (`GOOGLE_EMBEDDING_MODEL`, `GOOGLE_CHAT_MODEL`).

---

## 📄 Licença

Uso interno / proprietário da Token Brand — ENGINE CRIATIVA.
```


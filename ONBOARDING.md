# 🧑‍💻 ONBOARDING — Guia do novo usuário

> Este guia instala e roda o agente em uma máquina **Windows nova**, sem
> precisar instalar Python (o `setup.bat` traz um Python portátil) e sem
> interferir com o ambiente da máquina.

## O que o setup faz

1. Baixa Python 3.12 portátil → `runtime\` (não mexe em nenhum Python já instalado)
2. Habilita o pip nesse Python portátil
3. Instala as dependências do `requirements.txt`
4. Gera o `.env` a partir do `.env.example`
5. Gera o launcher `iniciar_agente.bat`

## O que você vai precisar

- Windows 10 ou superior
- Pasta do projeto em um local **sem OneDrive** (ex.: `C:\projetos\agente-conteudo`)
- Acesso à internet
- Conta Google (para a chave da API e o Drive)
- Adobe Photoshop instalado (para gerar os PSDs)

## Conteúdo proprietário (fornecido via Drive compartilhado)

| Item | Destino na máquina |
|---|---|
| PDFs da base de conhecimento | `knowledge_base\` |
| `system_prompt_token.md` | raiz do projeto |
| `oauth_credentials.json` | raiz do projeto |

## Passo 1 — Clonar o projeto

Com Git:

```
git clone https://github.com/rodolfo-medeiros/agente-conteudo.git
cd agente-conteudo
```

Sem Git: baixar o ZIP do repositório e extrair em uma pasta local.

## Passo 2 — setup.bat

Duplo clique em `setup.bat`. Demora 5–15 minutos conforme a internet.

Cria na pasta do projeto:

- `runtime\` — Python portátil + dependências (~1 GB), completamente isolado
- `.env` — modelo de variáveis (preencher no Passo 4)
- `iniciar_agente.bat` — launcher do painel

## Passo 3 — Conteúdo proprietário

Baixar os PDFs para `knowledge_base\` e copiar `system_prompt_token.md` e
`oauth_credentials.json` para a raiz do projeto.

Se o arquivo de OAuth não for compartilhado com você, crie o próprio em
`console.cloud.google.com`: crie um projeto → habilite a **Drive API** →
configure a tela de consentimento e adicione sua conta como **conta de
teste** → crie credenciais OAuth do tipo **Desktop** → baixe o JSON e
renomeie para `oauth_credentials.json` na raiz.

## Passo 4 — .env

Abra o `.env` num editor e preencha:

- `GOOGLE_API_KEY` — gere em `aistudio.google.com` → Get API key
- `GOOGLE_DRIVE_FOLDER_ID` — crie uma pasta no Drive e copie o ID da URL
- `GOOGLE_EMBEDDING_MODEL` e `GOOGLE_CHAT_MODEL` já vêm com valores padrão

## Passo 5 — Primeira execução

Duplo clique em `iniciar_agente.bat`.

Na primeira vez o navegador abre para autorizar o acesso ao Google
(aceite a permissão da conta de teste). O token fica em cache local em
`.token_cache.json` — ignorado pelo Git.

A execução completa leva de 25 a 45 minutos (agenda, 12 roteiros e 12 PSDs).
Não feche a aba do painel nem mexa na janela do Photoshop enquanto ele roda.

Antes da primeira execução, abra o Photoshop uma vez manualmente e feche
qualquer diálogo (licença, atualização, login Adobe) — diálogos abertos
travam a automação.

Se algum roteiro ou PSD falhar, o resumo final do log mostra quais. Para
refazer só os faltantes (sem refazer a agenda nem publicar de novo):

```
runtime\python.exe gerar_faltantes.py
```

⚠️ Não rode o agente em duas máquinas ao mesmo tempo para o mesmo mês —
as duas publicariam na mesma pasta do Drive.

## Atualizações

```
git pull
```

Se o `requirements.txt` mudar, rode o `setup.bat` de novo — ele só
reinstala o que falta.

## FAQ

- Preciso instalar Python? **Não** — o `setup.bat` traz um Python portátil.
- Onde ficam os PSDs? Localmente em `output_psd\MM-AAAA\` e no Drive, na subpasta `MM-AAAA-CARROSSEIS`.
- Quanto custa? O uso da API tem quotas no plano gratuito do Gemini.
- Mac ou Linux? **Não suportado** — a geração de PSDs usa Photoshop + COM (só Windows).

## Checklist final

- ☐ `setup.bat` rodou sem erros
- ☐ `.env` preenchido (GOOGLE_API_KEY e GOOGLE_DRIVE_FOLDER_ID)
- ☐ `knowledge_base\` com os PDFs da base de conhecimento
- ☐ `system_prompt_token.md` na raiz
- ☐ `oauth_credentials.json` na raiz
- ☐ `iniciar_agente.bat` abriu o painel sem erro

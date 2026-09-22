

from datetime import date, datetime
import os
from utils import config
import utils.functions as fn
from utils.roteiro import (
    extrair_conteudos,
    formatar_secao_roteiro,
    gerar_roteiro_conteudo,
)
from utils.gerador_psd import gerar_psd_carrossel



def main():
    knowledge_base_folder = "knowledge_base"

    today = date.today()
    year_month = today.strftime("%Y/%m")
    mes_ano = today.strftime("%m-%Y")
    data_hoje = datetime.now().strftime("%Y-%m-%d")


    # Passo 1 - Processa o pdf e gera resumo via gemini (fluxo original)
    vectorstore = fn.obter_ou_criar_vectorstore(knowledge_base_folder)
    comando = (
    f"Faça a agenda de conteúdo de {year_month}. "
    "Use EXATAMENTE o seguinte formato para cada semana, com um cabeçalho "
    "iniciado por cerquilhas (##) e o texto '📅 Semana' seguido do número:\n\n"
    "## 📅 Semana 1 (DD/MM a DD/MM): Título da semana\n\n"
    "[conteúdo da semana 1]\n\n"
    "## 📅 Semana 2 (DD/MM a DD/MM): Título da semana\n\n"
    "[conteúdo da semana 2]\n\n"
    "## 📅 Semana 3 (DD/MM a DD/MM): Título da semana\n\n"
    "[conteúdo da semana 3]\n\n"
    "## 📅 Semana 4 (DD/MM a DD/MM): Título da semana\n\n"
    "[conteúdo da semana 4]\n\n"
    "IMPORTANTE: cada semana DEVE começar com o cabeçalho '## 📅 Semana N' "
    "exatamente nesse formato, sem negrito, sem emojis adicionais nessa linha, "
    "e com o conteúdo da semana logo abaixo. Não use '####', '###' ou '**' "
    "no cabeçalho da semana."

    )

    resumo = fn.consultar_IA_com_retry(vectorstore, comando)

    # Extrai as semanas da agenda
    semanas = fn.extrair_semanas(resumo)
    print(f"\n📅 {len(semanas)} semanas encontradas no resumo.")

    if not semanas:
        print("❌ Não foram encontradas semanas no resumo. Finalizando.")
        return

    # Passo 2 - Extrai os 3 conteúdos de cada semana e gera 1 roteiro por conteúdo
    for semana in semanas:
        semana["conteudos"] = extrair_conteudos(semana["conteudo"])

    total_conteudos = sum(len(s["conteudos"]) for s in semanas)
    print(f"🎬 {total_conteudos} conteúdos encontrados. Gerando 1 roteiro por conteúdo...")

    for semana in semanas:
        if not semana["conteudos"]:
            print(
                f"⚠️ Semana {semana['numero']} sem conteúdos identificáveis; "
                "pulando roteiros desta semana."
            )
            continue

        for conteudo in semana["conteudos"]:
            try:
                roteiro_texto, slides = gerar_roteiro_conteudo(
                    conteudo["numero"],
                    conteudo["editoria"],
                    conteudo["texto"],
                    vectorstore,
                )
                conteudo["roteiro_texto"] = roteiro_texto
                conteudo["slides"] = slides
            except Exception as e:
                print(
                    f"⚠️ Falha ao gerar roteiro do Conteúdo {conteudo['numero']}: {e}. "
                    "Seguindo sem roteiro neste conteúdo."
                )
                conteudo["roteiro_texto"] = None
                conteudo["slides"] = None

    # Passo 3 - Conteúdo final de cada semana (agenda + roteiros dos seus conteúdos)
    for semana in semanas:
        partes = [semana["conteudo"]]
        for conteudo in semana["conteudos"]:
            if conteudo.get("roteiro_texto"):
                partes.append(
                    formatar_secao_roteiro(
                        conteudo["roteiro_texto"],
                        numero_conteudo=conteudo["numero"],
                        editoria=conteudo["editoria"],
                    )
                )
        semana["conteudo_final"] = "\n\n".join(partes)

    # Resumo completo = agenda inteira + roteiros de todos os conteúdos
    secoes_roteiros = [
        formatar_secao_roteiro(
            c["roteiro_texto"],
            numero_conteudo=c["numero"],
            editoria=c["editoria"],
        )
        for semana in semanas
        for c in semana["conteudos"]
        if c.get("roteiro_texto")
    ]
    resumo_completo = resumo
    if secoes_roteiros:
        resumo_completo += "\n\n" + "\n\n".join(secoes_roteiros)

    # Salva resumo localmente como backup/teste (agenda + roteiros)
    nome_arquivo_local = f"resumo_IA_{data_hoje}.txt"
    with open(nome_arquivo_local, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"RESUMO GERADO EM {data_hoje}\n")
        f.write("=" * 80 + "\n\n")
        f.write(resumo_completo)

    print(f"\n✅ Resumo salvo localmente: {nome_arquivo_local}")
    print(f"Conteúdo do resumo ({len(resumo)} caracteres):\n")
    print(resumo[:500] + "...\n" if len(resumo) > 500 else resumo)

    #conecta ao google drive
    drive_service = fn.conectar_google_drive()

    if not drive_service:
         print("❌ Não foi possível conectar ao Google Drive. Abortando.")
         return

    #cria a pasta do mes
    id_pasta_mes = fn.criar_pasta_drive(
        service=drive_service,
        nome_pasta=mes_ano,
        id_pasta_pai=config.GOOGLE_DRIVE_FOLDER_ID
    )

    if not id_pasta_mes:
        print("❌ Não foi possível criar a pasta do mês. Abortando.")
        return

    #cria as 5 subpastas
    nomes_subpastas = [
        "Resumo Completo",
        "Primeira Semana",
        "Segunda Semana",
        "Terceira Semana",
        "Quarta Semana",
        f"{mes_ano}-CARROSSEIS",
    ]

    ids_subpastas = {}

    for nome_subpasta in nomes_subpastas:
        id_pasta = fn.criar_pasta_drive(
            service=drive_service,
            nome_pasta=nome_subpasta,
            id_pasta_pai=id_pasta_mes

        )
        if id_pasta:
            ids_subpastas[nome_subpasta] = id_pasta
            print(f"  📁 {nome_subpasta} criada com sucesso!")


    # Publica o resumo completo (agenda + roteiros de todos os conteúdos)
    if "Resumo Completo" in ids_subpastas:
        fn.criar_documento_resumo(
            service=drive_service,
            nome_arquivo=f"resumo_{data_hoje}",
            conteudo_texto=resumo_completo,
            id_pasta_destino=ids_subpastas["Resumo Completo"]

        )

    # Publica o Doc de cada semana (agenda da semana + roteiros) - sem PDF no Drive
    mapa_subpastas = {
        1: "Primeira Semana",
        2: "Segunda Semana",
        3: "Terceira Semana",
        4: "Quarta Semana",
    }

    for semana in semanas:
        nome_subpasta = mapa_subpastas.get(
            semana["numero"], f"Semana {semana['numero']}"
        )

        if nome_subpasta not in ids_subpastas:
            print(f"⚠️ Pasta '{nome_subpasta}' não criada, pulando...")
            continue

        print(f"\n📄 Publicando {nome_subpasta}...")
        fn.criar_documento_resumo(
            service=drive_service,
            nome_arquivo=f"Semana {semana['numero']}",
            conteudo_texto=semana["conteudo_final"],
            id_pasta_destino=ids_subpastas[nome_subpasta],
        )

    # Passos 4 e 5 - Gera os 12 PSDs localmente (um por conteúdo)
    pasta_psd = os.path.join("output_psd", mes_ano)
    os.makedirs(pasta_psd, exist_ok=True)

    id_pasta_carrosseis = ids_subpastas.get(f"{mes_ano}-CARROSSEIS")

    print("\n🎨 Gerando os 12 PSDs dos carrosséis (o Photoshop será aberto)...")
    for semana in semanas:
        for conteudo in semana["conteudos"]:
            if not conteudo.get("slides"):
                print(
                    f"⚠️ Sem roteiro para o Conteúdo {conteudo['numero']}; "
                    "PSD não gerado."
                )
                continue

            # Nome sem acento, para segurança no COM do Photoshop
            nome_psd = f"Conteudo {conteudo['numero']:02d}.psd"
            caminho_psd = os.path.join(
                pasta_psd, nome_psd
            )
            try:
                gerar_psd_carrossel(
                    slides=conteudo["slides"],
                    caminho_saida=caminho_psd,
                    titulo_documento=f"Carrossel Conteudo {conteudo['numero']}",
                )

                # Upload dos PSD´s para a subpasta carrosseis no Drive
                if id_pasta_carrosseis:
                    fn.upload_arquivo_drive(
                        service=drive_service,
                        caminho_local=caminho_psd,
                        nome_arquivo=nome_psd,
                        mime_type="application/octet-stream",
                        id_pasta_destino=id_pasta_carrosseis

                    )

                else:
                    print(
                        f"!! Pasta '{mes_ano}-CARROSSEIS' indisponível;"
                        f"PSD do Conteúdo {conteudo['numero']} salvo só localmente."

                          )

            except Exception as e:
                print(f"❌ Erro ao gerar PSD do Conteúdo {conteudo['numero']}: {e}")

    print("\n🏁 Finalizado!")


if __name__ == "__main__":
    main()

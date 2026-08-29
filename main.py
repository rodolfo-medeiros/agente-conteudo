
#importando funcoes
from datetime import date, datetime
import os
import tempfile
from utils import config
import utils.functions as fn



def main():
    knowledge_base_folder = "knowledge_base"
    
    today= date.today()
    year_month =today.strftime("%Y/%m")
    mes_ano = today.strftime("%m-%Y")
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    
    
    #Processa o pdf e gera resumo via gemini
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

    resumo = fn.consultar_IA_com_retry(vectorstore,comando,tentativas_maximas=3,espera_segundos=5)
    
    # Salva resumo localmente como backup/teste
    nome_arquivo_local = f"resumo_IA_{data_hoje}.txt"
    with open(nome_arquivo_local, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"RESUMO GERADO EM {data_hoje}\n")
        f.write("=" * 80 + "\n\n")
        f.write(resumo)
    
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
        
    
    # Salva o resumo completo na pasta "Resumo Completo"
    if "Resumo Completo" in ids_subpastas:
        fn.criar_documento_resumo(
            service=drive_service,
            nome_arquivo=f"resumo_{data_hoje}",
            conteudo_texto=resumo,
            id_pasta_destino=ids_subpastas["Resumo Completo"]

        )
    
    # Extrai as semanas do resumo
    semanas = fn.extrair_semanas(resumo)
    print(f"\n📅 {len(semanas)} semanas encontradas no resumo.")
    
    if not semanas:
        print("❌ Não foram encontradas semanas no resumo. Finalizando.")
        return
    
    # Pasta local temporária para os PDFs
    pasta_local_pdfs = os.path.join(tempfile.gettempdir(), f"resumos_token_{data_hoje}")
    os.makedirs(pasta_local_pdfs, exist_ok=True)

    mapa_subpastas = {
        1: "Primeira Semana",
        2: "Segunda Semana",
        3: "Terceira Semana",
        4: "Quarta Semana",
    }

    for semana in semanas:
        numero = semana["numero"]
        nome_subpasta = mapa_subpastas.get(numero, f"Semana {numero}")

        if nome_subpasta not in ids_subpastas:
            print(f"⚠️ Pasta '{nome_subpasta}' não criada, pulando...")
            continue

        id_pasta_destino = ids_subpastas[nome_subpasta]
        conteudo_semana = semana["conteudo"]

        print(f"\n📄 Processando {nome_subpasta}...")

        # 1. Google Doc com o texto da semana
        fn.criar_documento_resumo(
            service=drive_service,
            nome_arquivo=f"Semana {numero}",
            conteudo_texto=conteudo_semana,
            id_pasta_destino=id_pasta_destino,
        )

        # 2. PDF com o mesmo conteúdo
        caminho_pdf = os.path.join(pasta_local_pdfs, f"Semana {numero}.pdf")
        try:
            fn.gerar_pdf_semana(
                titulo=semana["titulo"],
                conteudo=conteudo_semana,
                caminho_saida=caminho_pdf,
            )
            fn.upload_arquivo_drive(
                service=drive_service,
                caminho_local=caminho_pdf,
                nome_arquivo=f"Semana {numero}.pdf",
                mime_type="application/pdf",
                id_pasta_destino=id_pasta_destino,
            )
        except Exception as e:
            print(f"❌ Erro ao gerar/enviar PDF da Semana {numero}: {e}")


if __name__ == "__main__":
    main()
    
    
    
    
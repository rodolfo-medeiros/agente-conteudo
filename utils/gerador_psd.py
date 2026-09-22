"""Geração do PSD de carrossel para Instagram.

Canvas: 5400 x 1350 px (5 quadrantes de 1080 x 1350 px), um grupo por slide
com fundo sólido editável e camadas de TEXTO reais (editáveis no Photoshop).

Requisitos:
    - Adobe Photoshop instalado (testado na v27.10) - somente Windows
    - pip install photoshop-python-api (a versão do Photoshop é detectada
      automaticamente pelo registro do Windows)

Nota sobre enums (photoshop-python-api 0.24.x):
    Os membros seguem PascalCase: Units.Pixels, Direction.Vertical,
    TextType.ParagraphText, NewDocumentMode.NewRGB, DocumentFill.White,
    SaveOptions.DoNotSaveChanges, LayerKind.TextLayer.
"""

import os

import photoshop.api as ps
from photoshop.api.errors import PhotoshopPythonAPIError


# Dimensões do carrossel
LARGURA_QUADRANTE = 1080
ALTURA = 1350
NUM_SLIDES = 5
LARGURA_TOTAL = LARGURA_QUADRANTE * NUM_SLIDES  # 5400

# Layout
MARGEM = 80      # margem lateral interna do quadrante
TOPO = 100       # y inicial do primeiro bloco de texto
GAP = 40         # espaçamento vertical entre blocos
LARGURA_TEXTO = LARGURA_QUADRANTE - 2 * MARGEM  # 920 px

# Cores (RGB) e estilos tipográficos - tudo editável no Photoshop depois
COR_FUNDO = (247, 247, 249)  # #F7F7F9
ESTILOS = {
    "rotulo":    {"tamanho": 28, "cor": (150, 150, 155), "fonte": "Arial-BoldMT"},
    "titulo_1":  {"tamanho": 78, "cor": (26, 26, 46),    "fonte": "Arial-BoldMT"},
    "titulo":    {"tamanho": 56, "cor": (26, 26, 46),    "fonte": "Arial-BoldMT"},
    "subtitulo": {"tamanho": 40, "cor": (79, 79, 99),    "fonte": "ArialMT"},
    "texto":     {"tamanho": 36, "cor": (51, 51, 51),    "fonte": "ArialMT"},
    "cta":       {"tamanho": 34, "cor": (15, 52, 96),    "fonte": "Arial-BoldMT"},
}


def gerar_psd_carrossel(slides, caminho_saida, titulo_documento="Carrossel Instagram"):
    """Gera o arquivo .psd do carrossel.

    Args:
        slides: lista de dicts gerada por utils.roteiro.extrair_slides
            ({numero, rotulo, titulo, subtitulo, texto, cta}).
        caminho_saida: caminho local do arquivo .psd.
        titulo_documento: nome do documento dentro do Photoshop.
    """
    if not slides:
        raise ValueError("Nenhum slide recebido para gerar o PSD.")

    caminho_saida = os.path.abspath(caminho_saida)
    os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)

    try:
        app = ps.Application()
    except (PhotoshopPythonAPIError, Exception) as e:
        raise RuntimeError(
            "Não foi possível iniciar o Photoshop via COM. Verifique se o "
            "Adobe Photoshop está instalado/licenciado nesta máquina."
        ) from e

    # Posições, guias e seleções usam as unidades de régua (pixels).
    # NÃO setamos typeUnits: a classe Preferences da lib não expõe essa
    # property (atribuir seria um no-op silencioso) e, como o documento é
    # 72 dpi, 1pt = 1px — os valores numéricos ficam corretos assim.
    unidades_originais = app.preferences.rulerUnits
    app.preferences.rulerUnits = ps.Units.Pixels

    try:
        doc = app.documents.add(
            LARGURA_TOTAL,
            ALTURA,
            72,  # resolução
            titulo_documento,
            ps.NewDocumentMode.NewRGB,
            ps.DocumentFill.White,
        )

        _criar_guias(app)

        for slide in sorted(slides, key=lambda s: s["numero"])[:NUM_SLIDES]:
            _criar_grupo_slide(doc, slide)

        doc.saveAs(caminho_saida, ps.PhotoshopSaveOptions(), True)
        print(f"✅ PSD salvo: {caminho_saida}")

        doc.close(ps.SaveOptions.DoNotSaveChanges)
        return caminho_saida
    finally:
        app.preferences.rulerUnits = unidades_originais


def _criar_guias(app):
    """Cria guias verticais nos limites dos 5 quadrantes.

    Usa doJavaScript (ExtendScript) porque a coleção de guias não está
    exposta na wrapper Python do Document (o dispatch COM direto falha
    com 'Name guides not found').
    """
    jsx = (
        "var d = app.activeDocument;"
        f"for (var i = 1; i < {NUM_SLIDES}; i++) {{"
        f"d.guides.add(Direction.VERTICAL, new UnitValue(i * {LARGURA_QUADRANTE}, 'px'));"
        "}"
    )
    try:
        app.doJavaScript(jsx)
    except Exception as e:
        print(f"⚠️ Guias não criadas (sem impacto no arquivo): {e}")



def _criar_grupo_slide(doc, slide):
    """Cria o grupo do slide: fundo sólido + camadas de texto."""
    numero = slide["numero"]
    x0 = (numero - 1) * LARGURA_QUADRANTE

    grupo = doc.layerSets.add()
    rotulo_slide = slide.get("rotulo") or f"Slide {numero}"
    grupo.name = f"Slide {numero} - {rotulo_slide}"

    _preencher_fundo(doc, grupo, x0)

    y = TOPO
    for nome, conteudo, estilo, altura in _blocos_texto(slide):
        if not conteudo:
            continue
        _adicionar_camada_texto(
            grupo, nome, conteudo, estilo, x0 + MARGEM, y, altura
        )
        y += altura + GAP


def _preencher_fundo(doc, grupo, x0):
    """Preenche o quadrante do slide com a cor de fundo."""
    camada = grupo.artLayers.add()
    camada.name = "Fundo"

    cor = ps.SolidColor()
    cor.rgb.red, cor.rgb.green, cor.rgb.blue = COR_FUNDO

    doc.selection.select(
        [
            [x0, 0],
            [x0 + LARGURA_QUADRANTE, 0],
            [x0 + LARGURA_QUADRANTE, ALTURA],
            [x0, ALTURA],
        ]
    )
    doc.selection.fill(cor)
    doc.selection.deselect()


def _blocos_texto(slide):
    """Define os blocos de texto de cada tipo de slide.

    Retorna lista de (nome_da_camada, conteudo, estilo, altura_da_caixa).
    """
    blocos = []
    if slide["numero"] == 1:
        blocos.append(("Titulo", slide.get("titulo", ""), ESTILOS["titulo_1"], 520))
        blocos.append(
            ("Subtitulo", slide.get("subtitulo", ""), ESTILOS["subtitulo"], 480)
        )
    else:
        if slide.get("rotulo"):
            blocos.append(("Rotulo", slide["rotulo"], ESTILOS["rotulo"], 60))
        blocos.append(("Titulo", slide.get("titulo", ""), ESTILOS["titulo"], 300))
        if slide.get("texto"):
            blocos.append(("Texto", slide["texto"], ESTILOS["texto"], 560))
        if slide.get("cta"):
            blocos.append(("CTA", slide["cta"], ESTILOS["cta"], 180))
    return blocos


def _adicionar_camada_texto(grupo, nome, conteudo, estilo, x, y, altura):
    """Adiciona uma camada de texto (caixa de parágrafo) dentro do grupo."""
    camada = grupo.artLayers.add()
    camada.kind = ps.LayerKind.TextLayer

    item = camada.textItem
    item.kind = ps.TextType.ParagraphText
    item.contents = conteudo
    item.width = LARGURA_TEXTO
    item.height = altura
    item.position = [x, y]
    item.size = estilo["tamanho"]

    try:
        item.font = estilo["fonte"]
    except Exception:
        print(f"⚠️ Fonte '{estilo['fonte']}' indisponível; usando a padrão.")

    cor = ps.SolidColor()
    cor.rgb.red, cor.rgb.green, cor.rgb.blue = estilo["cor"]
    item.color = cor

    camada.name = nome
    return camada

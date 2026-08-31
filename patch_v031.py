from pathlib import Path

path = Path("main.py")
text = path.read_text(encoding="utf-8")

# Versao e imports para os novos botoes/ícones.
text = text.replace('APP_VERSION = "0.3.0"', 'APP_VERSION = "0.3.1"')
text = text.replace(
    'from PySide6.QtGui import QAction, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap, QTransform',
    'from PySide6.QtGui import QAction, QColor, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap, QTransform',
)
if '    QToolButton,\n' not in text:
    text = text.replace('    QToolBar,\n    QVBoxLayout,', '    QToolBar,\n    QToolButton,\n    QVBoxLayout,')

# Gera ícones vetoriais em alta definicao, sem depender de imagens externas.
helper_anchor = '''def save_config(data: dict) -> None:\n    try:\n        config_path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")\n    except Exception:\n        pass\n\n\n@dataclass'''
helper = '''def save_config(data: dict) -> None:\n    try:\n        config_path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")\n    except Exception:\n        pass\n\n\ndef make_tool_icon(kind: str, color: str) -> QIcon:\n    pix = QPixmap(56, 56)\n    pix.fill(Qt.transparent)\n    painter = QPainter(pix)\n    painter.setRenderHint(QPainter.Antialiasing, True)\n    pen = QPen(QColor(color), 3.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)\n    painter.setPen(pen)\n\n    if kind in ("crop", "clear_crop"):\n        # Cantos de recorte grandes e limpos.\n        painter.drawLine(12, 8, 12, 36)\n        painter.drawLine(12, 12, 40, 12)\n        painter.drawLine(44, 20, 44, 48)\n        painter.drawLine(16, 44, 44, 44)\n        painter.drawLine(8, 20, 36, 20)\n        painter.drawLine(20, 8, 20, 36)\n        if kind == "clear_crop":\n            red = QPen(QColor("#ff624f"), 3.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)\n            painter.setPen(red)\n            painter.drawLine(35, 35, 49, 49)\n            painter.drawLine(49, 35, 35, 49)\n    elif kind in ("rotate_left", "rotate_right"):\n        arc_rect = QRectF(11, 11, 34, 34)\n        if kind == "rotate_left":\n            painter.drawArc(arc_rect, 35 * 16, 285 * 16)\n            painter.drawLine(11, 18, 11, 8)\n            painter.drawLine(11, 8, 21, 8)\n        else:\n            painter.drawArc(arc_rect, -140 * 16, 285 * 16)\n            painter.drawLine(45, 18, 45, 8)\n            painter.drawLine(45, 8, 35, 8)\n    elif kind == "delete":\n        painter.drawLine(18, 17, 38, 17)\n        painter.drawLine(22, 13, 34, 13)\n        painter.drawRoundedRect(QRectF(20, 20, 16, 25), 2, 2)\n        painter.drawLine(25, 25, 25, 40)\n        painter.drawLine(31, 25, 31, 40)\n\n    painter.end()\n    return QIcon(pix)\n\n\n@dataclass'''
if 'def make_tool_icon(' not in text:
    if helper_anchor not in text:
        raise RuntimeError('Nao encontrei ponto para inserir make_tool_icon')
    text = text.replace(helper_anchor, helper)

# Coluna esquerda um pouco mais larga, como na previa aprovada.
text = text.replace('left.setMinimumWidth(280)', 'left.setMinimumWidth(320)')
text = text.replace('left.setMaximumWidth(330)', 'left.setMaximumWidth(380)')

# Reconstrói a grade de edicao com botoes grandes e icones realmente visiveis.
start_marker = '        # Ferramentas de edicao em cards quadrados, sempre fora da pre-visualizacao.\n'
end_marker = '        left_layout.addWidget(edit_tools)\n'
start = text.index(start_marker)
end = text.index(end_marker, start) + len(end_marker)
new_tools = '''        # Ferramentas de edicao em cards quadrados, sempre fora da pre-visualizacao.\n        tools_title = QLabel("EDIÇÃO DA PÁGINA")\n        tools_title.setObjectName("sectionTitle")\n        left_layout.addWidget(tools_title)\n\n        edit_tools = QFrame()\n        edit_tools.setObjectName("cropToolsCard")\n        tools_grid = QGridLayout(edit_tools)\n        tools_grid.setContentsMargins(0, 0, 0, 0)\n        tools_grid.setHorizontalSpacing(10)\n        tools_grid.setVerticalSpacing(10)\n\n        def make_editor_button(label: str, icon_kind: str, icon_color: str, object_name: str) -> QToolButton:\n            button = QToolButton()\n            button.setText(label)\n            button.setIcon(make_tool_icon(icon_kind, icon_color))\n            button.setIconSize(QSize(44, 44))\n            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)\n            button.setObjectName(object_name)\n            button.setMinimumSize(134, 108)\n            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)\n            return button\n\n        self.btn_crop = make_editor_button("Selecionar corte", "crop", "#4f9cff", "toolPrimary")\n        self.btn_crop.clicked.connect(self.toggle_crop)\n        self.btn_clear_crop = make_editor_button("Remover recorte", "clear_crop", "#ff755f", "toolCropClear")\n        self.btn_clear_crop.clicked.connect(self.clear_crop)\n        btn_left = make_editor_button("Girar à esquerda", "rotate_left", "#39d99a", "toolRotate")\n        btn_left.clicked.connect(lambda: self.rotate_current(-90))\n        btn_right = make_editor_button("Girar à direita", "rotate_right", "#39d99a", "toolRotate")\n        btn_right.clicked.connect(lambda: self.rotate_current(90))\n\n        btn_del = QToolButton()\n        btn_del.setText("Excluir página")\n        btn_del.setIcon(make_tool_icon("delete", "#ff535d"))\n        btn_del.setIconSize(QSize(32, 32))\n        btn_del.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)\n        btn_del.setObjectName("toolDelete")\n        btn_del.setMinimumHeight(60)\n        btn_del.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)\n        btn_del.clicked.connect(self.delete_current)\n\n        tools_grid.addWidget(self.btn_crop, 0, 0)\n        tools_grid.addWidget(self.btn_clear_crop, 0, 1)\n        tools_grid.addWidget(btn_left, 1, 0)\n        tools_grid.addWidget(btn_right, 1, 1)\n        tools_grid.addWidget(btn_del, 2, 0, 1, 2)\n        left_layout.addWidget(edit_tools)\n'''
text = text[:start] + new_tools + text[end:]

# Remove completamente o bloco de dica solicitado pelo usuario.
tip_block = '''        tip = QLabel("ⓘ  Você também pode reorganizar as páginas arrastando as miniaturas na faixa inferior.")\n        tip.setObjectName("tipBox")\n        tip.setWordWrap(True)\n        tip.setMaximumHeight(68)\n        left_layout.addWidget(tip)\n'''
text = text.replace(tip_block, '')

# Centro nao entra diretamente no splitter: ele formara uma coluna com PÁGINAS abaixo.
text = text.replace('        splitter.addWidget(center)\n\n        # CONFIGURAÇÕES — coluna direita', '        # CONFIGURAÇÕES — coluna direita')
text = text.replace('        splitter.addWidget(right)\n        splitter.setSizes([300, 900, 315])', '        splitter.addWidget(right)')

# PÁGINAS fica alinhado apenas com a pre-visualizacao; coluna esquerda e configuracoes ocupam a altura total.
old_pages_end = '''        pages_layout.addWidget(self.list)\n        workspace_layout.addWidget(pages_panel)\n\n        self.setStatusBar(QStatusBar())'''
new_pages_end = '''        pages_layout.addWidget(self.list)\n        pages_panel.setMaximumHeight(174)\n\n        middle = QWidget()\n        middle_layout = QVBoxLayout(middle)\n        middle_layout.setContentsMargins(0, 0, 0, 0)\n        middle_layout.setSpacing(10)\n        middle_layout.addWidget(center, 1)\n        middle_layout.addWidget(pages_panel, 0)\n        splitter.insertWidget(1, middle)\n        splitter.setSizes([350, 900, 330])\n\n        self.setStatusBar(QStatusBar())'''
if old_pages_end not in text:
    raise RuntimeError('Nao encontrei final da faixa de paginas')
text = text.replace(old_pages_end, new_pages_end)

# Texto do QToolButton de recorte sem glifos pequenos; o icone vetorial permanece grande acima.
text = text.replace('self.btn_crop.setText("⌗\\nSelecionar\\ncorte")', 'self.btn_crop.setText("Selecionar corte")')
text = text.replace('self.btn_crop.setText("×\\nCancelar\\nseleção" if self.crop_mode else "⌗\\nSelecionar\\ncorte")', 'self.btn_crop.setText("Cancelar seleção" if self.crop_mode else "Selecionar corte")')

# Estilo especifico dos QToolButtons para impedir texto/icone sobrepostos.
style_anchor = '''            QPushButton:pressed { background:#0d1a28; }\n'''
style_add = '''            QPushButton:pressed { background:#0d1a28; }\n            QToolButton { background:#101d2d; color:#edf5ff; border:1px solid #2a425b; border-radius:12px; padding:8px 8px 10px 8px; font-size:13px; font-weight:600; }\n            QToolButton:hover { background:#17283b; border-color:#4b7096; }\n            QToolButton:pressed { background:#0d1a28; }\n'''
text = text.replace(style_anchor, style_add)

# README da release fica coerente com a build que sera empacotada.
readme = Path('README.md')
readme.write_text('''# Editor de PDF — Windows Portable v0.3.1\n\nVersão refinada do layout moderno aprovado para o Editor de PDF no Windows.\n\n## Novidades v0.3.1\n- Layout reproduzido a partir da prévia aprovada.\n- Removido o bloco de dica abaixo da área de arrastar e soltar.\n- A faixa **PÁGINAS** agora fica alinhada somente com a **PRÉ-VISUALIZAÇÃO**.\n- Coluna esquerda ocupa toda a altura e ganhou mais espaço útil.\n- **EDIÇÃO DA PÁGINA** refeita com cards quadrados, ícones vetoriais maiores e textos separados.\n- Botões de recorte e giro não ficam mais sobrepostos.\n- **Excluir página** permanece em botão horizontal destacado.\n- Pré-visualização, zoom e Ajustar mantidos.\n\n## Mantido\n- Ctrl+Z.\n- Drag & drop de imagens e PDFs.\n- Reordenação pelas miniaturas.\n- Capa padrão opcional sempre inteira e sem corte.\n- Geração inteligente do PDF e qualidades Alta / Média / Compacta.\n- Publicação direta em GitHub Releases.\n\nRelease: `v0.3.1`.\n''', encoding='utf-8')

path.write_text(text, encoding="utf-8")
print("Windows v0.3.1 aplicado com sucesso")

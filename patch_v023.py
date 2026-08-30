from pathlib import Path

path = Path('main.py')
text = path.read_text(encoding='utf-8')

if 'APP_VERSION = "0.2.3"' in text:
    print('main.py já está na v0.2.3; nenhum ajuste necessário.')
    raise SystemExit(0)

replacements = [
    ('APP_VERSION = "0.2.2"', 'APP_VERSION = "0.2.3"'),
    ('self.setMinimumSize(420, 520)', 'self.setMinimumSize(260, 260)'),
    ('available = self.contentsRect().adjusted(14, 14, -14, -14)', 'available = self.contentsRect().adjusted(18, 18, -18, -18)'),
    ('workspace_layout.setContentsMargins(18, 16, 18, 12)', 'workspace_layout.setContentsMargins(14, 12, 14, 10)'),
    ('workspace_layout.setSpacing(12)', 'workspace_layout.setSpacing(10)'),
    ('left.setMinimumWidth(235)', 'left.setMinimumWidth(280)'),
    ('left.setMaximumWidth(290)', 'left.setMaximumWidth(330)'),
    ('left_layout.setContentsMargins(16, 16, 16, 16)', 'left_layout.setContentsMargins(14, 14, 14, 14)'),
    ('left_layout.setSpacing(10)', 'left_layout.setSpacing(8)'),
    ('btn_img.setMinimumHeight(52)', 'btn_img.setMinimumHeight(44)'),
    ('btn_pdf.setMinimumHeight(52)', 'btn_pdf.setMinimumHeight(44)'),
    ('btn_cover.setMinimumHeight(52)', 'btn_cover.setMinimumHeight(44)'),
    ('tools_layout.setContentsMargins(10, 10, 10, 10)', 'tools_layout.setContentsMargins(9, 9, 9, 9)'),
    ('tools_layout.setSpacing(7)', 'tools_layout.setSpacing(6)'),
    ('b.setMinimumHeight(38)', 'b.setMinimumHeight(34)'),
    ('drop.setMinimumHeight(130)', 'drop.setMinimumHeight(92)'),
    ('right.setMinimumWidth(280)', 'right.setMinimumWidth(295)'),
    ('right.setMaximumWidth(340)', 'right.setMaximumWidth(335)'),
    ('self.cover_preview.setMinimumHeight(145)', 'self.cover_preview.setMinimumHeight(105)'),
    ('self.cover_preview.setMaximumHeight(175)', 'self.cover_preview.setMaximumHeight(125)'),
    ('btn_generate.setMinimumHeight(58)', 'btn_generate.setMinimumHeight(52)'),
    ('splitter.setSizes([250, 820, 310])', 'splitter.setSizes([300, 900, 315])'),
    ('self.list.setIconSize(QSize(105, 105))', 'self.list.setIconSize(QSize(82, 82))'),
    ('self.list.setGridSize(QSize(150, 132))', 'self.list.setGridSize(QSize(132, 104))'),
    ('self.list.setSpacing(6)', 'self.list.setSpacing(5)'),
    ('self.list.setFixedHeight(142)', 'self.list.setFixedHeight(112)'),
    ("#appTitle { font-size:26px;", "#appTitle { font-size:24px;"),
    ("#dropZone { background:#0e1826; color:#aebed1; border:1px dashed #667b93; border-radius:10px; padding:14px; font-size:14px; }", "#dropZone { background:#0e1826; color:#aebed1; border:1px dashed #667b93; border-radius:10px; padding:10px; font-size:13px; }"),
    ("#tipBox { color:#a3b4c8; background:#142235; border:1px solid #28405a; border-radius:8px; padding:10px; }", "#tipBox { color:#a3b4c8; background:#142235; border:1px solid #28405a; border-radius:8px; padding:8px; font-size:12px; }"),
]

for old, new in replacements:
    if old not in text:
        raise SystemExit(f'Trecho não encontrado: {old}')
    text = text.replace(old, new, 1)

needle = "        self._rubber = QRect()\n\n    def set_crop_mode(self, enabled: bool):"
insert = "        self._rubber = QRect()\n\n    def sizeHint(self):\n        return QSize(640, 480)\n\n    def minimumSizeHint(self):\n        return QSize(260, 260)\n\n    def set_crop_mode(self, enabled: bool):"
if needle not in text:
    raise SystemExit('Ponto de inserção do sizeHint não encontrado')
text = text.replace(needle, insert, 1)

needle = "        tip.setWordWrap(True)\n        left_layout.addWidget(tip)"
insert = "        tip.setWordWrap(True)\n        tip.setMaximumHeight(68)\n        left_layout.addWidget(tip)"
if needle not in text:
    raise SystemExit('Ponto de ajuste da dica não encontrado')
text = text.replace(needle, insert, 1)

needle = "        info.setWordWrap(True)\n        f_layout.addWidget(info)"
insert = "        info.setWordWrap(True)\n        info.setMaximumHeight(130)\n        f_layout.addWidget(info)"
if needle not in text:
    raise SystemExit('Ponto de ajuste do card PDF inteligente não encontrado')
text = text.replace(needle, insert, 1)

needle = "        splitter.setChildrenCollapsible(False)\n        workspace_layout.addWidget(splitter, 1)"
insert = "        splitter.setChildrenCollapsible(False)\n        splitter.setHandleWidth(6)\n        workspace_layout.addWidget(splitter, 1)"
if needle not in text:
    raise SystemExit('Ponto de ajuste do splitter não encontrado')
text = text.replace(needle, insert, 1)

path.write_text(text, encoding='utf-8')
print('main.py atualizado para v0.2.3')

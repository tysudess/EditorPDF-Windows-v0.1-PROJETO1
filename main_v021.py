import sys
from copy import deepcopy

import main as base
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QListWidgetItem, QPushButton

base.APP_VERSION = "0.2.1"


class EditorPDFv021(base.EditorPDF):
    """Atualizacao v0.2.1 sobre a base moderna v0.2.0."""

    def __init__(self):
        self._undo_stack = []
        super().__init__()
        self._install_crop_tools_outside_preview()
        self._install_undo_controls()
        self.statusBar().showMessage("Pronto — Ctrl+Z desfaz a ultima edicao")

    def _install_crop_tools_outside_preview(self):
        # Reutiliza os botoes existentes, apenas movendo-os para a coluna ACOES.
        clear_button = None
        for button in self.findChildren(QPushButton):
            if button.text() == "Remover recorte":
                clear_button = button
                break

        splitter = self.findChildren(base.QSplitter)
        if not splitter:
            return
        left_panel = splitter[0].widget(0)
        left_layout = left_panel.layout()
        if left_layout is None:
            return

        crop_card = QFrame()
        crop_card.setObjectName("cropToolsCard")
        crop_row = QHBoxLayout(crop_card)
        crop_row.setContentsMargins(0, 0, 0, 0)
        crop_row.setSpacing(7)

        self.btn_crop.setParent(crop_card)
        self.btn_crop.setObjectName("editPrimary")
        crop_row.addWidget(self.btn_crop)

        if clear_button is not None:
            self.btn_clear_crop = clear_button
            self.btn_clear_crop.setParent(crop_card)
            crop_row.addWidget(self.btn_clear_crop)

        # Entra antes da zona de arrastar/soltar, deixando a imagem totalmente livre.
        insert_at = min(4, max(0, left_layout.count() - 1))
        left_layout.insertWidget(insert_at, crop_card)

    def _install_undo_controls(self):
        self.undo_action = QAction("Desfazer", self)
        self.undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self.undo_action.setShortcutContext(Qt.ApplicationShortcut)
        self.undo_action.triggered.connect(self.undo_last)
        self.addAction(self.undo_action)

        self.btn_undo = QPushButton("↶  Desfazer  Ctrl+Z")
        self.btn_undo.setObjectName("topAction")
        self.btn_undo.clicked.connect(self.undo_last)

        headers = [f for f in self.findChildren(QFrame) if f.objectName() == "header"]
        if headers:
            layout = headers[0].layout()
            # Insere antes dos botoes Imagem / PDF / Exportar.
            index = max(0, layout.count() - 3)
            layout.insertWidget(index, self.btn_undo)

        self._update_undo_enabled()

    def _update_undo_enabled(self):
        enabled = bool(self._undo_stack)
        if hasattr(self, "undo_action"):
            self.undo_action.setEnabled(enabled)
        if hasattr(self, "btn_undo"):
            self.btn_undo.setEnabled(enabled)

    def _push_page_state(self, page):
        if not page:
            return
        self._undo_stack.append({
            "type": "page_state",
            "uid": page.uid,
            "rotation": page.rotation,
            "crop": deepcopy(page.crop),
        })
        self._undo_stack = self._undo_stack[-30:]
        self._update_undo_enabled()

    def apply_crop(self, x, y, w, h):
        page = self.current_page()
        if page:
            self._push_page_state(page)
        super().apply_crop(x, y, w, h)

    def clear_crop(self):
        page = self.current_page()
        if not page or page.crop is None:
            return
        self._push_page_state(page)
        super().clear_crop()

    def rotate_current(self, delta):
        page = self.current_page()
        if not page:
            return
        self._push_page_state(page)
        super().rotate_current(delta)

    def delete_current(self):
        row = self.list.currentRow()
        item = self.list.currentItem()
        page = self.current_page()
        if row < 0 or item is None or page is None:
            return

        self._undo_stack.append({
            "type": "delete",
            "row": row,
            "label": item.text(),
            "page": deepcopy(page),
        })
        self._undo_stack = self._undo_stack[-30:]
        self._update_undo_enabled()
        super().delete_current()

    def undo_last(self):
        if not self._undo_stack:
            self.statusBar().showMessage("Nada para desfazer.", 2000)
            return

        action = self._undo_stack.pop()
        kind = action.get("type")

        if kind == "page_state":
            page = self.pages.get(action["uid"])
            if page is not None:
                page.rotation = action["rotation"]
                page.crop = deepcopy(action["crop"])
                for row in range(self.list.count()):
                    item = self.list.item(row)
                    if item.data(Qt.UserRole) == page.uid:
                        self.list.setCurrentRow(row)
                        break
                self.crop_mode = False
                self.preview.set_crop_mode(False)
                self.btn_crop.setText("⌗  Selecionar corte")
                self.refresh_preview()
                self.refresh_current_thumbnail()
                self.statusBar().showMessage("Ultima edicao desfeita.", 3000)

        elif kind == "delete":
            page = action["page"]
            self.pages[page.uid] = page
            item = QListWidgetItem(action["label"])
            item.setData(Qt.UserRole, page.uid)
            thumb = self.make_thumbnail(page)
            if thumb:
                item.setIcon(QIcon(thumb))
            row = max(0, min(action["row"], self.list.count()))
            self.list.insertItem(row, item)
            self.list.setCurrentRow(row)
            if hasattr(self, "pages_count"):
                self.pages_count.setText(f"{self.list.count()} pagina(s)")
            self.statusBar().showMessage("Pagina excluida restaurada.", 3000)

        self._update_undo_enabled()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(base.APP_NAME)
    app.setWindowIcon(QIcon(str(base.resource_path("assets/editor_pdf_icon.png"))))
    window = EditorPDFv021()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

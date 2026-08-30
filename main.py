import copy
import io
import json
import os
import shutil
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image, ImageOps
from PySide6.QtCore import Qt, QRect, QRectF, QSize, Signal
from PySide6.QtGui import QAction, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QListView,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "Editor de PDF"
APP_VERSION = "0.2.2"
STANDARD_PAGE_W = 595.276  # largura A4 em pontos; todas as paginas internas usam esta largura
CONTENT_MARGIN_PT = 2.0    # margem interna minima (aprox. 0,7 mm)
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
SUPPORTED_DROP_EXTS = SUPPORTED_IMAGE_EXTS | {".pdf"}


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(relative: str) -> Path:
    bundle = Path(getattr(sys, "_MEIPASS", base_dir()))
    return bundle / relative


def data_dir() -> Path:
    p = base_dir() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    return data_dir() / "config.json"


def load_config() -> dict:
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(data: dict) -> None:
    try:
        config_path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


@dataclass
class PageData:
    uid: str
    kind: str  # image | pdf
    path: str
    page_no: int = 0
    rotation: int = 0
    crop: Optional[Tuple[float, float, float, float]] = None


class CropLabel(QLabel):
    cropSelected = Signal(float, float, float, float)

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(420, 520)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#151922; border:1px solid #2d3544; border-radius:8px;")
        self._source_pixmap: Optional[QPixmap] = None
        self._display_rect = QRect()
        self._crop_mode = False
        self._dragging = False
        self._start = None
        self._rubber = QRect()

    def set_crop_mode(self, enabled: bool):
        self._crop_mode = enabled
        self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)
        if not enabled:
            self._dragging = False
            self._rubber = QRect()
            self.update()

    def set_source_pixmap(self, pixmap: Optional[QPixmap]):
        self._source_pixmap = pixmap
        self._rubber = QRect()
        self.update_scaled()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_scaled()

    def update_scaled(self):
        if not self._source_pixmap or self._source_pixmap.isNull():
            self.clear()
            self._display_rect = QRect()
            return
        available = self.contentsRect().adjusted(14, 14, -14, -14)
        scaled = self._source_pixmap.scaled(
            available.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        super().setPixmap(scaled)
        x = available.x() + (available.width() - scaled.width()) // 2
        y = available.y() + (available.height() - scaled.height()) // 2
        self._display_rect = QRect(x, y, scaled.width(), scaled.height())
        self.update()

    def mousePressEvent(self, event):
        if self._crop_mode and event.button() == Qt.LeftButton and self._display_rect.contains(event.position().toPoint()):
            self._dragging = True
            self._start = event.position().toPoint()
            self._rubber = QRect(self._start, self._start)
            self.update()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._crop_mode and self._dragging:
            p = event.position().toPoint()
            p.setX(max(self._display_rect.left(), min(p.x(), self._display_rect.right())))
            p.setY(max(self._display_rect.top(), min(p.y(), self._display_rect.bottom())))
            self._rubber = QRect(self._start, p).normalized()
            self.update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._crop_mode and self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            r = self._rubber.intersected(self._display_rect)
            if r.width() >= 20 and r.height() >= 20 and self._display_rect.width() > 0 and self._display_rect.height() > 0:
                x = (r.left() - self._display_rect.left()) / self._display_rect.width()
                y = (r.top() - self._display_rect.top()) / self._display_rect.height()
                w = r.width() / self._display_rect.width()
                h = r.height() / self._display_rect.height()
                self.cropSelected.emit(x, y, w, h)
            self._rubber = QRect()
            self.update()
        else:
            super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._crop_mode and not self._rubber.isNull():
            painter = QPainter(self)
            pen = QPen(Qt.white, 2, Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(self._rubber)


class PageListWidget(QListWidget):
    """Lista que mantém a reordenação interna e também aceita arquivos do Explorer."""

    filesDropped = Signal(list)

    @staticmethod
    def _local_supported_paths(event) -> list[str]:
        if not event.mimeData().hasUrls():
            return []
        paths: list[str] = []
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if Path(path).is_file() and Path(path).suffix.lower() in SUPPORTED_DROP_EXTS:
                paths.append(path)
        return paths

    def dragEnterEvent(self, event):
        if self._local_supported_paths(event):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._local_supported_paths(event):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        paths = self._local_supported_paths(event)
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()
            return
        # Continua permitindo arrastar as miniaturas para reorganizar páginas.
        super().dropEvent(event)


class EditorPDF(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}")
        icon_path = resource_path("assets/editor_pdf_icon.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1480, 900)
        self.setMinimumSize(1120, 720)
        self.setAcceptDrops(True)

        self.pages: dict[str, PageData] = {}
        self.current_uid: Optional[str] = None
        self.crop_mode = False
        self.undo_stack: list[dict] = []
        self.config = load_config()

        self.default_cover = self._resolve_cover_path()

        self._build_ui()
        self._apply_theme()
        self._setup_shortcuts()
        self.statusBar().showMessage("Pronto")

    def _resolve_cover_path(self) -> Path:
        configured = self.config.get("cover_path")
        if configured and Path(configured).exists():
            return Path(configured)
        return resource_path("assets/capa_padrao.png")

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Cabeçalho moderno
        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 14, 22, 14)
        header_layout.setSpacing(12)

        logo = QLabel()
        icon_png = resource_path("assets/editor_pdf_icon.png")
        if icon_png.exists():
            logo.setPixmap(QPixmap(str(icon_png)).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setFixedSize(52, 52)
        header_layout.addWidget(logo)

        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("Editor de PDF")
        title.setObjectName("appTitle")
        subtitle = QLabel("Organize, edite e exporte documentos com rapidez")
        subtitle.setObjectName("appSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)
        header_layout.addStretch(1)

        self.btn_undo = QPushButton("↶  Desfazer  Ctrl+Z")
        self.btn_undo.setObjectName("topAction")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self.undo_last_action)

        btn_top_img = QPushButton("＋  Imagem")
        btn_top_img.setObjectName("topAction")
        btn_top_img.clicked.connect(self.add_images)
        btn_top_pdf = QPushButton("▣  PDF")
        btn_top_pdf.setObjectName("topAction")
        btn_top_pdf.clicked.connect(self.add_pdf)
        btn_top_export = QPushButton("Exportar PDF")
        btn_top_export.setObjectName("topPrimary")
        btn_top_export.clicked.connect(self.generate_pdf)
        header_layout.addWidget(self.btn_undo)
        header_layout.addWidget(btn_top_img)
        header_layout.addWidget(btn_top_pdf)
        header_layout.addWidget(btn_top_export)
        outer.addWidget(header)

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(18, 16, 18, 12)
        workspace_layout.setSpacing(12)
        outer.addWidget(workspace, 1)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        workspace_layout.addWidget(splitter, 1)

        # AÇÕES — coluna esquerda
        left = QFrame()
        left.setObjectName("panel")
        left.setMinimumWidth(235)
        left.setMaximumWidth(290)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(10)

        left_title = QLabel("AÇÕES")
        left_title.setObjectName("sectionTitle")
        left_layout.addWidget(left_title)

        btn_img = QPushButton("▧   Adicionar imagem")
        btn_img.setObjectName("primaryAction")
        btn_img.setMinimumHeight(52)
        btn_img.clicked.connect(self.add_images)
        left_layout.addWidget(btn_img)

        btn_pdf = QPushButton("▣   Adicionar PDF")
        btn_pdf.setObjectName("secondaryAction")
        btn_pdf.setMinimumHeight(52)
        btn_pdf.clicked.connect(self.add_pdf)
        left_layout.addWidget(btn_pdf)

        btn_cover = QPushButton("▤   Alterar capa padrão")
        btn_cover.setObjectName("secondaryAction")
        btn_cover.setMinimumHeight(52)
        btn_cover.clicked.connect(self.choose_cover)
        left_layout.addWidget(btn_cover)

        # Todas as ferramentas de edição ficam FORA da área de pré-visualização.
        edit_tools = QFrame()
        edit_tools.setObjectName("cropToolsCard")
        tools_layout = QVBoxLayout(edit_tools)
        tools_layout.setContentsMargins(10, 10, 10, 10)
        tools_layout.setSpacing(7)
        tools_title = QLabel("EDIÇÃO DA PÁGINA")
        tools_title.setObjectName("fieldLabel")
        tools_layout.addWidget(tools_title)

        self.btn_crop = QPushButton("⌗  Selecionar corte")
        self.btn_crop.setObjectName("editPrimary")
        self.btn_crop.clicked.connect(self.toggle_crop)
        self.btn_clear_crop = QPushButton("Remover recorte")
        self.btn_clear_crop.clicked.connect(self.clear_crop)
        btn_left = QPushButton("↶  Girar à esquerda")
        btn_left.clicked.connect(lambda: self.rotate_current(-90))
        btn_right = QPushButton("↷  Girar à direita")
        btn_right.clicked.connect(lambda: self.rotate_current(90))
        btn_del = QPushButton("⌫  Excluir página")
        btn_del.clicked.connect(self.delete_current)

        for b in (self.btn_crop, self.btn_clear_crop, btn_left, btn_right, btn_del):
            b.setMinimumHeight(38)
            tools_layout.addWidget(b)
        left_layout.addWidget(edit_tools)

        drop = QLabel("☁\n\nArraste imagens\nou PDFs aqui\n\nJPG • PNG • WebP • PDF")
        drop.setObjectName("dropZone")
        drop.setAlignment(Qt.AlignCenter)
        drop.setMinimumHeight(130)
        drop.setWordWrap(True)
        left_layout.addWidget(drop)

        tip = QLabel("ⓘ  Você também pode reorganizar as páginas arrastando as miniaturas na faixa inferior.")
        tip.setObjectName("tipBox")
        tip.setWordWrap(True)
        left_layout.addWidget(tip)
        left_layout.addStretch(1)
        splitter.addWidget(left)

        # PRÉ-VISUALIZAÇÃO — centro
        center = QFrame()
        center.setObjectName("panel")
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(14, 14, 14, 14)
        center_layout.setSpacing(10)

        center_head = QHBoxLayout()
        preview_title = QLabel("PRÉ-VISUALIZAÇÃO")
        preview_title.setObjectName("sectionTitle")
        center_head.addWidget(preview_title)
        center_head.addStretch(1)
        self.page_indicator = QLabel("Nenhuma página selecionada")
        self.page_indicator.setObjectName("mutedText")
        center_head.addWidget(self.page_indicator)
        center_layout.addLayout(center_head)

        self.preview = CropLabel()
        self.preview.setObjectName("previewArea")
        self.preview.cropSelected.connect(self.apply_crop)
        center_layout.addWidget(self.preview, 1)

        splitter.addWidget(center)

        # CONFIGURAÇÕES — coluna direita
        right = QFrame()
        right.setObjectName("panel")
        right.setMinimumWidth(280)
        right.setMaximumWidth(340)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(10)

        right_title = QLabel("CONFIGURAÇÕES")
        right_title.setObjectName("sectionTitle")
        right_layout.addWidget(right_title)

        cover_box = QFrame()
        cover_box.setObjectName("settingsCard")
        cb_layout = QVBoxLayout(cover_box)
        cb_layout.setContentsMargins(12, 12, 12, 12)
        self.cover_check = QCheckBox("Incluir capa padrão")
        self.cover_check.setChecked(True)
        cb_layout.addWidget(self.cover_check)
        self.cover_preview = QLabel()
        self.cover_preview.setAlignment(Qt.AlignCenter)
        self.cover_preview.setMinimumHeight(145)
        self.cover_preview.setMaximumHeight(175)
        self.cover_preview.setObjectName("coverPreview")
        cb_layout.addWidget(self.cover_preview)
        cover_buttons = QHBoxLayout()
        btn_change = QPushButton("Trocar capa")
        btn_change.clicked.connect(self.choose_cover)
        btn_reset = QPushButton("Restaurar")
        btn_reset.clicked.connect(self.reset_cover)
        cover_buttons.addWidget(btn_change)
        cover_buttons.addWidget(btn_reset)
        cb_layout.addLayout(cover_buttons)
        right_layout.addWidget(cover_box)
        self.refresh_cover_preview()

        quality_box = QFrame()
        quality_box.setObjectName("settingsCard")
        q_layout = QVBoxLayout(quality_box)
        q_layout.setContentsMargins(12, 12, 12, 12)
        q_label = QLabel("Qualidade")
        q_label.setObjectName("fieldLabel")
        q_layout.addWidget(q_label)
        self.quality = QComboBox()
        self.quality.addItem("Alta (300 DPI)", 300)
        self.quality.addItem("Média (220 DPI)", 220)
        self.quality.addItem("Compacta (160 DPI)", 160)
        q_layout.addWidget(self.quality)
        right_layout.addWidget(quality_box)

        format_box = QFrame()
        format_box.setObjectName("settingsCard")
        f_layout = QVBoxLayout(format_box)
        f_layout.setContentsMargins(12, 12, 12, 12)
        info = QLabel(
            "PDF inteligente\n\n"
            "• Capa sempre inteira, sem corte\n"
            "• Largura padronizada\n"
            "• Altura automática\n"
            "• Margem mínima\n"
            "• Vetor preservado quando possível"
        )
        info.setObjectName("info")
        info.setWordWrap(True)
        f_layout.addWidget(info)
        right_layout.addWidget(format_box)
        right_layout.addStretch(1)

        btn_generate = QPushButton("▣   GERAR PDF")
        btn_generate.setObjectName("generate")
        btn_generate.setMinimumHeight(58)
        btn_generate.clicked.connect(self.generate_pdf)
        right_layout.addWidget(btn_generate)
        splitter.addWidget(right)
        splitter.setSizes([250, 820, 310])

        # Faixa de miniaturas inferior
        pages_panel = QFrame()
        pages_panel.setObjectName("pagesPanel")
        pages_layout = QVBoxLayout(pages_panel)
        pages_layout.setContentsMargins(12, 10, 12, 10)
        pages_layout.setSpacing(7)

        pages_head = QHBoxLayout()
        pages_title = QLabel("PÁGINAS")
        pages_title.setObjectName("sectionTitle")
        pages_head.addWidget(pages_title)
        pages_head.addWidget(QLabel("arraste para reordenar"))
        pages_head.addStretch(1)
        self.pages_count = QLabel("0 página(s)")
        self.pages_count.setObjectName("mutedText")
        pages_head.addWidget(self.pages_count)
        pages_layout.addLayout(pages_head)

        self.list = PageListWidget()
        self.list.setViewMode(QListView.IconMode)
        self.list.setFlow(QListView.LeftToRight)
        self.list.setWrapping(False)
        self.list.setResizeMode(QListView.Adjust)
        self.list.setMovement(QListView.Snap)
        self.list.setIconSize(QSize(105, 105))
        self.list.setGridSize(QSize(150, 132))
        self.list.setSpacing(6)
        self.list.setFixedHeight(142)
        self.list.setDragDropMode(QListWidget.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.currentItemChanged.connect(self.on_current_changed)
        self.list.filesDropped.connect(self.import_dropped_files)
        pages_layout.addWidget(self.list)
        workspace_layout.addWidget(pages_panel)

        self.setStatusBar(QStatusBar())

    def _apply_theme(self):
        self.setStyleSheet("""
            * { font-family: 'Segoe UI'; font-size: 13px; }
            QMainWindow, #appRoot { background:#0b1220; color:#eef4ff; }
            #header { background:#101b2b; border-bottom:1px solid #26384f; }
            #appTitle { font-size:26px; font-weight:700; color:#f5f8ff; }
            #appSubtitle, #mutedText { color:#8fa3bd; }
            #panel, #pagesPanel { background:#111d2c; border:1px solid #263950; border-radius:12px; }
            #sectionTitle { color:#c7d3e3; font-size:13px; font-weight:700; letter-spacing:1px; }
            QPushButton { background:#1a2a3e; color:#edf4ff; border:1px solid #314861; border-radius:8px; padding:9px 12px; }
            QPushButton:hover { background:#233951; border-color:#47709a; }
            QPushButton:pressed { background:#152639; }
            #primaryAction, #topPrimary, #generate, #editPrimary { background:#1769d2; border:1px solid #2c82ea; font-weight:700; }
            #primaryAction:hover, #topPrimary:hover, #generate:hover, #editPrimary:hover { background:#2379e5; }
            #secondaryAction { text-align:left; padding-left:16px; }
            #topAction, #topPrimary { min-height:34px; }
            #dropZone { background:#0e1826; color:#aebed1; border:1px dashed #667b93; border-radius:10px; padding:14px; font-size:14px; }
            #tipBox { color:#a3b4c8; background:#142235; border:1px solid #28405a; border-radius:8px; padding:10px; }
            #previewArea { background:#0b1420; border:1px solid #263a51; border-radius:10px; }
            #editBar { background:#0e1826; border:1px solid #263950; border-radius:9px; }
            #settingsCard, #cropToolsCard { background:#152235; border:1px solid #2a4058; border-radius:10px; }
            #coverPreview { background:#0b1420; border:1px solid #263a51; border-radius:7px; }
            #fieldLabel { color:#c7d3e3; font-weight:600; }
            #info { color:#9fb1c7; line-height:1.35; }
            QComboBox { background:#0e1928; color:#eef4ff; border:1px solid #38516d; border-radius:7px; padding:9px; }
            QComboBox QAbstractItemView { background:#101b2b; color:#eef4ff; selection-background-color:#1769d2; }
            QCheckBox { color:#eef4ff; spacing:8px; }
            QListWidget { background:#0d1724; border:1px solid #253a51; border-radius:9px; padding:5px; outline:0; }
            QListWidget::item { background:#152235; border:1px solid #2a4058; border-radius:8px; padding:5px; margin:2px; }
            QListWidget::item:hover { border-color:#4c759e; background:#1a2c42; }
            QListWidget::item:selected { background:#163e70; border:2px solid #2f8cff; color:white; }
            QSplitter::handle { background:#0b1220; width:7px; }
            QStatusBar { background:#09101a; color:#90a4bc; border-top:1px solid #1f3146; }
            QScrollBar:horizontal { height:9px; background:#0d1724; }
            QScrollBar::handle:horizontal { background:#38516d; border-radius:4px; min-width:30px; }
            QScrollBar:vertical { width:9px; background:#0d1724; }
            QScrollBar::handle:vertical { background:#38516d; border-radius:4px; min-height:30px; }
        """)

    def _setup_shortcuts(self):
        self.undo_action = QAction("Desfazer", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.setShortcutContext(Qt.ApplicationShortcut)
        self.undo_action.triggered.connect(self.undo_last_action)
        self.addAction(self.undo_action)
        self._update_undo_ui()

    def _update_undo_ui(self):
        enabled = bool(self.undo_stack)
        if hasattr(self, "undo_action"):
            self.undo_action.setEnabled(enabled)
        if hasattr(self, "btn_undo"):
            self.btn_undo.setEnabled(enabled)

    def _page_label(self, page: PageData) -> str:
        if page.kind == "pdf":
            return f"{Path(page.path).name} — pág. {page.page_no + 1}"
        return Path(page.path).name

    def _push_undo(self, description: str):
        order = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            order.append((item.data(Qt.UserRole), item.text()))
        self.undo_stack.append({
            "description": description,
            "pages": copy.deepcopy(self.pages),
            "order": order,
            "current_uid": self.current_uid,
        })
        if len(self.undo_stack) > 30:
            self.undo_stack.pop(0)
        self._update_undo_ui()

    def undo_last_action(self):
        if not self.undo_stack:
            return
        snapshot = self.undo_stack.pop()
        self.pages = copy.deepcopy(snapshot["pages"])

        self.list.blockSignals(True)
        self.list.clear()
        selected_row = -1
        for row, (uid, label) in enumerate(snapshot["order"]):
            page = self.pages.get(uid)
            if not page:
                continue
            item = QListWidgetItem(label or self._page_label(page))
            item.setData(Qt.UserRole, uid)
            thumb = self.make_thumbnail(page)
            if thumb:
                item.setIcon(QIcon(thumb))
            self.list.addItem(item)
            if uid == snapshot.get("current_uid"):
                selected_row = row
        self.list.blockSignals(False)

        self.crop_mode = False
        self.preview.set_crop_mode(False)
        self.btn_crop.setText("⌗  Selecionar corte")
        if hasattr(self, "pages_count"):
            self.pages_count.setText(f"{self.list.count()} página(s)")

        if self.list.count():
            if selected_row < 0 or selected_row >= self.list.count():
                selected_row = 0
            self.list.setCurrentRow(selected_row)
            self.on_current_changed(self.list.currentItem(), None)
        else:
            self.current_uid = None
            self.preview.set_source_pixmap(None)
            self.page_indicator.setText("Nenhuma página selecionada")

        self._update_undo_ui()
        self.statusBar().showMessage(f"Desfeito: {snapshot.get('description', 'última ação')}", 4000)

    def page_order(self) -> list[PageData]:
        ordered = []
        for i in range(self.list.count()):
            uid = self.list.item(i).data(Qt.UserRole)
            if uid in self.pages:
                ordered.append(self.pages[uid])
        return ordered

    @staticmethod
    def _supported_local_paths(event) -> list[str]:
        if not event.mimeData().hasUrls():
            return []
        paths: list[str] = []
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if Path(path).is_file() and Path(path).suffix.lower() in SUPPORTED_DROP_EXTS:
                paths.append(path)
        return paths

    def dragEnterEvent(self, event):
        if self._supported_local_paths(event):
            self.statusBar().showMessage("Solte para adicionar imagens/PDFs ao projeto")
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if self._supported_local_paths(event):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.statusBar().showMessage("Pronto", 1500)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        paths = self._supported_local_paths(event)
        if not paths:
            event.ignore()
            return
        self.import_dropped_files(paths)
        event.acceptProposedAction()

    def import_dropped_files(self, paths: list[str]):
        """Importa imagens e PDFs misturados, mantendo a ordem em que foram soltos."""
        added_images = 0
        added_pdf_pages = 0
        failed: list[tuple[str, str]] = []

        for p in paths:
            suffix = Path(p).suffix.lower()
            if suffix in SUPPORTED_IMAGE_EXTS:
                try:
                    # Valida antes de inserir para evitar um item quebrado na lista.
                    with Image.open(p) as img:
                        img.verify()
                    page = PageData(uid=str(uuid.uuid4()), kind="image", path=p)
                    self.pages[page.uid] = page
                    self._add_list_item(page, Path(p).name)
                    added_images += 1
                except Exception as exc:
                    failed.append((p, str(exc)))
            elif suffix == ".pdf":
                try:
                    doc = fitz.open(p)
                    count = doc.page_count
                    doc.close()
                    for n in range(count):
                        page = PageData(uid=str(uuid.uuid4()), kind="pdf", path=p, page_no=n)
                        self.pages[page.uid] = page
                        self._add_list_item(page, f"{Path(p).name} — pág. {n+1}")
                        added_pdf_pages += 1
                except Exception as exc:
                    failed.append((p, str(exc)))

        total = added_images + added_pdf_pages
        if total:
            parts = []
            if added_images:
                parts.append(f"{added_images} imagem(ns)")
            if added_pdf_pages:
                parts.append(f"{added_pdf_pages} página(s) de PDF")
            self.statusBar().showMessage("Adicionado por arrastar e soltar: " + " + ".join(parts), 5000)

        if failed:
            detalhes = "\n\n".join(f"{Path(path).name}: {erro}" for path, erro in failed[:5])
            if len(failed) > 5:
                detalhes += f"\n\n... e mais {len(failed) - 5} arquivo(s)."
            QMessageBox.warning(
                self,
                APP_NAME,
                "Alguns arquivos não puderam ser adicionados:\n\n" + detalhes,
            )

    def add_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Adicionar imagens", "", "Imagens (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"
        )
        if not paths:
            return
        for p in paths:
            page = PageData(uid=str(uuid.uuid4()), kind="image", path=p)
            self.pages[page.uid] = page
            self._add_list_item(page, Path(p).name)
        self.statusBar().showMessage(f"{len(paths)} imagem(ns) adicionada(s)", 4000)

    def add_pdf(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Adicionar PDF", "", "PDF (*.pdf)")
        if not paths:
            return
        total = 0
        for p in paths:
            try:
                doc = fitz.open(p)
                count = doc.page_count
                doc.close()
                for n in range(count):
                    page = PageData(uid=str(uuid.uuid4()), kind="pdf", path=p, page_no=n)
                    self.pages[page.uid] = page
                    self._add_list_item(page, f"{Path(p).name} — pág. {n+1}")
                    total += 1
            except Exception as exc:
                QMessageBox.warning(self, APP_NAME, f"Não foi possível abrir:\n{p}\n\n{exc}")
        self.statusBar().showMessage(f"{total} página(s) de PDF adicionada(s)", 4000)

    def _add_list_item(self, page: PageData, label: str):
        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, page.uid)
        thumb = self.make_thumbnail(page)
        if thumb:
            item.setIcon(QIcon(thumb))
        self.list.addItem(item)
        if hasattr(self, "pages_count"):
            self.pages_count.setText(f"{self.list.count()} página(s)")
        if self.list.count() == 1:
            self.list.setCurrentRow(0)

    def make_thumbnail(self, page: PageData) -> Optional[QPixmap]:
        try:
            img = self.render_qimage(page, dpi=55, apply_crop=True)
            if img.isNull():
                return None
            return QPixmap.fromImage(img).scaled(70, 95, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        except Exception:
            return None

    def on_current_changed(self, current, previous):
        if not current:
            self.current_uid = None
            self.preview.set_source_pixmap(None)
            if hasattr(self, "page_indicator"):
                self.page_indicator.setText("Nenhuma página selecionada")
            return
        self.current_uid = current.data(Qt.UserRole)
        if hasattr(self, "page_indicator"):
            self.page_indicator.setText(current.text())
        self.crop_mode = False
        self.preview.set_crop_mode(False)
        self.btn_crop.setText("⌗  Selecionar corte")
        self.refresh_preview()

    def current_page(self) -> Optional[PageData]:
        if self.current_uid:
            return self.pages.get(self.current_uid)
        return None

    def refresh_preview(self, full_for_crop: bool = False):
        page = self.current_page()
        if not page:
            self.preview.set_source_pixmap(None)
            return
        try:
            img = self.render_qimage(page, dpi=125, apply_crop=not full_for_crop)
            self.preview.set_source_pixmap(QPixmap.fromImage(img))
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, f"Erro na pré-visualização:\n{exc}")

    def render_qimage(self, page: PageData, dpi: int = 120, apply_crop: bool = True) -> QImage:
        if page.kind == "image":
            img = QImage(page.path)
            if img.isNull():
                raise RuntimeError("Imagem inválida ou formato não suportado.")
        else:
            doc = fitz.open(page.path)
            p = doc.load_page(page.page_no)
            scale = dpi / 72.0
            pix = p.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            data = pix.tobytes("png")
            doc.close()
            img = QImage.fromData(data)

        if page.rotation:
            img = img.transformed(QTransform().rotate(page.rotation), Qt.SmoothTransformation)

        if apply_crop and page.crop:
            x, y, w, h = page.crop
            rx = max(0, min(img.width() - 1, round(x * img.width())))
            ry = max(0, min(img.height() - 1, round(y * img.height())))
            rw = max(1, min(img.width() - rx, round(w * img.width())))
            rh = max(1, min(img.height() - ry, round(h * img.height())))
            img = img.copy(rx, ry, rw, rh)
        return img

    def toggle_crop(self):
        page = self.current_page()
        if not page:
            return
        self.crop_mode = not self.crop_mode
        self.preview.set_crop_mode(self.crop_mode)
        self.btn_crop.setText("Cancelar seleção" if self.crop_mode else "⌗  Selecionar corte")
        self.refresh_preview(full_for_crop=self.crop_mode)
        if self.crop_mode:
            self.statusBar().showMessage("Arraste sobre a área que deseja manter.")

    def apply_crop(self, x: float, y: float, w: float, h: float):
        page = self.current_page()
        if not page:
            return
        self._push_undo("recorte")
        page.crop = (x, y, w, h)
        self.crop_mode = False
        self.preview.set_crop_mode(False)
        self.btn_crop.setText("⌗  Selecionar corte")
        self.refresh_preview()
        self.refresh_current_thumbnail()
        self.statusBar().showMessage("Recorte aplicado. O arquivo original não foi alterado.", 4500)

    def clear_crop(self):
        page = self.current_page()
        if not page:
            return
        if page.crop is None:
            return
        self._push_undo("remoção do recorte")
        page.crop = None
        self.crop_mode = False
        self.preview.set_crop_mode(False)
        self.btn_crop.setText("⌗  Selecionar corte")
        self.refresh_preview()
        self.refresh_current_thumbnail()
        self.statusBar().showMessage("Recorte removido.", 3000)

    def rotate_current(self, delta: int):
        page = self.current_page()
        if not page:
            return
        self._push_undo("giro da página")
        page.rotation = (page.rotation + delta) % 360
        if page.crop is not None:
            page.crop = None
            self.statusBar().showMessage("Página girada. O recorte anterior foi removido para evitar deformação.", 5000)
        self.refresh_preview()
        self.refresh_current_thumbnail()

    def refresh_current_thumbnail(self):
        item = self.list.currentItem()
        page = self.current_page()
        if item and page:
            thumb = self.make_thumbnail(page)
            if thumb:
                item.setIcon(QIcon(thumb))

    def delete_current(self):
        row = self.list.currentRow()
        item = self.list.currentItem()
        if row < 0 or not item:
            return
        uid = item.data(Qt.UserRole)
        self._push_undo("exclusão da página")
        self.list.takeItem(row)
        self.pages.pop(uid, None)
        if hasattr(self, "pages_count"):
            self.pages_count.setText(f"{self.list.count()} página(s)")
        if self.list.count():
            self.list.setCurrentRow(min(row, self.list.count() - 1))
        else:
            self.current_uid = None
            self.preview.set_source_pixmap(None)

    def move_current(self, delta: int):
        row = self.list.currentRow()
        if row < 0:
            return
        target = row + delta
        if not (0 <= target < self.list.count()):
            return
        item = self.list.takeItem(row)
        self.list.insertItem(target, item)
        self.list.setCurrentRow(target)

    def refresh_cover_preview(self):
        if self.default_cover.exists():
            pix = QPixmap(str(self.default_cover))
            if not pix.isNull():
                self.cover_preview.setPixmap(pix.scaled(170, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return
        self.cover_preview.setText("Capa padrão indisponível")

    def choose_cover(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolher capa padrão", "", "Imagens (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not path:
            return
        try:
            img = Image.open(path)
            img.verify()
            target = data_dir() / "capa_padrao_usuario.png"
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.save(target, "PNG", optimize=True)
            self.default_cover = target
            self.config["cover_path"] = str(target)
            save_config(self.config)
            self.refresh_cover_preview()
            self.statusBar().showMessage("Nova capa padrão salva.", 3500)
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, f"Não foi possível usar essa imagem como capa:\n{exc}")

    def reset_cover(self):
        self.default_cover = resource_path("assets/capa_padrao.png")
        self.config.pop("cover_path", None)
        save_config(self.config)
        self.refresh_cover_preview()
        self.statusBar().showMessage("Capa padrão original restaurada.", 3500)

    def _pil_for_page(self, page: PageData, dpi: int) -> Image.Image:
        if page.kind == "image":
            img = Image.open(page.path)
            img = ImageOps.exif_transpose(img).convert("RGB")
        else:
            doc = fitz.open(page.path)
            p = doc.load_page(page.page_no)
            scale = dpi / 72.0
            pix = p.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            doc.close()
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")

        if page.rotation:
            img = img.rotate(-page.rotation, expand=True, resample=Image.Resampling.BICUBIC)
        if page.crop:
            x, y, w, h = page.crop
            left = round(x * img.width)
            top = round(y * img.height)
            right = round((x + w) * img.width)
            bottom = round((y + h) * img.height)
            left = max(0, min(img.width - 1, left))
            top = max(0, min(img.height - 1, top))
            right = max(left + 1, min(img.width, right))
            bottom = max(top + 1, min(img.height, bottom))
            img = img.crop((left, top, right, bottom))
        return img

    @staticmethod
    def _dynamic_page_rect(content_width: float, content_height: float, margin: float = CONTENT_MARGIN_PT) -> tuple[fitz.Rect, fitz.Rect]:
        """
        Cria uma pagina com largura fixa e altura ajustada ao conteudo.
        O conteudo nunca e cortado nem deformado; sobra apenas a margem minima.
        """
        content_width = max(1.0, float(content_width))
        content_height = max(1.0, float(content_height))
        inner_w = STANDARD_PAGE_W - (2.0 * margin)
        scale = inner_w / content_width
        inner_h = content_height * scale
        page_h = inner_h + (2.0 * margin)
        page_rect = fitz.Rect(0, 0, STANDARD_PAGE_W, page_h)
        inner_rect = fitz.Rect(margin, margin, STANDARD_PAGE_W - margin, page_h - margin)
        return page_rect, inner_rect

    def _insert_cover_page(self, out: fitz.Document, image_path: Path | str):
        """Insere a capa inteira, sem recorte, sem deformacao e sem borda branca."""
        with Image.open(image_path) as raw:
            img = ImageOps.exif_transpose(raw).convert("RGB")
            page_w = STANDARD_PAGE_W
            page_h = page_w * (img.height / max(1, img.width))
            page_rect = fitz.Rect(0, 0, page_w, page_h)
            page = out.new_page(width=page_w, height=page_h)

            # PNG e usado para evitar perda adicional de qualidade na capa.
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            page.insert_image(page_rect, stream=buffer.getvalue(), keep_proportion=True)

    def generate_pdf(self):
        ordered = self.page_order()
        if not ordered and not self.cover_check.isChecked():
            QMessageBox.information(self, APP_NAME, "Adicione pelo menos uma imagem/PDF ou habilite a capa padrão.")
            return

        suggested = "RADAR DE NOTICIAS.pdf" if self.cover_check.isChecked() else "documento.pdf"
        out_path, _ = QFileDialog.getSaveFileName(self, "Gerar PDF", suggested, "PDF (*.pdf)")
        if not out_path:
            return
        if not out_path.lower().endswith(".pdf"):
            out_path += ".pdf"

        dpi = int(self.quality.currentData())
        out = fitz.open()
        pdf_cache: dict[str, fitz.Document] = {}

        try:
            if self.cover_check.isChecked():
                if not self.default_cover.exists():
                    raise RuntimeError("A capa padrão não foi encontrada.")
                self._insert_cover_page(out, self.default_cover)

            for index, page_data in enumerate(ordered, start=1):
                self.statusBar().showMessage(f"Gerando página {index} de {len(ordered)}...")
                QApplication.processEvents()

                # Preserve vector quality for untouched PDF pages.
                if page_data.kind == "pdf" and page_data.rotation == 0 and page_data.crop is None:
                    if page_data.path not in pdf_cache:
                        pdf_cache[page_data.path] = fitz.open(page_data.path)
                    src = pdf_cache[page_data.path]
                    src_page = src.load_page(page_data.page_no)
                    r = src_page.rect
                    page_rect, content_rect = self._dynamic_page_rect(r.width, r.height)
                    new_page = out.new_page(width=page_rect.width, height=page_rect.height)
                    new_page.show_pdf_page(
                        content_rect, src, page_data.page_no, keep_proportion=True
                    )
                    continue

                img = self._pil_for_page(page_data, dpi=dpi)
                page_rect, content_rect = self._dynamic_page_rect(img.width, img.height)
                new_page = out.new_page(width=page_rect.width, height=page_rect.height)
                buffer = io.BytesIO()
                # Alta qualidade para paginas rasterizadas/editadas.
                img.save(buffer, format="JPEG", quality=97, subsampling=0, optimize=True)
                new_page.insert_image(
                    content_rect, stream=buffer.getvalue(), keep_proportion=True
                )

            if out.page_count == 0:
                raise RuntimeError("Nenhuma página foi gerada.")

            out.save(out_path, garbage=4, deflate=True, clean=True)
            out.close()
            for doc in pdf_cache.values():
                doc.close()

            self.statusBar().showMessage("PDF gerado com sucesso.", 5000)
            box = QMessageBox(self)
            box.setWindowTitle(APP_NAME)
            box.setIcon(QMessageBox.Information)
            box.setText("PDF gerado com sucesso!")
            box.setInformativeText(out_path)
            open_btn = box.addButton("Abrir pasta", QMessageBox.ActionRole)
            box.addButton("OK", QMessageBox.AcceptRole)
            box.exec()
            if box.clickedButton() == open_btn:
                folder = str(Path(out_path).resolve().parent)
                if sys.platform.startswith("win"):
                    os.startfile(folder)
                elif sys.platform == "darwin":
                    os.system(f'open "{folder}"')
                else:
                    os.system(f'xdg-open "{folder}" >/dev/null 2>&1 &')

        except Exception as exc:
            try:
                out.close()
            except Exception:
                pass
            for doc in pdf_cache.values():
                try:
                    doc.close()
                except Exception:
                    pass
            QMessageBox.critical(self, APP_NAME, f"Não foi possível gerar o PDF:\n\n{exc}")
            self.statusBar().showMessage("Falha ao gerar o PDF.", 5000)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(resource_path("assets/editor_pdf_icon.png"))))
    window = EditorPDF()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

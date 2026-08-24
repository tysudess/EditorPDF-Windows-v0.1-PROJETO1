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
from PySide6.QtGui import QAction, QIcon, QImage, QPainter, QPen, QPixmap, QTransform
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
APP_VERSION = "0.1.1"
STANDARD_PAGE_W = 595.276  # largura A4 em pontos; todas as paginas internas usam esta largura
CONTENT_MARGIN_PT = 2.0    # margem interna minima (aprox. 0,7 mm)


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


class EditorPDF(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}")
        self.resize(1260, 790)
        self.setMinimumSize(980, 650)

        self.pages: dict[str, PageData] = {}
        self.current_uid: Optional[str] = None
        self.crop_mode = False
        self.config = load_config()

        self.default_cover = self._resolve_cover_path()

        self._build_ui()
        self._apply_theme()
        self.statusBar().showMessage("Pronto")

    def _resolve_cover_path(self) -> Path:
        configured = self.config.get("cover_path")
        if configured and Path(configured).exists():
            return Path(configured)
        return resource_path("assets/capa_padrao.png")

    def _build_ui(self):
        toolbar = QToolBar("Principal")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        act_img = QAction("Adicionar imagem", self)
        act_img.triggered.connect(self.add_images)
        toolbar.addAction(act_img)

        act_pdf = QAction("Adicionar PDF", self)
        act_pdf.triggered.connect(self.add_pdf)
        toolbar.addAction(act_pdf)

        toolbar.addSeparator()
        act_gen = QAction("Gerar PDF", self)
        act_gen.triggered.connect(self.generate_pdf)
        toolbar.addAction(act_gen)

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel("EDITOR DE PDF")
        title.setObjectName("title")
        subtitle = QLabel("Importe, recorte, organize e gere PDFs no padrão de capas")
        subtitle.setObjectName("subtitle")
        root_layout.addWidget(title)
        root_layout.addWidget(subtitle)

        splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(splitter, 1)

        # Left panel
        left = QFrame()
        left.setObjectName("panel")
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("PÁGINAS"))

        self.list = QListWidget()
        self.list.setIconSize(QSize(70, 95))
        self.list.setDragDropMode(QListWidget.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.currentItemChanged.connect(self.on_current_changed)
        left_layout.addWidget(self.list, 1)

        row1 = QHBoxLayout()
        btn_img = QPushButton("+ Imagem")
        btn_img.clicked.connect(self.add_images)
        btn_pdf = QPushButton("+ PDF")
        btn_pdf.clicked.connect(self.add_pdf)
        row1.addWidget(btn_img)
        row1.addWidget(btn_pdf)
        left_layout.addLayout(row1)

        row2 = QHBoxLayout()
        btn_up = QPushButton("↑")
        btn_up.setToolTip("Mover página para cima")
        btn_up.clicked.connect(lambda: self.move_current(-1))
        btn_down = QPushButton("↓")
        btn_down.setToolTip("Mover página para baixo")
        btn_down.clicked.connect(lambda: self.move_current(1))
        btn_del = QPushButton("Excluir")
        btn_del.clicked.connect(self.delete_current)
        row2.addWidget(btn_up)
        row2.addWidget(btn_down)
        row2.addWidget(btn_del)
        left_layout.addLayout(row2)

        splitter.addWidget(left)

        # Center preview
        center = QFrame()
        center.setObjectName("panel")
        center_layout = QVBoxLayout(center)
        center_layout.addWidget(QLabel("PRÉ-VISUALIZAÇÃO"))
        self.preview = CropLabel()
        self.preview.cropSelected.connect(self.apply_crop)
        center_layout.addWidget(self.preview, 1)

        edit_row = QHBoxLayout()
        self.btn_crop = QPushButton("Recortar")
        self.btn_crop.clicked.connect(self.toggle_crop)
        btn_clear_crop = QPushButton("Remover recorte")
        btn_clear_crop.clicked.connect(self.clear_crop)
        btn_left = QPushButton("↶ Girar")
        btn_left.clicked.connect(lambda: self.rotate_current(-90))
        btn_right = QPushButton("Girar ↷")
        btn_right.clicked.connect(lambda: self.rotate_current(90))
        edit_row.addWidget(self.btn_crop)
        edit_row.addWidget(btn_clear_crop)
        edit_row.addWidget(btn_left)
        edit_row.addWidget(btn_right)
        center_layout.addLayout(edit_row)

        splitter.addWidget(center)

        # Right panel
        right = QFrame()
        right.setObjectName("panel")
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("PDF FINAL"))

        cover_box = QFrame()
        cover_box.setObjectName("softPanel")
        cb_layout = QVBoxLayout(cover_box)
        self.cover_check = QCheckBox("Incluir capa padrão como primeira página")
        self.cover_check.setChecked(True)
        cb_layout.addWidget(self.cover_check)

        self.cover_preview = QLabel()
        self.cover_preview.setAlignment(Qt.AlignCenter)
        self.cover_preview.setMinimumHeight(190)
        self.cover_preview.setMaximumHeight(240)
        self.cover_preview.setStyleSheet("background:#11151c; border-radius:6px;")
        cb_layout.addWidget(self.cover_preview)
        self.refresh_cover_preview()

        cover_buttons = QHBoxLayout()
        btn_cover = QPushButton("Alterar capa")
        btn_cover.clicked.connect(self.choose_cover)
        btn_reset_cover = QPushButton("Restaurar")
        btn_reset_cover.clicked.connect(self.reset_cover)
        cover_buttons.addWidget(btn_cover)
        cover_buttons.addWidget(btn_reset_cover)
        cb_layout.addLayout(cover_buttons)
        right_layout.addWidget(cover_box)

        right_layout.addSpacing(8)
        right_layout.addWidget(QLabel("Qualidade para páginas editadas"))
        self.quality = QComboBox()
        self.quality.addItem("Alta - 300 dpi", 300)
        self.quality.addItem("Média - 220 dpi", 220)
        self.quality.addItem("Compacta - 160 dpi", 160)
        right_layout.addWidget(self.quality)

        info = QLabel(
            "Padrão do PDF:\n"
            "• Capa inteira, sem corte e sem borda branca\n"
            "• Páginas internas com largura padronizada\n"
            "• Altura automática para reduzir espaços brancos\n"
            "• Proporção preservada e margem mínima\n"
            "• PDF original preservado em vetor quando não editado"
        )
        info.setWordWrap(True)
        info.setObjectName("info")
        right_layout.addWidget(info)
        right_layout.addStretch(1)

        btn_generate = QPushButton("GERAR PDF")
        btn_generate.setObjectName("generate")
        btn_generate.setMinimumHeight(48)
        btn_generate.clicked.connect(self.generate_pdf)
        right_layout.addWidget(btn_generate)

        splitter.addWidget(right)
        splitter.setSizes([270, 690, 300])

        self.setStatusBar(QStatusBar())

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#0d1117; color:#e7edf5; font-size:13px; }
            QToolBar { background:#111722; border-bottom:1px solid #273041; spacing:7px; padding:6px; }
            QToolButton { background:#1b2431; border:1px solid #344156; border-radius:6px; padding:7px 10px; }
            QToolButton:hover { background:#263244; }
            #title { font-size:24px; font-weight:800; letter-spacing:1px; }
            #subtitle { color:#91a0b5; margin-bottom:5px; }
            #panel { background:#121821; border:1px solid #263143; border-radius:10px; }
            #softPanel { background:#161d28; border:1px solid #2a3547; border-radius:8px; }
            QPushButton { background:#1a2432; border:1px solid #34445a; border-radius:7px; padding:8px 10px; }
            QPushButton:hover { background:#243349; }
            QPushButton:pressed { background:#152033; }
            #generate { background:#26456f; font-weight:800; font-size:14px; }
            #generate:hover { background:#315a8f; }
            QListWidget { background:#0f141c; border:1px solid #263143; border-radius:7px; padding:4px; }
            QListWidget::item { padding:6px; border-radius:6px; }
            QListWidget::item:selected { background:#27364b; }
            QComboBox { background:#111722; border:1px solid #34445a; border-radius:6px; padding:7px; }
            QCheckBox { spacing:8px; }
            #info { color:#a9b6c8; background:#10161f; border:1px solid #253043; border-radius:7px; padding:10px; }
            QStatusBar { background:#0b0f15; color:#9eacbf; }
        """)

    def page_order(self) -> list[PageData]:
        ordered = []
        for i in range(self.list.count()):
            uid = self.list.item(i).data(Qt.UserRole)
            if uid in self.pages:
                ordered.append(self.pages[uid])
        return ordered

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
            return
        self.current_uid = current.data(Qt.UserRole)
        self.crop_mode = False
        self.preview.set_crop_mode(False)
        self.btn_crop.setText("Recortar")
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
        self.btn_crop.setText("Cancelar recorte" if self.crop_mode else "Recortar")
        self.refresh_preview(full_for_crop=self.crop_mode)
        if self.crop_mode:
            self.statusBar().showMessage("Arraste sobre a área que deseja manter.")

    def apply_crop(self, x: float, y: float, w: float, h: float):
        page = self.current_page()
        if not page:
            return
        page.crop = (x, y, w, h)
        self.crop_mode = False
        self.preview.set_crop_mode(False)
        self.btn_crop.setText("Recortar")
        self.refresh_preview()
        self.refresh_current_thumbnail()
        self.statusBar().showMessage("Recorte aplicado. O arquivo original não foi alterado.", 4500)

    def clear_crop(self):
        page = self.current_page()
        if not page:
            return
        page.crop = None
        self.crop_mode = False
        self.preview.set_crop_mode(False)
        self.btn_crop.setText("Recortar")
        self.refresh_preview()
        self.refresh_current_thumbnail()
        self.statusBar().showMessage("Recorte removido.", 3000)

    def rotate_current(self, delta: int):
        page = self.current_page()
        if not page:
            return
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
        self.list.takeItem(row)
        self.pages.pop(uid, None)
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
    window = EditorPDF()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

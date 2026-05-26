from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.path import Path as MplPath
from matplotlib.widgets import LassoSelector
from rdkit import Chem
from rdkit.Chem import Draw
from PySide6.QtCore import QByteArray, QEvent, QObject, QSize, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup, QColor, QImage, QPalette, QPainter, QPixmap, QResizeEvent
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QCheckBox,
    QAbstractItemView,
    QApplication,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStyle,
    QStyleFactory,
    QToolButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .analysis import AnalysisResult, AnalysisSettings, ColumnMapping, run_analysis
from .data_io import excel_sheet_names, load_table
from .project_file import PROJECT_SUFFIX, load_project, save_project


@dataclass
class PlotStyle:
    title: str
    color: str
    marker_size: int = 34
    edge_color: str = "black"
    opacity: float = 0.75
    show_outline: bool = True
    y_min: float | None = None
    y_max: float | None = None


class AnalysisWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)
    progress_changed = Signal(int, str)

    def __init__(
        self,
        data: pd.DataFrame,
        mapping: ColumnMapping,
        settings: AnalysisSettings,
    ) -> None:
        super().__init__()
        self.data = data
        self.mapping = mapping
        self.settings = settings

    @Slot()
    def run(self) -> None:
        try:
            result = run_analysis(self.data, self.mapping, self.settings, self.progress_changed.emit)
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.completed.emit(result)


class PausableFigureCanvas(FigureCanvasQTAgg):
    """Avoid expensive Matplotlib redraws during a continuous window resize."""

    def __init__(self, figure: Figure) -> None:
        super().__init__(figure)
        self.resize_redraw_paused = False

    def resizeEvent(self, event: QResizeEvent) -> None:
        if self.resize_redraw_paused:
            QWidget.resizeEvent(self, event)
            return
        super().resizeEvent(event)

    def finish_resize_pause(self) -> None:
        if not self.resize_redraw_paused:
            return
        self.resize_redraw_paused = False
        self.resizeEvent(QResizeEvent(self.size(), self.size()))
        self.draw_idle()


class PopoutWindow(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(title)
        self.resize(960, 720)
        self.content_layout = QVBoxLayout(self)
        self.view_kind = ""
        self.figure: Figure | None = None
        self.canvas: FigureCanvasQTAgg | None = None
        self.image_label: QLabel | None = None


class StructurePopoutWindow(PopoutWindow):
    def __init__(self, title: str, owner: "MainWindow") -> None:
        super().__init__(title, owner)
        self.owner = owner
        self.view_kind = "structures"
        header = QHBoxLayout()
        header.addWidget(QLabel("Selected Chemical Structures"))
        header.addStretch()
        save = QPushButton("Save...")
        save.clicked.connect(self.save_image)
        header.addWidget(save)
        self.content_layout.addLayout(header)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.viewport().installEventFilter(self)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.image_label.setStyleSheet("background: white;")
        self.scroll.setWidget(self.image_label)
        self.content_layout.addWidget(self.scroll)
        self.svg: str | None = None
        self.columns: int | None = None
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(120)
        self._resize_timer.timeout.connect(self.refresh)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if watched is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._resize_timer.start()
        return super().eventFilter(watched, event)

    def refresh(self) -> None:
        selected = self.owner._selected_frame()
        if selected is None or selected.empty:
            self.image_label.clear()
            self.svg = None
            return
        columns = min(len(selected.head(40)), max(1, self.scroll.viewport().width() // 240))
        if columns == self.columns and self.svg is not None:
            return
        self.columns = columns
        svg, pixmap = self.owner._render_structure_pixmap(selected, columns, self.owner._value_axis_label())
        self.svg = svg
        self.image_label.setPixmap(pixmap)

    def save_image(self) -> None:
        if self.svg is None or self.image_label.pixmap() is None:
            QMessageBox.information(self, "No Structures", "Select compounds before saving a structure image.")
            return
        self.owner._save_structure_image(self.svg, self.image_label.pixmap())


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._base_title = "Project Sweet Chem O' Mine - Chemical UMAP Explorer"
        self.setWindowTitle(self._base_title)
        self.resize(1420, 940)

        self.data: pd.DataFrame | None = None
        self.result: AnalysisResult | None = None
        self.selected_positions: list[int] = []
        self.project_path: Path | None = None
        self.source_filename: str | None = None
        self.source_bytes: bytes | None = None
        self._lasso: LassoSelector | None = None
        self._structure_columns: int | None = None
        self._structure_svg: str | None = None
        self._structure_render_cache: dict[tuple[object, ...], tuple[str, QPixmap]] = {}
        self._molecule_cache: dict[str, object] = {}
        self._analysis_thread: QThread | None = None
        self._analysis_worker: AnalysisWorker | None = None
        self._popout_windows: list[PopoutWindow] = []
        self.areas_of_interest: dict[str, list[int]] = {}
        self._dirty = False
        self._loading_state = False
        application = QApplication.instance()
        self._system_palette = QPalette(application.palette()) if application is not None else QPalette()
        self._theme_mode = "auto"
        self.umap_style = PlotStyle("Chemical Space UMAP", "RdYlGn_r", 20, "black", 0.75, False)
        self.bar_style = PlotStyle("Selected Compounds", "#d95f4b", edge_color="black")
        self._structure_resize_timer = QTimer(self)
        self._structure_resize_timer.setSingleShot(True)
        self._structure_resize_timer.setInterval(120)
        self._structure_resize_timer.timeout.connect(self._redraw_main_structure_after_resize)
        self._visual_resize_timer = QTimer(self)
        self._visual_resize_timer.setSingleShot(True)
        self._visual_resize_timer.setInterval(160)
        self._visual_resize_timer.timeout.connect(self._finish_visual_resize_pause)

        self._create_menu()
        self._create_interface()
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedSize(300, 20)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #6b6b6b; border-radius: 4px; background: #e8e8e8; }"
            "QProgressBar::chunk { background: #2ca25f; border-radius: 3px; }"
        )
        self.statusBar().addWidget(self.progress_bar)
        self.progress_bar.hide()
        self.statusBar().showMessage("Open a CSV or Excel table to begin.")
        if application is not None:
            application.styleHints().colorSchemeChanged.connect(self._system_color_scheme_changed)
        self.apply_theme("auto")

    def _create_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        open_action = QAction("&Open...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        save_action = QAction("&Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_current_project)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self.save_project_as)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        export_menu = self.menuBar().addMenu("&Export")
        export_aoi_action = QAction("Export &AOIs as CSV...", self)
        export_aoi_action.triggered.connect(self.export_areas_of_interest)
        export_menu.addAction(export_aoi_action)
        export_pdf_action = QAction("Export &Figures as PDF...", self)
        export_pdf_action.triggered.connect(self.export_figures_pdf)
        export_menu.addAction(export_pdf_action)

        view_menu = self.menuBar().addMenu("&View")
        reset_layout_action = QAction("&Reset Panel Layout", self)
        reset_layout_action.triggered.connect(self.reset_panel_layout)
        view_menu.addAction(reset_layout_action)
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("&Theme")
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)
        for text, theme in (("Auto", "auto"), ("Light", "light"), ("Dark", "dark")):
            action = QAction(text, self)
            action.setCheckable(True)
            action.setData(theme)
            action.triggered.connect(lambda _checked, choice=theme: self.apply_theme(choice))
            self.theme_group.addAction(action)
            theme_menu.addAction(action)
            if theme == "auto":
                action.setChecked(True)

        help_menu = self.menuBar().addMenu("&Help")
        guide_action = QAction("&Quick Guide", self)
        guide_action.triggered.connect(self.show_quick_guide)
        help_menu.addAction(guide_action)
        about_action = QAction("&About Sweet Chem O' Mine", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def _create_interface(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.addWidget(self._create_settings_panel())

        self.plots_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.plots_splitter.addWidget(self._create_aoi_panel())
        self.plots_splitter.addWidget(self._create_umap_panel())
        self.plots_splitter.addWidget(self._create_bar_panel())
        self.plots_splitter.setSizes([230, 700, 600])
        self.plots_splitter.splitterMoved.connect(lambda _pos, _index: self._begin_visual_resize_pause())

        self.panels_splitter = QSplitter(Qt.Orientation.Vertical)
        self.panels_splitter.addWidget(self.plots_splitter)
        self.panels_splitter.addWidget(self._create_structure_panel())
        self.panels_splitter.setSizes([560, 270])
        self.panels_splitter.splitterMoved.connect(lambda _pos, _index: self._begin_visual_resize_pause())
        root.addWidget(self.panels_splitter, stretch=1)
        self.setCentralWidget(central)

    def _set_dirty(self) -> None:
        if self._loading_state or self.data is None:
            return
        self._dirty = True
        self.setWindowTitle(f"* {self._base_title}")

    def _set_clean(self) -> None:
        self._dirty = False
        self.setWindowTitle(self._base_title)

    def _confirm_save_changes(self) -> bool:
        if not self._dirty:
            return True
        response = QMessageBox.question(
            self,
            "Unsaved Changes",
            "This project has unsaved changes. Save before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if response == QMessageBox.StandardButton.Cancel:
            return False
        if response == QMessageBox.StandardButton.Save:
            return self.save_current_project()
        return True

    def reset_panel_layout(self) -> None:
        self.settings_toggle.setChecked(True)
        self.plots_splitter.setSizes([230, 700, 600])
        self.panels_splitter.setSizes([560, 270])

    def apply_theme(self, theme: str) -> None:
        application = QApplication.instance()
        if application is None:
            return
        self._theme_mode = theme
        requested_theme = theme
        if theme == "auto":
            theme = "dark" if self._system_prefers_dark() else "light"
        application.setStyle(QStyleFactory.create("Fusion"))
        application.setPalette(self._dark_palette() if theme == "dark" else self._light_palette())
        for action in self.theme_group.actions():
            if action.data() == requested_theme:
                action.setChecked(True)
                break

    def _system_color_scheme_changed(self, _scheme) -> None:  # type: ignore[no-untyped-def]
        if self._theme_mode == "auto":
            self.apply_theme("auto")

    def _system_prefers_dark(self) -> bool:
        application = QApplication.instance()
        if application is None:
            return False
        scheme = application.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
        window_color = self._system_palette.color(QPalette.ColorRole.Window)
        return window_color.lightness() < 128

    @staticmethod
    def _light_palette() -> QPalette:
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(246, 246, 246))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(240, 240, 240))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 225))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.Text, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.Button, QColor(238, 238, 238))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(200, 0, 0))
        palette.setColor(QPalette.ColorRole.Link, QColor(0, 90, 180))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(40, 112, 190))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(110, 110, 110))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(135, 135, 135))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(135, 135, 135))
        return palette

    @staticmethod
    def _dark_palette() -> QPalette:
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(235, 235, 235))
        palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(55, 55, 55))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(235, 235, 235))
        palette.setColor(QPalette.ColorRole.Text, QColor(235, 235, 235))
        palette.setColor(QPalette.ColorRole.Button, QColor(55, 55, 55))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(235, 235, 235))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 100, 100))
        palette.setColor(QPalette.ColorRole.Link, QColor(90, 170, 255))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(150, 150, 150))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(125, 125, 125))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(125, 125, 125))
        return palette

    def show_quick_guide(self) -> None:
        QMessageBox.information(
            self,
            "Quick Guide",
            "1. Open a CSV or Excel data table.\n"
            "2. Map display name, SMILES, value, and an optional error bar column.\n"
            "3. Set parameters and run analysis.\n"
            "4. Select points on the UMAP plot to view results.\n"
            "5. Export AOIs or figures, or save the complete .scom project.",
        )

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Sweet Chem O' Mine",
            "Project Sweet Chem O' Mine\n\nChemical UMAP Explorer\n"
            "Desktop visualisation and selection of chemical-space assay data.",
        )

    def _create_settings_panel(self) -> QWidget:
        section = QWidget()
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(1)
        self.settings_toggle = QToolButton()
        self.settings_toggle.setText("Data Mapping and Analysis Settings")
        self.settings_toggle.setCheckable(True)
        self.settings_toggle.setChecked(True)
        self.settings_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.settings_toggle.setArrowType(Qt.ArrowType.DownArrow)
        self.settings_toggle.toggled.connect(self._toggle_settings_panel)
        settings_header = QHBoxLayout()
        settings_header.addWidget(self.settings_toggle)
        self.data_summary = QLabel("No data loaded")
        self.data_summary.setStyleSheet("color: #8a8a8a;")
        settings_header.addWidget(self.data_summary)
        settings_header.addStretch()
        section_layout.addLayout(settings_header)
        box = QGroupBox()
        self.settings_content = box
        layout = QGridLayout(box)
        layout.setContentsMargins(6, 5, 6, 4)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(2)

        mappings = QGroupBox("Columns")
        mappings.setMinimumWidth(315)
        mappings.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        mapping_form = QFormLayout(mappings)
        self._compact_settings_form(mapping_form)
        self.name_column = QComboBox()
        self.smiles_column = QComboBox()
        self.value_column = QComboBox()
        self.stdev_column = QComboBox()
        for widget in (self.name_column, self.smiles_column, self.stdev_column):
            widget.setMinimumWidth(185)
            widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            widget.setMinimumContentsLength(20)
        self.value_column.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.value_axis_label = QLineEdit()
        self.value_axis_label.setPlaceholderText("Value axis label")
        value_controls = QWidget()
        value_layout = QHBoxLayout(value_controls)
        value_layout.setContentsMargins(0, 0, 0, 0)
        value_layout.setSpacing(5)
        value_layout.addWidget(self.value_column, stretch=1)
        value_layout.addWidget(self.value_axis_label, stretch=1)
        mapping_form.addRow("Display name:", self.name_column)
        mapping_form.addRow("SMILES structure:", self.smiles_column)
        mapping_form.addRow("Value:", value_controls)
        mapping_form.addRow("Error bar:", self.stdev_column)

        fingerprint = QGroupBox("Morgan Fingerprint")
        fingerprint_form = QFormLayout(fingerprint)
        self._compact_settings_form(fingerprint_form)
        self.radius = QSpinBox()
        self.radius.setRange(0, 10)
        self.bits = QSpinBox()
        self.bits.setRange(128, 16384)
        self.bits.setSingleStep(128)
        self.chirality = QCheckBox()
        fingerprint_form.addRow(
            self._parameter_label(
                "Radius:",
                "How far from each atom the fingerprint describes its surroundings. Radius 0 "
                "captures atom-level features only; radius 2 (ECFP4-like) is recommended for "
                "general exploration; higher values capture larger fragments.",
            ),
            self.radius,
        )
        fingerprint_form.addRow(
            self._parameter_label(
                "Bits:",
                "Length of the fingerprint vector. More bits reduce collisions but increase "
                "memory and processing cost. 2048 is a common default.",
            ),
            self.bits,
        )
        fingerprint_form.addRow(
            self._parameter_label(
                "Include chirality:",
                "When enabled, stereochemistry is included when generating fingerprints, "
                "so stereoisomers can be distinguished.",
            ),
            self.chirality,
        )

        umap_box = QGroupBox("UMAP Reducer")
        umap_form = QFormLayout(umap_box)
        self._compact_settings_form(umap_form)
        self.neighbors = QSpinBox()
        self.neighbors.setRange(2, 1000)
        self.min_dist = QDoubleSpinBox()
        self.min_dist.setRange(0, 1)
        self.min_dist.setDecimals(4)
        self.min_dist.setSingleStep(0.01)
        self.metric_column = QComboBox()
        self.metric_column.addItems(["jaccard", "dice", "hamming", "euclidean", "cosine"])
        self.seed = QSpinBox()
        self.seed.setRange(0, 2_147_483_647)
        umap_form.addRow(
            self._parameter_label(
                "Neighbours:",
                "Number of nearby compounds used to build the local map. Smaller values "
                "emphasise local clusters; larger values preserve broader structure.",
            ),
            self.neighbors,
        )
        umap_form.addRow(
            self._parameter_label(
                "Minimum distance:",
                "Controls how tightly points may pack in the plot. Smaller values form tighter "
                "clusters; larger values create a more spread-out display.",
            ),
            self.min_dist,
        )
        umap_form.addRow(
            self._parameter_label(
                "Metric:",
                "Method for comparing fingerprints. Jaccard is appropriate for binary Morgan "
                "fingerprints and is the default for this workflow.",
            ),
            self.metric_column,
        )
        umap_form.addRow(
            self._parameter_label(
                "Random seed:",
                "Fixes UMAP's random starting state so rerunning with the same data and settings "
                "produces a reproducible layout.",
            ),
            self.seed,
        )

        buttons = QWidget()
        buttons_layout = QVBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(3)
        buttons.setFixedWidth(112)
        self.run_button = QPushButton("Run Analysis")
        self.run_button.setFixedWidth(112)
        self.run_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.run_button.setShortcut("Ctrl+R")
        self.run_button.clicked.connect(self.run_current_analysis)
        defaults = QPushButton("Defaults")
        defaults.setFixedWidth(112)
        defaults.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        defaults.clicked.connect(self.restore_defaults)
        buttons_layout.addWidget(self.run_button)
        buttons_layout.addWidget(defaults)

        excluded_preview = QWidget()
        excluded_layout = QVBoxLayout(excluded_preview)
        excluded_layout.setContentsMargins(0, 0, 0, 0)
        excluded_layout.setSpacing(0)
        excluded_header = QHBoxLayout()
        self.excluded_summary = QLabel("No analysis results.")
        font = self.excluded_summary.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)
        self.excluded_summary.setFont(font)
        self.excluded_summary.setStyleSheet("color: #c62828;")
        show_full = QPushButton("Show Full List")
        show_full.setFixedWidth(112)
        show_full.clicked.connect(self.show_excluded_rows)
        excluded_header.addWidget(self.excluded_summary)
        excluded_header.addWidget(show_full)
        excluded_header.addStretch()
        excluded_layout.addLayout(excluded_header)

        layout.addWidget(mappings, 0, 0, 1, 1)
        layout.addWidget(fingerprint, 0, 1, 1, 1)
        layout.addWidget(umap_box, 0, 2, 1, 1)
        layout.addWidget(buttons, 0, 3)
        layout.addWidget(excluded_preview, 1, 0, 1, 4)
        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(1, 2)
        layout.setColumnStretch(2, 2)
        layout.setColumnStretch(3, 1)
        self.restore_defaults()
        for combo in (self.name_column, self.smiles_column, self.value_column, self.stdev_column, self.metric_column):
            combo.currentTextChanged.connect(lambda _text: self._set_dirty())
        for combo in (self.name_column, self.smiles_column, self.value_column, self.stdev_column):
            combo.currentTextChanged.connect(self._mapping_column_changed)
        self.value_column.currentTextChanged.connect(self._value_column_changed)
        self.value_axis_label.textChanged.connect(lambda _text: self._set_dirty())
        self.value_axis_label.editingFinished.connect(self._value_label_changed)
        for spinbox in (self.radius, self.bits, self.neighbors, self.min_dist, self.seed):
            spinbox.valueChanged.connect(lambda _value: self._set_dirty())
        self.chirality.toggled.connect(lambda _checked: self._set_dirty())
        section_layout.addWidget(box)
        return section

    @staticmethod
    def _compact_settings_form(form: QFormLayout) -> None:
        form.setContentsMargins(6, 7, 6, 5)
        form.setHorizontalSpacing(6)
        form.setVerticalSpacing(2)

    @staticmethod
    def _parameter_label(text: str, tooltip: str) -> QWidget:
        label_container = QWidget()
        layout = QHBoxLayout(label_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        if text:
            layout.addWidget(QLabel(text))
        help_button = QToolButton()
        help_button.setText("?")
        help_button.setToolTip(tooltip)
        help_button.setAccessibleName(f"Help for {text.rstrip(':') or 'this parameter'}")
        help_button.setFixedSize(16, 16)
        help_button.setAutoRaise(True)
        help_button.setStyleSheet(
            "QToolButton { border: 1px solid #888; border-radius: 7px; font-weight: bold; padding: 0px; }"
        )
        layout.addWidget(help_button)
        layout.addStretch()
        return label_container

    def _create_aoi_panel(self) -> QWidget:
        panel = QGroupBox("Areas of Interest")
        panel.setMinimumWidth(210)
        layout = QHBoxLayout(panel)
        self.aoi_list = QListWidget()
        self.aoi_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.aoi_list.itemSelectionChanged.connect(self.select_areas_of_interest)
        self.aoi_list.itemClicked.connect(lambda _item: self.select_areas_of_interest())
        layout.addWidget(self.aoi_list, stretch=1)
        controls = QVBoxLayout()
        self.aoi_name = QLineEdit()
        self.aoi_name.setPlaceholderText("AOI name")
        save_aoi = QPushButton("Save AOI")
        save_aoi.clicked.connect(self.save_area_of_interest)
        delete_aoi = QPushButton("Delete AOI")
        delete_aoi.clicked.connect(self.delete_area_of_interest)
        controls.addWidget(self.aoi_name)
        controls.addWidget(save_aoi)
        controls.addWidget(delete_aoi)
        controls.addStretch()
        layout.addLayout(controls)
        return panel

    def _toggle_settings_panel(self, expanded: bool) -> None:
        self.settings_content.setVisible(expanded)
        self.settings_toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)

    def _refresh_aoi_list(self) -> None:
        selected_names = {item.text() for item in self.aoi_list.selectedItems()}
        self.aoi_list.blockSignals(True)
        self.aoi_list.clear()
        self.aoi_list.addItems(self.areas_of_interest.keys())
        for name in selected_names:
            matches = self.aoi_list.findItems(name, Qt.MatchFlag.MatchExactly)
            if matches:
                matches[0].setSelected(True)
        self.aoi_list.blockSignals(False)

    def _next_aoi_name(self) -> str:
        number = 1
        while f"AOI_{number}" in self.areas_of_interest:
            number += 1
        return f"AOI_{number}"

    def _clear_aoi_active_state(self) -> None:
        self.aoi_list.blockSignals(True)
        self.aoi_list.clearSelection()
        self.aoi_list.setCurrentItem(None)
        self.aoi_list.blockSignals(False)
        self.aoi_name.clear()

    def _sync_aoi_highlight_to_selection(self) -> None:
        if self.result is None or not self.selected_positions:
            self._clear_aoi_active_state()
            return
        selected_rows = {
            int(row) for row in self.result.embedding.iloc[self.selected_positions]["source_row"].tolist()
        }
        matching_names = [
            name
            for name, rows in self.areas_of_interest.items()
            if set(rows) == selected_rows
        ]
        self.aoi_list.blockSignals(True)
        self.aoi_list.clearSelection()
        if matching_names:
            matches = self.aoi_list.findItems(matching_names[0], Qt.MatchFlag.MatchExactly)
            if matches:
                self.aoi_list.setCurrentItem(matches[0])
                matches[0].setSelected(True)
            self.aoi_name.setText(matching_names[0])
        else:
            self.aoi_list.setCurrentItem(None)
            self.aoi_name.clear()
        self.aoi_list.blockSignals(False)

    def save_area_of_interest(self) -> None:
        if self.result is None or not self.selected_positions:
            QMessageBox.information(self, "No Selection", "Select compounds on the UMAP plot before saving an AOI.")
            return
        name = self.aoi_name.text().strip()
        if not name:
            name = self._next_aoi_name()
            self.aoi_name.setText(name)
        source_rows = [
            int(row) for row in self.result.embedding.iloc[self.selected_positions]["source_row"].tolist()
        ]
        self.areas_of_interest[name] = source_rows
        self._refresh_aoi_list()
        self.aoi_list.blockSignals(True)
        self.aoi_list.clearSelection()
        matches = self.aoi_list.findItems(name, Qt.MatchFlag.MatchExactly)
        if matches:
            self.aoi_list.setCurrentItem(matches[0])
            matches[0].setSelected(True)
        self.aoi_list.blockSignals(False)
        self._set_dirty()
        self.statusBar().showMessage(f"Saved AOI '{name}' with {len(source_rows)} compound(s).")
        self._clear_aoi_active_state()

    def select_areas_of_interest(self) -> None:
        if self.result is None:
            return
        names = [item.text() for item in self.aoi_list.selectedItems()]
        if not names:
            return
        rows = {
            row
            for name in names
            for row in self.areas_of_interest.get(name, [])
        }
        self.selected_positions = [
            position
            for position, row in enumerate(self.result.embedding["source_row"])
            if int(row) in rows
        ]
        self.aoi_name.setText(names[0] if len(names) == 1 else "")
        self._set_dirty()
        self._draw_all_results()

    def delete_area_of_interest(self) -> None:
        items = self.aoi_list.selectedItems()
        if not items:
            return
        names = [item.text() for item in items]
        for name in names:
            self.areas_of_interest.pop(name, None)
        self._refresh_aoi_list()
        self._clear_aoi_active_state()
        self._set_dirty()
        self.statusBar().showMessage(f"Deleted {len(names)} AOI(s).")

    def _new_plot_canvas(self) -> tuple[QWidget, Figure, PausableFigureCanvas, NavigationToolbar2QT]:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        figure = Figure(layout="constrained")
        canvas = PausableFigureCanvas(figure)
        toolbar = NavigationToolbar2QT(canvas, self)
        toolbar.hide()
        layout.addWidget(canvas, stretch=1)
        return container, figure, canvas, toolbar

    def _create_plot_header(
        self,
        title: str,
        edit_callback,
        popout_callback,
        toolbar: NavigationToolbar2QT,
    ) -> QWidget:  # type: ignore[no-untyped-def]
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(3, 0, 3, 0)
        layout.setSpacing(3)
        edit_title = QPushButton(title)
        edit_title.setToolTip("Click to edit plot appearance")
        edit_title.setStyleSheet(
            "QPushButton { padding: 2px 8px; font-weight: bold; border: 1px solid palette(mid); "
            "border-radius: 4px; background: palette(button); }"
            "QPushButton:hover { background: palette(highlight); color: palette(highlighted-text); }"
        )
        edit_title.clicked.connect(edit_callback)
        layout.addWidget(edit_title)
        layout.addStretch()
        popout = QToolButton()
        popout.setText("Open")
        popout.setToolTip("Open this figure in a new window")
        popout.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        popout.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        popout.setIconSize(QSize(14, 14))
        popout.setAutoRaise(True)
        popout.clicked.connect(popout_callback)
        layout.addWidget(popout)

        actions = {action.text().replace("&", ""): action for action in toolbar.actions()}
        for label in ("Home", "Back", "Forward", "Pan", "Zoom", "Save"):
            action = actions.get(label)
            if label == "Save":
                action = action or actions.get("Save the figure")
            if action is None:
                continue
            button = QToolButton()
            button.setDefaultAction(action)
            button.setIconSize(QSize(14, 14))
            button.setFixedSize(22, 22)
            layout.addWidget(button)
        return header

    def _create_umap_panel(self) -> QWidget:
        panel = QGroupBox()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 4, 6, 6)
        child, self.umap_figure, self.umap_canvas, self.umap_toolbar = self._new_plot_canvas()
        layout.addWidget(
            self._create_plot_header("UMAP Chemical Space", self.edit_umap_style, self.open_umap_window, self.umap_toolbar)
        )
        self.umap_canvas.mpl_connect("button_press_event", self._umap_clicked)
        layout.addWidget(child)
        self._show_empty_plot(self.umap_figure, self.umap_canvas, "Run analysis to display UMAP")
        return panel

    def _create_bar_panel(self) -> QWidget:
        panel = QGroupBox()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 4, 6, 6)
        child, self.bar_figure, self.bar_canvas, self.bar_toolbar = self._new_plot_canvas()
        layout.addWidget(
            self._create_plot_header(
                "Selected Compound Values", self.edit_bar_style, self.open_bar_window, self.bar_toolbar
            )
        )
        layout.addWidget(child)
        self._show_empty_plot(self.bar_figure, self.bar_canvas, "Select compounds on the UMAP plot")
        return panel

    def _create_structure_panel(self) -> QWidget:
        panel = QGroupBox()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 4, 6, 6)
        header = QHBoxLayout()
        title = QLabel("Selected Chemical Structures")
        save_structures = QToolButton()
        save_structures.setText("Save")
        save_structures.setToolTip("Save selected chemical structures")
        save_structures.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        save_structures.clicked.connect(self.save_structure_grid)
        open_structures = QToolButton()
        open_structures.setText("Open")
        open_structures.setToolTip("Open structures in a new window")
        open_structures.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        open_structures.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        open_structures.setAutoRaise(True)
        open_structures.clicked.connect(self.open_structure_window)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(open_structures)
        header.addWidget(save_structures)
        layout.addLayout(header)
        self.structure_message = QLabel("Select compounds on the UMAP plot to display structures.")
        layout.addWidget(self.structure_message)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.structure_scroll = scroll
        scroll.viewport().installEventFilter(self)
        self.structure_image = QLabel()
        self.structure_image.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.structure_image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.structure_image.setStyleSheet("background: white;")
        scroll.setWidget(self.structure_image)
        layout.addWidget(scroll, stretch=1)
        return panel

    @staticmethod
    def _show_empty_plot(figure: Figure, canvas: FigureCanvasQTAgg, message: str) -> None:
        figure.clear()
        axis = figure.add_subplot(111)
        axis.text(0.5, 0.5, message, horizontalalignment="center", verticalalignment="center")
        axis.set_axis_off()
        canvas.draw_idle()

    def restore_defaults(self) -> None:
        defaults = AnalysisSettings()
        self.radius.setValue(defaults.fingerprint_radius)
        self.bits.setValue(defaults.fingerprint_bits)
        self.chirality.setChecked(defaults.include_chirality)
        self.neighbors.setValue(defaults.n_neighbors)
        self.min_dist.setValue(defaults.min_dist)
        self.metric_column.setCurrentText(defaults.metric)
        self.seed.setValue(defaults.random_seed)

    def edit_umap_style(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("UMAP Plot Appearance")
        form = QFormLayout(dialog)
        title = QLineEdit(self.umap_style.title)
        color_scale = QComboBox()
        reversed_scale = self.umap_style.color.endswith("_r")
        selected_scale = self.umap_style.color[:-2] if reversed_scale else self.umap_style.color
        color_scales = ["RdYlGn", "viridis", "plasma", "coolwarm", "Blues", "Reds", "Greys"]
        if selected_scale not in color_scales:
            color_scales.append(selected_scale)
        color_scale.addItems(color_scales)
        color_scale.setCurrentText(selected_scale)
        reverse_color_scale = QCheckBox("Reverse colour scale")
        reverse_color_scale.setChecked(reversed_scale)
        dot_size = QSpinBox()
        dot_size.setRange(5, 200)
        dot_size.setValue(self.umap_style.marker_size)
        opacity = QDoubleSpinBox()
        opacity.setRange(0.05, 1.0)
        opacity.setSingleStep(0.05)
        opacity.setDecimals(2)
        opacity.setValue(self.umap_style.opacity)
        show_outline = QCheckBox("Show dot outline")
        show_outline.setChecked(self.umap_style.show_outline)
        edge_button = QPushButton("Choose Colour...")
        selected_edge = QColor(self.umap_style.edge_color)

        def choose_edge_color() -> None:
            nonlocal selected_edge
            chosen = QColorDialog.getColor(selected_edge, dialog, "Select Dot Outline Colour")
            if chosen.isValid():
                selected_edge = chosen
                edge_button.setStyleSheet(f"background-color: {chosen.name()};")

        edge_button.setStyleSheet(f"background-color: {selected_edge.name()};")
        edge_button.clicked.connect(choose_edge_color)
        form.addRow("Plot title:", title)
        form.addRow("Dot colour scale:", color_scale)
        form.addRow("", reverse_color_scale)
        form.addRow("Dot size:", dot_size)
        form.addRow("Dot opacity:", opacity)
        form.addRow("", show_outline)
        form.addRow("Dot outline colour:", edge_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.umap_style.title = title.text().strip() or "Chemical Space UMAP"
            self.umap_style.color = color_scale.currentText() + ("_r" if reverse_color_scale.isChecked() else "")
            self.umap_style.marker_size = dot_size.value()
            self.umap_style.edge_color = selected_edge.name()
            self.umap_style.opacity = opacity.value()
            self.umap_style.show_outline = show_outline.isChecked()
            self._set_dirty()
            if self.result is not None:
                self._draw_umap()

    def edit_bar_style(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Bar Plot Appearance")
        form = QFormLayout(dialog)
        title = QLineEdit(self.bar_style.title)
        lower_limit = QLineEdit("" if self.bar_style.y_min is None else str(self.bar_style.y_min))
        lower_limit.setPlaceholderText("Auto")
        upper_limit = QLineEdit("" if self.bar_style.y_max is None else str(self.bar_style.y_max))
        upper_limit.setPlaceholderText("Auto")
        color_button = QPushButton("Choose Colour...")
        selected_color = QColor(self.bar_style.color)

        def choose_color() -> None:
            nonlocal selected_color
            chosen = QColorDialog.getColor(selected_color, dialog, "Select Bar Colour")
            if chosen.isValid():
                selected_color = chosen
                color_button.setStyleSheet(f"background-color: {chosen.name()};")

        color_button.setStyleSheet(f"background-color: {selected_color.name()};")
        color_button.clicked.connect(choose_color)
        form.addRow("Plot title:", title)
        form.addRow("Bar colour:", color_button)
        form.addRow("Upper Y limit:", upper_limit)
        form.addRow("Lower Y limit:", lower_limit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                y_min = float(lower_limit.text()) if lower_limit.text().strip() else None
                y_max = float(upper_limit.text()) if upper_limit.text().strip() else None
            except ValueError:
                QMessageBox.warning(self, "Invalid Y-axis Limit", "Y-axis limits must be numbers or left blank for Auto.")
                return
            if y_min is not None and y_max is not None and y_min >= y_max:
                QMessageBox.warning(self, "Invalid Y-axis Limit", "Lower Y limit must be smaller than upper Y limit.")
                return
            self.bar_style.title = title.text().strip() or "Selected Compounds"
            self.bar_style.color = selected_color.name()
            self.bar_style.y_min = y_min
            self.bar_style.y_max = y_max
            self._set_dirty()
            if self.result is not None and self.selected_positions:
                self._draw_selected()
                self._refresh_popouts()

    def open_file(self) -> None:
        if self._analysis_is_running():
            QMessageBox.information(self, "Analysis Running", "Wait for the current analysis to finish before opening data.")
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open Chemical Dataset or Project",
            "",
            "Supported Files (*.csv *.xls *.xlsx *.scom);;Project Files (*.scom);;"
            "Data Tables (*.csv *.xls *.xlsx)",
        )
        if not filename:
            return
        if not self._confirm_save_changes():
            return
        try:
            if Path(filename).suffix.lower() == PROJECT_SUFFIX:
                self._open_saved_project(Path(filename))
            else:
                self._open_table(Path(filename))
        except Exception as error:
            QMessageBox.critical(self, "Open Failed", str(error))

    def _open_table(self, path: Path) -> None:
        self._loading_state = True
        sheet_name = None
        try:
            if path.suffix.lower() in {".xls", ".xlsx"}:
                sheets = excel_sheet_names(path)
                sheet_name, accepted = QInputDialog.getItem(
                    self, "Select Working Sheet", "Worksheet containing the processed table:", sheets, 0, False
                )
                if not accepted:
                    return
            self.data = load_table(path, sheet_name)
            self.source_filename = path.name
            self.source_bytes = path.read_bytes()
            self._structure_render_cache.clear()
            self.project_path = None
            self.result = None
            self.selected_positions = []
            self.areas_of_interest = {}
            self._refresh_aoi_list()
            self._populate_columns()
            source = f"{path.name}" + (f" [{sheet_name}]" if sheet_name else "")
            self.data_summary.setText(f"{source}  |  {len(self.data):,} rows, {len(self.data.columns)} columns")
            self._clear_results()
            self.statusBar().showMessage(f"Loaded {source}. Map columns and run analysis to display figures.")
        finally:
            self._loading_state = False
        if self.data is not None:
            self._set_dirty()

    def _open_saved_project(self, path: Path) -> None:
        self._loading_state = True
        try:
            saved = load_project(path)
            self.data = saved.data
            self.source_filename = saved.source_filename
            self.source_bytes = saved.source_bytes
            self._structure_render_cache.clear()
            self.project_path = path
            self.areas_of_interest = saved.areas_of_interest
            self._refresh_aoi_list()
            self._populate_columns(saved.mapping)
            self._apply_settings(saved.settings)
            if "umap" in saved.plot_styles:
                self.umap_style = PlotStyle(**saved.plot_styles["umap"])
            if "bar" in saved.plot_styles:
                self.bar_style = PlotStyle(**saved.plot_styles["bar"])
            if saved.embedding is not None:
                report_columns = ["source_row", "display_name", "smiles", "reason"]
                excluded = (
                    saved.excluded if saved.excluded is not None else pd.DataFrame(columns=report_columns)
                )
                warnings = (
                    saved.warnings if saved.warnings is not None else pd.DataFrame(columns=report_columns)
                )
                self.result = AnalysisResult(saved.embedding, excluded, saved.settings, saved.mapping, warnings)
                source_rows = set(saved.selected_rows)
                self.selected_positions = [
                    position
                    for position, row in enumerate(self.result.embedding["source_row"])
                    if int(row) in source_rows
                ]
                self._draw_all_results()
                self._update_excluded_preview()
            else:
                self.result = None
                self._clear_results()
            self.data_summary.setText(f"{path.name}  |  {len(self.data):,} rows, saved project")
            self.statusBar().showMessage(f"Opened project {path.name}.")
        finally:
            self._loading_state = False
        self._set_clean()

    def _populate_columns(self, mapping: ColumnMapping | None = None) -> None:
        assert self.data is not None
        columns = [str(column) for column in self.data.columns]
        for widget in (self.name_column, self.smiles_column, self.value_column):
            widget.clear()
            widget.addItems(columns)
        self.stdev_column.clear()
        self.stdev_column.addItem("None (no error bars)")
        self.stdev_column.addItems(columns)

        if mapping:
            choices = [mapping.display_name, mapping.smiles, mapping.value]
        else:
            choices = [
                self._guess_column(columns, ["sample number", "name", "compound", "id"]),
                self._guess_column(columns, ["smiles", "smile"]),
                self._guess_column(columns, ["average", "value", "activity", "inhibition"]),
            ]
        for widget, column in zip((self.name_column, self.smiles_column, self.value_column), choices):
            if column in columns:
                widget.setCurrentText(column)
        error_column = (
            mapping.stdev
            if mapping
            else self._guess_optional_column(columns, ["stdev", "std", "sd", "standard deviation"])
        )
        self.stdev_column.setCurrentText(error_column if error_column in columns else "None (no error bars)")
        self.value_axis_label.setText(
            mapping.display_value_label() if mapping else self.value_column.currentText()
        )

    @staticmethod
    def _guess_column(columns: list[str], candidates: list[str]) -> str:
        lowered = {column.lower().strip(): column for column in columns}
        for candidate in candidates:
            if candidate in lowered:
                return lowered[candidate]
        for candidate in candidates:
            for column in columns:
                if candidate in column.lower():
                    return column
        return columns[0] if columns else ""

    @staticmethod
    def _guess_optional_column(columns: list[str], candidates: list[str]) -> str | None:
        lowered = {column.lower().strip(): column for column in columns}
        for candidate in candidates:
            if candidate in lowered:
                return lowered[candidate]
        for candidate in candidates:
            for column in columns:
                if candidate in column.lower():
                    return column
        return None

    def _value_column_changed(self, column: str) -> None:
        self.value_axis_label.setText(column)
        self._redraw_value_label_changes()

    def _mapping_column_changed(self, _column: str) -> None:
        if self._loading_state or self.result is None:
            return
        self.result = None
        self.selected_positions = []
        self._structure_render_cache.clear()
        self._clear_aoi_active_state()
        self._clear_results()
        self.statusBar().showMessage("Column mapping changed. Run Analysis to display updated figures.")

    def _value_label_changed(self) -> None:
        if not self.value_axis_label.text().strip():
            self.value_axis_label.setText(self.value_column.currentText())
        self._redraw_value_label_changes()

    def _redraw_value_label_changes(self) -> None:
        if not self._loading_state and self.result is not None:
            self._draw_all_results()

    def _value_axis_label(self) -> str:
        return self.value_axis_label.text().strip() or self.value_column.currentText() or "Value"

    def _current_mapping(self) -> ColumnMapping:
        return ColumnMapping(
            display_name=self.name_column.currentText(),
            smiles=self.smiles_column.currentText(),
            value=self.value_column.currentText(),
            stdev=None if self.stdev_column.currentIndex() == 0 else self.stdev_column.currentText(),
            value_label=self._value_axis_label(),
        )

    def _current_settings(self) -> AnalysisSettings:
        return AnalysisSettings(
            fingerprint_radius=self.radius.value(),
            fingerprint_bits=self.bits.value(),
            include_chirality=self.chirality.isChecked(),
            n_neighbors=self.neighbors.value(),
            min_dist=self.min_dist.value(),
            metric=self.metric_column.currentText(),
            random_seed=self.seed.value(),
        )

    def _apply_settings(self, settings: AnalysisSettings) -> None:
        self.radius.setValue(settings.fingerprint_radius)
        self.bits.setValue(settings.fingerprint_bits)
        self.chirality.setChecked(settings.include_chirality)
        self.neighbors.setValue(settings.n_neighbors)
        self.min_dist.setValue(settings.min_dist)
        self.metric_column.setCurrentText(settings.metric)
        self.seed.setValue(settings.random_seed)

    def run_current_analysis(self) -> None:
        if self.data is None:
            QMessageBox.information(self, "No Data", "Open a data table before running analysis.")
            return
        if self._analysis_is_running():
            return
        self.statusBar().clearMessage()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Starting... 0%")
        self.progress_bar.show()
        self.run_button.setEnabled(False)
        self._analysis_thread = QThread(self)
        self._analysis_worker = AnalysisWorker(
            self.data.copy(),
            self._current_mapping(),
            self._current_settings(),
        )
        self._analysis_worker.moveToThread(self._analysis_thread)
        self._analysis_thread.started.connect(self._analysis_worker.run)
        self._analysis_worker.progress_changed.connect(self._analysis_progress)
        self._analysis_worker.completed.connect(self._analysis_completed)
        self._analysis_worker.failed.connect(self._analysis_failed)
        self._analysis_worker.completed.connect(self._analysis_worker.deleteLater)
        self._analysis_worker.failed.connect(self._analysis_worker.deleteLater)
        self._analysis_worker.completed.connect(self._analysis_thread.quit)
        self._analysis_worker.failed.connect(self._analysis_thread.quit)
        self._analysis_thread.finished.connect(self._analysis_finished)
        self._analysis_thread.finished.connect(self._analysis_thread.deleteLater)
        self._analysis_thread.start()

    @Slot(int, str)
    def _analysis_progress(self, value: int, message: str) -> None:
        self.progress_bar.setValue(value)
        short_message = message.split(":", maxsplit=1)[0]
        self.progress_bar.setFormat(f"{value}% - {short_message}")

    @Slot(object)
    def _analysis_completed(self, result: AnalysisResult) -> None:
        self.result = result
        self._structure_render_cache.clear()
        self.selected_positions = []
        self._set_dirty()
        self._draw_all_results()
        self._update_excluded_preview()
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("100%")
        excluded = len(self.result.excluded)
        message = f"Analysis complete: {len(self.result.embedding)} compounds mapped"
        if excluded:
            message += f"; {excluded} excluded (use Show Full List in settings)"
        if len(self.result.warnings):
            message += f"; {len(self.result.warnings)} warning(s)"
        self.statusBar().showMessage(message)

    @Slot(str)
    def _analysis_failed(self, error: str) -> None:
        QMessageBox.critical(self, "Analysis Failed", error)
        self.statusBar().showMessage("Analysis failed.")

    @Slot()
    def _analysis_finished(self) -> None:
        self.run_button.setEnabled(True)
        self.progress_bar.hide()
        self._analysis_worker = None
        self._analysis_thread = None

    def _analysis_is_running(self) -> bool:
        return self._analysis_thread is not None and self._analysis_thread.isRunning()

    def _begin_visual_resize_pause(self) -> None:
        if not hasattr(self, "umap_canvas"):
            return
        self.umap_canvas.resize_redraw_paused = True
        self.bar_canvas.resize_redraw_paused = True
        if hasattr(self, "structure_scroll"):
            self.structure_scroll.viewport().setUpdatesEnabled(False)
        self._structure_resize_timer.stop()
        self._visual_resize_timer.start()

    def _finish_visual_resize_pause(self) -> None:
        if not hasattr(self, "umap_canvas"):
            return
        self.umap_canvas.finish_resize_pause()
        self.bar_canvas.finish_resize_pause()
        if hasattr(self, "structure_scroll"):
            self.structure_scroll.viewport().setUpdatesEnabled(True)
            self.structure_scroll.viewport().update()
        self._redraw_main_structure_after_resize()

    def _draw_all_results(self) -> None:
        self._draw_umap()
        self._draw_selected()
        self._refresh_popouts()

    def _plot_umap_on_axis(self, figure: Figure) -> None:
        assert self.result is not None
        frame = self.result.embedding
        axis = figure.add_subplot(111)
        if self.selected_positions:
            selected = frame.iloc[self.selected_positions]
            axis.scatter(
                selected["UMAP 1"],
                selected["UMAP 2"],
                s=self.umap_style.marker_size * 2.2,
                facecolors="none",
                edgecolors="#1557c0",
                linewidths=3.6,
                alpha=0.8,
                zorder=1,
            )
        points = axis.scatter(
            frame["UMAP 1"],
            frame["UMAP 2"],
            c=frame["value"],
            cmap=self.umap_style.color,
            s=self.umap_style.marker_size,
            alpha=self.umap_style.opacity,
            edgecolors=self.umap_style.edge_color if self.umap_style.show_outline else "none",
            linewidths=0.35 if self.umap_style.show_outline else 0,
            rasterized=len(frame) > 2000,
            zorder=2,
        )
        figure.colorbar(points, ax=axis, label=self._value_axis_label())
        axis.set_title(self.umap_style.title)
        axis.set_xlabel("UMAP 1")
        axis.set_ylabel("UMAP 2")

    def _draw_umap(self) -> None:
        assert self.result is not None
        if self._lasso is not None:
            self._lasso.disconnect_events()
        self.umap_figure.clear()
        self._plot_umap_on_axis(self.umap_figure)
        axis = self.umap_figure.axes[0]
        self._lasso = LassoSelector(axis, onselect=self._lasso_selected)
        self.umap_canvas.draw_idle()

    def clear_selection(self) -> None:
        if self.result is None:
            return
        self.selected_positions = []
        self._clear_aoi_active_state()
        self._set_dirty()
        self._draw_all_results()

    def _umap_clicked(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.dblclick:
            self.clear_selection()

    def _lasso_selected(self, vertices: list[tuple[float, float]]) -> None:
        if self.result is None:
            return
        coordinates = self.result.embedding[["UMAP 1", "UMAP 2"]].to_numpy()
        selected = MplPath(vertices).contains_points(coordinates)
        self.selected_positions = list(np.nonzero(selected)[0])
        self._sync_aoi_highlight_to_selection()
        self._set_dirty()
        self._draw_all_results()

    def _popout_lasso_selected(self, vertices: list[tuple[float, float]], canvas: FigureCanvasQTAgg) -> None:
        self._lasso_selected(vertices)
        canvas.draw_idle()

    def _draw_selected(self) -> None:
        if self.result is None or not self.selected_positions:
            self._show_empty_plot(self.bar_figure, self.bar_canvas, "Select compounds on the UMAP plot")
            self.structure_message.setText("Select compounds on the UMAP plot to display structures.")
            self.structure_image.clear()
            self._structure_columns = None
            self._structure_svg = None
            return

        selected = self.result.embedding.iloc[self.selected_positions].sort_values("value", ascending=False)
        self.bar_figure.clear()
        self._plot_bar_on_axis(self.bar_figure, selected)
        self.bar_canvas.draw_idle()

        self._draw_structure_grid(selected)

    def _selected_frame(self) -> pd.DataFrame | None:
        if self.result is None or not self.selected_positions:
            return None
        return self.result.embedding.iloc[self.selected_positions].sort_values("value", ascending=False)

    def _plot_bar_on_axis(self, figure: Figure, selected: pd.DataFrame) -> None:
        axis = figure.add_subplot(111)
        bar_options: dict[str, object] = {}
        if selected["stdev"].notna().any():
            bar_options["yerr"] = selected["stdev"].fillna(0)
            bar_options["capsize"] = 3
        axis.bar(
            selected["display_name"],
            selected["value"],
            color=self.bar_style.color,
            edgecolor="black",
            linewidth=0.4,
            **bar_options,
        )
        axis.set_title(f"{self.bar_style.title} (n={len(selected)})")
        axis.set_ylabel(self._value_axis_label())
        if self.bar_style.y_min is not None or self.bar_style.y_max is not None:
            axis.set_ylim(bottom=self.bar_style.y_min, top=self.bar_style.y_max)
        axis.tick_params(axis="x", rotation=70, labelsize=8)
        axis.grid(axis="y", alpha=0.2)

    def _draw_structure_grid(self, selected: pd.DataFrame) -> None:
        visible = selected.head(40)
        viewport_width = self.structure_scroll.viewport().width()
        columns = min(len(visible), max(1, viewport_width // 240))
        self._structure_columns = columns
        svg, pixmap = self._render_structure_pixmap(selected, columns, self._value_axis_label())
        self._structure_svg = svg
        self.structure_image.setPixmap(pixmap)
        note = f"Showing {len(visible)} selected structure(s)."
        if len(selected) > len(visible):
            note += " Display limited to the first 40 sorted compounds."
        self.structure_message.setText(note)

    def _render_structure_pixmap(self, selected: pd.DataFrame, columns: int, value_label: str) -> tuple[str, QPixmap]:
        visible = selected.head(40)
        key = (
            columns,
            value_label,
            tuple(visible["smiles"].astype(str)),
            tuple(visible["display_name"].astype(str)),
            tuple(visible["value"].astype(float)),
        )
        cached = self._structure_render_cache.get(key)
        if cached is not None:
            return cached
        mols = []
        for smiles in visible["smiles"].astype(str):
            if smiles not in self._molecule_cache:
                self._molecule_cache[smiles] = Chem.MolFromSmiles(smiles)
            mols.append(self._molecule_cache[smiles])
        legends = [
            f"{name}\n{value_label}: {value:.2f}"
            for name, value in zip(visible["display_name"], visible["value"])
        ]
        svg = Draw.MolsToGridImage(
            mols,
            legends=legends,
            molsPerRow=columns,
            subImgSize=(240, 190),
            useSVG=True,
        )
        svg = svg.replace("encoding='iso-8859-1'", "encoding='utf-8'")
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pixmap = QPixmap(renderer.defaultSize())
        pixmap.fill(Qt.GlobalColor.white)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        if len(self._structure_render_cache) >= 12:
            self._structure_render_cache.pop(next(iter(self._structure_render_cache)))
        self._structure_render_cache[key] = (svg, pixmap)
        return svg, pixmap

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if (
            hasattr(self, "structure_scroll")
            and watched is self.structure_scroll.viewport()
            and event.type() == QEvent.Type.Resize
            and self.result is not None
            and self.selected_positions
        ):
            columns = min(40, len(self.selected_positions), max(1, event.size().width() // 240))
            if columns != self._structure_columns:
                self._structure_resize_timer.start()
        return super().eventFilter(watched, event)

    def _redraw_main_structure_after_resize(self) -> None:
        selected = self._selected_frame()
        if selected is not None and not selected.empty:
            self._draw_structure_grid(selected)

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._begin_visual_resize_pause()
        super().resizeEvent(event)

    def _clear_results(self) -> None:
        if self._lasso is not None:
            self._lasso.disconnect_events()
            self._lasso = None
        self._show_empty_plot(self.umap_figure, self.umap_canvas, "Run analysis to display UMAP")
        self._show_empty_plot(self.bar_figure, self.bar_canvas, "Select compounds on the UMAP plot")
        self.structure_image.clear()
        self._structure_columns = None
        self._structure_svg = None
        self.structure_message.setText("Select compounds on the UMAP plot to display structures.")
        self._update_excluded_preview()
        self._refresh_popouts()

    def save_structure_grid(self) -> None:
        if self._structure_svg is None or self.structure_image.pixmap() is None:
            QMessageBox.information(self, "No Structures", "Select compounds before saving a structure image.")
            return
        self._save_structure_image(self._structure_svg, self.structure_image.pixmap())

    def _save_structure_image(self, svg: str, pixmap: QPixmap) -> None:
        filename, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Selected Chemical Structures",
            "",
            "SVG Image (*.svg);;PNG Image (*.png)",
        )
        if not filename:
            return
        path = Path(filename)
        if "PNG" in selected_filter:
            if path.suffix.lower() != ".png":
                path = path.with_suffix(".png")
            if not pixmap.save(str(path), "PNG"):
                QMessageBox.critical(self, "Save Failed", "Could not save the PNG structure image.")
                return
        else:
            if path.suffix.lower() != ".svg":
                path = path.with_suffix(".svg")
            path.write_text(svg, encoding="utf-8")
        self.statusBar().showMessage(f"Saved chemical structures to {path.name}.")

    def _show_popout(self, window: PopoutWindow) -> None:
        self._popout_windows.append(window)
        window.destroyed.connect(lambda: self._popout_windows.remove(window) if window in self._popout_windows else None)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.setWindowIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView))
        window.show()

    def _popout_title(self, view_name: str) -> str:
        source = self.project_path.name if self.project_path is not None else self.source_filename
        return f"{source or 'Untitled'} - {view_name}"

    def open_umap_window(self) -> None:
        if self.result is None:
            QMessageBox.information(self, "No Figure", "Run analysis before opening the UMAP figure.")
            return
        window = PopoutWindow(self._popout_title("UMAP"), self)
        window.view_kind = "umap"
        figure = Figure(layout="constrained")
        canvas = FigureCanvasQTAgg(figure)
        window.figure = figure
        window.canvas = canvas
        toolbar = NavigationToolbar2QT(canvas, window)
        self._plot_umap_on_axis(figure)
        axis = figure.axes[0]
        window.lasso_selector = LassoSelector(  # type: ignore[attr-defined]
            axis, onselect=lambda vertices: self._popout_lasso_selected(vertices, canvas)
        )
        window.content_layout.addWidget(toolbar)
        window.content_layout.addWidget(canvas, stretch=1)
        canvas.draw_idle()
        self._show_popout(window)

    def open_bar_window(self) -> None:
        window = PopoutWindow(self._popout_title("Barchart"), self)
        window.view_kind = "bar"
        figure = Figure(layout="constrained")
        canvas = FigureCanvasQTAgg(figure)
        window.figure = figure
        window.canvas = canvas
        toolbar = NavigationToolbar2QT(canvas, window)
        if self.result is None or not self.selected_positions:
            self._show_empty_plot(figure, canvas, "Select compounds on the UMAP plot")
        else:
            selected = self.result.embedding.iloc[self.selected_positions].sort_values("value", ascending=False)
            self._plot_bar_on_axis(figure, selected)
        window.content_layout.addWidget(toolbar)
        window.content_layout.addWidget(canvas, stretch=1)
        canvas.draw_idle()
        self._show_popout(window)

    def open_structure_window(self) -> None:
        if self.structure_image.pixmap() is None:
            QMessageBox.information(self, "No Structures", "Select compounds before opening the structure view.")
            return
        window = StructurePopoutWindow(self._popout_title("Selected Chemical Structures"), self)
        window.refresh()
        self._show_popout(window)

    def _refresh_popouts(self) -> None:
        for window in list(self._popout_windows):
            if window.view_kind == "umap" and window.figure is not None and window.canvas is not None:
                if self.result is None:
                    self._show_empty_plot(window.figure, window.canvas, "Run analysis to display UMAP")
                else:
                    window.figure.clear()
                    self._plot_umap_on_axis(window.figure)
                    window.lasso_selector = LassoSelector(  # type: ignore[attr-defined]
                        window.figure.axes[0],
                        onselect=lambda vertices, canvas=window.canvas: self._popout_lasso_selected(vertices, canvas),
                    )
                    window.canvas.draw_idle()
            elif window.view_kind == "bar" and window.figure is not None and window.canvas is not None:
                if self.result is None or not self.selected_positions:
                    self._show_empty_plot(window.figure, window.canvas, "Select compounds on the UMAP plot")
                else:
                    selected = self.result.embedding.iloc[self.selected_positions].sort_values("value", ascending=False)
                    window.figure.clear()
                    self._plot_bar_on_axis(window.figure, selected)
                    window.canvas.draw_idle()
            elif isinstance(window, StructurePopoutWindow):
                window.columns = None
                window.refresh()

    def export_areas_of_interest(self) -> None:
        if self.result is None:
            QMessageBox.information(self, "No Analysis", "Run analysis before exporting Areas of Interest.")
            return
        if not self.areas_of_interest:
            QMessageBox.information(self, "No AOIs", "No Areas of Interest have been saved.")
            return
        exported: list[pd.DataFrame] = []
        for name, source_rows in self.areas_of_interest.items():
            rows = self.result.embedding[self.result.embedding["source_row"].isin(source_rows)].copy()
            if rows.empty:
                continue
            rows.insert(0, "AOI", name)
            exported.append(rows)
        if not exported:
            QMessageBox.information(self, "No AOI Rows", "Saved AOIs do not match the current analysis results.")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Areas of Interest",
            "areas_of_interest.csv",
            "CSV File (*.csv)",
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != ".csv":
            path = path.with_suffix(".csv")
        pd.concat(exported, ignore_index=True).to_csv(path, index=False)
        self.statusBar().showMessage(f"Exported Areas of Interest to {path.name}.")

    def export_figures_pdf(self) -> None:
        if self.result is None:
            QMessageBox.information(self, "No Figures", "Run analysis before exporting figures.")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Figures as PDF",
            "sweet_chem_figures.pdf",
            "PDF File (*.pdf)",
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")
        selected = self._selected_frame()
        try:
            with PdfPages(path) as pdf:
                umap_figure = Figure(figsize=(11, 8.5), layout="constrained")
                self._plot_umap_on_axis(umap_figure)
                umap_figure.savefig(pdf, format="pdf")

                bar_figure = Figure(figsize=(11, 8.5), layout="constrained")
                if selected is None or selected.empty:
                    axis = bar_figure.add_subplot(111)
                    axis.text(0.5, 0.5, "No compounds selected", ha="center", va="center")
                    axis.set_axis_off()
                else:
                    self._plot_bar_on_axis(bar_figure, selected)
                bar_figure.savefig(pdf, format="pdf")

                structure_figure = Figure(figsize=(11, 8.5), layout="constrained")
                axis = structure_figure.add_subplot(111)
                if selected is None or selected.empty:
                    axis.text(0.5, 0.5, "No compounds selected", ha="center", va="center")
                else:
                    columns = min(len(selected.head(40)), 4)
                    _, pixmap = self._render_structure_pixmap(selected, columns, self._value_axis_label())
                    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
                    pixels = np.frombuffer(image.bits(), dtype=np.uint8, count=image.sizeInBytes())
                    pixels = pixels.reshape((image.height(), image.width(), 4))
                    axis.imshow(pixels)
                axis.set_axis_off()
                axis.set_title("Selected Chemical Structures")
                structure_figure.savefig(pdf, format="pdf")
        except Exception as error:
            QMessageBox.critical(self, "Export Failed", str(error))
            return
        self.statusBar().showMessage(f"Exported three figure pages to {path.name}.")

    def save_current_project(self) -> bool:
        if self._analysis_is_running():
            QMessageBox.information(self, "Analysis Running", "Wait for the current analysis to finish before saving.")
            return False
        if self.project_path is None:
            return self.save_project_as()
        return self._write_project(self.project_path)

    def save_project_as(self) -> bool:
        if self._analysis_is_running():
            QMessageBox.information(self, "Analysis Running", "Wait for the current analysis to finish before saving.")
            return False
        if self.data is None:
            QMessageBox.information(self, "No Data", "Open a data table before saving a project.")
            return False
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Sweet Chem O Mine", "", "Sweet Chem O Mine (*.scom)"
        )
        if not filename:
            return False
        path = Path(filename)
        if path.suffix.lower() != PROJECT_SUFFIX:
            path = path.with_suffix(PROJECT_SUFFIX)
        return self._write_project(path)

    def _write_project(self, path: Path) -> bool:
        assert self.data is not None
        selected_rows: list[int] = []
        if self.result is not None and self.selected_positions:
            selected_rows = [
                int(row) for row in self.result.embedding.iloc[self.selected_positions]["source_row"].tolist()
            ]
        try:
            save_project(
                path,
                self.data,
                self._current_mapping(),
                self._current_settings(),
                self.result,
                selected_rows,
                self.source_filename,
                self.source_bytes,
                {"umap": asdict(self.umap_style), "bar": asdict(self.bar_style)},
                self.areas_of_interest,
            )
        except Exception as error:
            QMessageBox.critical(self, "Save Failed", str(error))
            return False
        self.project_path = path
        self._set_clean()
        self.statusBar().showMessage(f"Saved project to {path.name}.")
        return True

    @staticmethod
    def _fill_table(table: QTableWidget, frame: pd.DataFrame) -> None:
        table.clear()
        table.setRowCount(len(frame))
        table.setColumnCount(len(frame.columns))
        table.setHorizontalHeaderLabels([str(column) for column in frame.columns])
        for row_number, (_, row) in enumerate(frame.iterrows()):
            for column_number, value in enumerate(row):
                table.setItem(row_number, column_number, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()

    def _update_excluded_preview(self) -> None:
        if not hasattr(self, "excluded_summary"):
            return
        if self.result is None:
            self.excluded_summary.setText("No analysis results.")
            self.excluded_summary.setStyleSheet("color: #666666;")
            return
        excluded_count = len(self.result.excluded)
        warning_count = len(self.result.warnings)
        if not excluded_count and not warning_count:
            self.excluded_summary.setText("No data issues found.")
            self.excluded_summary.setStyleSheet("color: #2e7d32;")
            return
        parts = []
        if excluded_count:
            parts.append(f"{excluded_count} row(s) excluded")
        if warning_count:
            parts.append(f"{warning_count} warning(s)")
        self.excluded_summary.setText("; ".join(parts) + ".")
        self.excluded_summary.setStyleSheet("color: #c62828;" if excluded_count else "color: #d97706;")

    def _data_issue_report(self) -> pd.DataFrame:
        assert self.result is not None
        frames: list[pd.DataFrame] = []
        if not self.result.excluded.empty:
            excluded = self.result.excluded.copy()
            excluded.insert(0, "status", "Excluded")
            frames.append(excluded)
        if not self.result.warnings.empty:
            warnings = self.result.warnings.copy()
            warnings.insert(0, "status", "Warning")
            frames.append(warnings)
        if not frames:
            return pd.DataFrame(columns=["status", "source_row", "display_name", "smiles", "reason"])
        return pd.concat(frames, ignore_index=True)

    def show_excluded_rows(self) -> None:
        if self.result is None or self._data_issue_report().empty:
            QMessageBox.information(self, "Data Issues", "No excluded rows or warnings are present in the current analysis.")
            return
        report = self._data_issue_report()
        table = QTableWidget()
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        self._fill_table(table, report)
        window = QWidget(self, Qt.WindowType.Dialog)
        window.setWindowTitle("Data Issues Report")
        window.resize(760, 420)
        layout = QVBoxLayout(window)
        header = QHBoxLayout()
        header.addWidget(
            QLabel(f"{len(self.result.excluded)} row(s) excluded; {len(self.result.warnings)} warning(s).")
        )
        header.addStretch()
        export = QPushButton("Export CSV...")
        export.clicked.connect(self.export_excluded_rows)
        header.addWidget(export)
        layout.addLayout(header)
        layout.addWidget(table)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.show()
        self._excluded_window = window

    def export_excluded_rows(self) -> None:
        if self.result is None or self._data_issue_report().empty:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Data Issues",
            "data_issues.csv",
            "CSV File (*.csv)",
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != ".csv":
            path = path.with_suffix(".csv")
        self._data_issue_report().to_csv(path, index=False)
        self.statusBar().showMessage(f"Exported data issues to {path.name}.")

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._analysis_is_running():
            QMessageBox.information(self, "Analysis Running", "Wait for the current analysis to finish before closing.")
            event.ignore()
            return
        if not self._confirm_save_changes():
            event.ignore()
            return
        super().closeEvent(event)

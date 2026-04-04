"""字体管理器对话框"""

from __future__ import annotations

import asyncio
import shutil
import threading
from pathlib import Path
from typing import Optional

from inkscape_wps.core.services.font_service import FontService
from inkscape_wps.ui.qt_compat import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSize,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)


class FontManagerDialog(QDialog):
    """字体管理器对话框"""

    fontsLoaded = pyqtSignal(object)
    fontLoadFinished = pyqtSignal(str, bool, str)
    taskFinished = pyqtSignal(str, bool, str)

    def __init__(self, font_service: FontService, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.font_service = font_service
        self.setWindowTitle("字体管理器")
        self.resize(800, 600)

        self.fontsLoaded.connect(self._apply_loaded_fonts)
        self.fontLoadFinished.connect(self._on_font_loaded)
        self.taskFinished.connect(self._on_task_finished)

        self._setup_ui()
        self._load_fonts()

    def _setup_ui(self) -> None:
        """设置界面"""
        layout = QVBoxLayout(self)

        # 顶部工具栏
        toolbar = QHBoxLayout()

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self._refresh_fonts)

        self.import_btn = QPushButton("导入字体...")
        self.import_btn.clicked.connect(self._import_font)

        self.export_btn = QPushButton("导出选中字体...")
        self.export_btn.clicked.connect(self._export_font)

        self.merge_btn = QPushButton("合并字体...")
        self.merge_btn.clicked.connect(self._merge_fonts)

        toolbar.addWidget(self.refresh_btn)
        toolbar.addWidget(self.import_btn)
        toolbar.addWidget(self.export_btn)
        toolbar.addWidget(self.merge_btn)
        toolbar.addStretch()

        layout.addLayout(toolbar)

        # 主要内容区域
        content_layout = QHBoxLayout()

        # 左侧：字体列表
        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("可用字体:"))

        self.font_list = QListWidget()
        self.font_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.font_list.itemSelectionChanged.connect(self._on_font_selected)
        left_panel.addWidget(self.font_list)

        # 右侧：字体信息和预览
        right_panel = QVBoxLayout()

        # 字体信息
        info_group = QVBoxLayout()
        info_group.addWidget(QLabel("字体信息:"))

        self.font_info = QLabel("选择字体以查看信息")
        self.font_info.setWordWrap(True)
        info_group.addWidget(self.font_info)

        # 字符集预览
        char_group = QVBoxLayout()
        char_group.addWidget(QLabel("字符集预览:"))

        self.char_preview = QListWidget()
        self.char_preview.setViewMode(QListWidget.ViewMode.IconMode)
        self.char_preview.setIconSize(QSize(32, 32))
        self.char_preview.setGridSize(QSize(40, 40))
        char_group.addWidget(self.char_preview)

        right_panel.addLayout(info_group)
        right_panel.addLayout(char_group)

        content_layout.addLayout(left_panel, 1)
        content_layout.addLayout(right_panel, 2)

        layout.addLayout(content_layout)

        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

    def _load_fonts(self) -> None:
        """加载字体列表"""
        self.font_list.clear()
        self.font_info.setText("正在加载字体列表...")
        self._run_in_thread(self._load_fonts_worker)

    def _run_in_thread(self, target) -> None:
        thread = threading.Thread(target=target, daemon=True)
        thread.start()

    def _load_fonts_worker(self) -> None:
        try:
            font_names = asyncio.run(self.font_service.discover_fonts())
        except Exception as e:
            self.taskFinished.emit("load", False, f"加载字体失败: {e}")
            return
        self.fontsLoaded.emit(sorted(font_names))

    def _apply_loaded_fonts(self, font_names: object) -> None:
        names = [str(name) for name in font_names] if isinstance(font_names, list) else []
        self.font_list.clear()
        for font_name in names:
            self.font_list.addItem(QListWidgetItem(font_name))
        if names:
            self.font_info.setText(f"已加载 {len(names)} 个字体，选择字体以查看信息。")
        else:
            self.font_info.setText("未发现可用字体。")

    def _refresh_fonts(self) -> None:
        """刷新字体列表"""
        self._load_fonts()

    def _on_font_selected(self) -> None:
        """字体选择事件"""
        selected_items = self.font_list.selectedItems()
        if not selected_items:
            return

        font_name = selected_items[0].text()
        self.font_info.setText(f"正在加载字体 “{font_name}” ...")
        self._run_in_thread(lambda: self._load_font_worker(font_name))

    def _load_font_worker(self, font_name: str) -> None:
        try:
            loaded = asyncio.run(self.font_service.load_font(font_name))
        except Exception as e:
            self.fontLoadFinished.emit(font_name, False, str(e))
            return
        if not loaded:
            self.fontLoadFinished.emit(font_name, False, "字体加载失败")
            return
        self.fontLoadFinished.emit(font_name, True, "")

    def _on_font_loaded(self, font_name: str, success: bool, message: str) -> None:
        if not success:
            self.font_info.setText(message or f"字体加载失败: {font_name}")
            return
        self._show_font_info(font_name)

    def _show_font_info(self, font_name: str) -> None:
        """显示字体信息"""
        font_info = self.font_service.get_font_info(font_name)
        if not font_info:
            self.font_info.setText("字体信息不可用")
            return

        # 显示基本信息
        info_text = f"""字体名称: {font_name}
类型: {font_info.get('type', '未知')}
状态: {'已加载' if font_info.get('loaded', False) else '未加载'}
"""

        if 'metadata' in font_info:
            metadata = font_info['metadata']
            info_text += f"字符数: {font_info.get('character_count', 0)}\n"
            if 'description' in metadata:
                info_text += f"描述: {metadata['description']}\n"
            if 'version' in metadata:
                info_text += f"版本: {metadata['version']}\n"

        self.font_info.setText(info_text)

        # 显示字符集
        self._show_character_set(font_name)

    def _show_character_set(self, font_name: str) -> None:
        """显示字符集"""
        self.char_preview.clear()

        char_set = self.font_service.get_character_set(font_name)
        if not char_set:
            return

        # 显示前100个字符
        for char in char_set[:100]:
            item = QListWidgetItem(char)
            item.setFont(item.font())  # 使用默认字体显示字符
            self.char_preview.addItem(item)

    def _import_font(self) -> None:
        """导入字体"""
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        file_dialog.setNameFilter("字体文件 (*.json *.jhf)")

        if file_dialog.exec() == QDialog.DialogCode.Accepted:
            imported = self._import_font_files(
                [Path(file_path) for file_path in file_dialog.selectedFiles()]
            )
            if imported:
                self.font_info.setText(f"已导入 {imported} 个字体文件。")
                self._refresh_fonts()

    def _user_font_dir(self) -> Path:
        return Path.home() / ".config" / "inkscape-wps" / "fonts"

    def _import_font_files(self, files: list[Path]) -> int:
        imported = 0
        target_dir = self._user_font_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        for src in files:
            if not src.is_file():
                continue
            if src.suffix.lower() not in {".json", ".jhf"}:
                continue
            shutil.copy2(src, target_dir / src.name)
            imported += 1
        if imported > 0:
            self.font_service.clear_cache()
        return imported

    def _export_font(self) -> None:
        """导出字体"""
        selected_items = self.font_list.selectedItems()
        if not selected_items:
            return

        font_name = selected_items[0].text()

        file_dialog = QFileDialog(self)
        file_dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        file_dialog.setNameFilter("JSON字体 (*.json)")
        file_dialog.setDefaultSuffix("json")

        if file_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        output_path = Path(file_dialog.selectedFiles()[0])
        try:
            self.font_info.setText(f"正在导出字体到 {output_path} ...")
            self._run_in_thread(
                lambda: self._export_font_worker(font_name, output_path)
            )
        except Exception as e:
            self.font_info.setText(f"导出失败: {e}")

    def _export_font_worker(self, font_name: str, output_path: Path) -> None:
        try:
            success = asyncio.run(self.font_service.export_font(font_name, output_path))
        except Exception as e:
            self.taskFinished.emit("export", False, f"导出失败: {e}")
            return
        if success:
            self.taskFinished.emit("export", True, f"字体导出成功: {output_path}")
        else:
            self.taskFinished.emit("export", False, "字体导出失败")

    def _merge_fonts(self) -> None:
        """合并字体"""
        # 创建字体选择对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("合并字体")
        dialog.resize(400, 200)

        layout = QVBoxLayout(dialog)

        # 基础字体选择
        base_layout = QHBoxLayout()
        base_layout.addWidget(QLabel("基础字体:"))
        base_combo = QComboBox()
        base_combo.addItems(self.font_service.get_available_fonts())
        base_layout.addWidget(base_combo)
        layout.addLayout(base_layout)

        # 附加字体选择
        add_layout = QHBoxLayout()
        add_layout.addWidget(QLabel("附加字体:"))
        add_combo = QComboBox()
        add_combo.addItems(self.font_service.get_available_fonts())
        add_layout.addWidget(add_combo)
        layout.addLayout(add_layout)

        # 输出名称
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("输出名称:"))
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("输入新字体名称")
        name_edit.setText(f"{base_combo.currentText()}_{add_combo.currentText()}")
        name_layout.addWidget(name_edit)
        layout.addLayout(name_layout)

        # 按钮
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        cancel_btn = QPushButton("取消")
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            base_font = base_combo.currentText()
            add_font = add_combo.currentText()
            output_name = name_edit.text()

            if base_font and add_font and output_name:
                self.font_info.setText(
                    f"正在合并字体: {base_font} + {add_font} -> {output_name}"
                )
                self._run_in_thread(
                    lambda: self._merge_fonts_worker(base_font, add_font, output_name)
                )

    def _merge_fonts_worker(
        self,
        base_font: str,
        add_font: str,
        output_name: str,
    ) -> None:
        try:
            success = asyncio.run(
                self.font_service.merge_fonts(base_font, add_font, output_name)
            )
        except Exception as e:
            self.taskFinished.emit("merge", False, f"合并失败: {e}")
            return
        if success:
            self.taskFinished.emit("merge", True, f"字体合并成功: {output_name}")
        else:
            self.taskFinished.emit("merge", False, "字体合并失败")

    def _on_task_finished(self, action: str, success: bool, message: str) -> None:
        self.font_info.setText(message)
        if action == "merge" and success:
            self._refresh_fonts()

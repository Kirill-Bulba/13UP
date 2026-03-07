import sys
import sqlite3
from pathlib import Path
from PyQt5.QtCore import Qt, QDate, QSize
from PyQt5.QtGui import QFont, QIntValidator, QDoubleValidator, QPixmap, QPalette, QColor, QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QFileDialog,
)

LABEL_OVERRIDES = {
    "Holodilniki": "Холодильники",
    "Klienty": "Клиенты",
    "Zakazy": "Заказы",
    "kod_modeli": "Код модели",
    "model": "Модель",
    "zavod_izgotovitel": "Завод-изготовитель",
    "kolichestvo_morozilnyh_kamer": "Количество морозильных камер",
    "tsvet": "Цвет",
    "tsena": "Цена",
    "image_path": "Путь к изображению",
    "id_klienta": "ID клиента",
    "familiya": "Фамилия",
    "imya": "Имя",
    "otchestvo": "Отчество",
    "gorod": "Город",
    "nomer_zakaza": "Номер заказа",
    "data_zakaza": "Дата заказа",
    "kolichestvo": "Количество",
    "skidka": "Скидка",
}


def display_label(name: str) -> str:
    if name in LABEL_OVERRIDES:
        return LABEL_OVERRIDES[name]
    return translit_to_ru(name)


def is_file_field(name: str) -> bool:
    n = name.lower()
    return "image" in n or "photo" in n or "img" in n or n.endswith("_path") or n.endswith("path")

def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'

BASE_DIR = Path(__file__).resolve().parent
class DbSchema:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
    def list_tables(self):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [row[0] for row in cur.fetchall()]
    def columns(self, table: str):
        cur = self.conn.cursor()
        cur.execute(f"PRAGMA table_info({quote_ident(table)})")
        cols = []
        for cid, name, col_type, notnull, dflt_value, pk in cur.fetchall():
            cols.append(
                {
                    "name": name,
                    "type": (col_type or "").upper(),
                    "notnull": bool(notnull),
                    "pk": bool(pk),
                    "default": dflt_value,
                }
            )
        return cols
    def foreign_keys(self, table: str):
        cur = self.conn.cursor()
        cur.execute(f"PRAGMA foreign_key_list({quote_ident(table)})")
        fk_map = {}
        for _id, _seq, ref_table, from_col, to_col, *_rest in cur.fetchall():
            fk_map[from_col] = (ref_table, to_col)
        return fk_map
class RecordDialog(QDialog):
    def __init__(self, conn, table, columns, fk_map, mode="add", row_data=None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.table = table
        self.columns = columns
        self.fk_map = fk_map
        self.mode = mode
        self.inputs = {}
        self.setWindowTitle("Добавить запись" if mode == "add" else "Редактировать запись")
        root = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignHCenter | Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        for col in self.columns:
            self._add_field(form, col)
        root.addLayout(form)
        root.addSpacing(8)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        if ok_btn is not None:
            ok_btn.setText("ОК")
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        if cancel_btn is not None:
            cancel_btn.setText("Отмена")
        root.addWidget(buttons)
        if row_data is not None:
            self.set_values(row_data)
        if self.mode == "edit":
            for col in self.columns:
                if col["pk"]:
                    widget = self.inputs[col["name"]]
                    widget.setDisabled(True)
    def accept(self):
        missing = self.validate()
        if missing:
            QMessageBox.critical(
                self,
                "Ошибка",
                "Заполните обязательные поля: " + ", ".join(missing),
                QMessageBox.Ok,
            )
            return
        super().accept()

    def _add_field(self, layout, col):
        name = col["name"]
        label = QLabel(self._pretty_name(name))
        if self._is_file_field(name):
            container, line = self._file_input()
            self.inputs[name] = line
            layout.addRow(label, container)
            return
        widget = self._make_widget(col)
        self.inputs[name] = widget
        layout.addRow(label, widget)
    def _file_input(self):
        container = QWidget(self)
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        line = QLineEdit(container)
        btn = QPushButton("...", container)
        btn.setFixedWidth(28)
        btn.clicked.connect(lambda: self._select_file(line))
        row.addWidget(line)
        row.addWidget(btn)
        return container, line
    def _select_file(self, line):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Выберите файл", "", "Изображения (*.png *.jpg *.jpeg);;Все файлы (*)"
        )
        if filename:
            path = Path(filename)
            try:
                rel = path.resolve().relative_to(BASE_DIR)
                line.setText(str(rel).replace("\\", "/"))
            except ValueError:
                line.setText(filename)
    def _make_widget(self, col):
        name = col["name"]
        col_type = col["type"]
        if name in self.fk_map:
            combo = QComboBox(self)
            if not col["notnull"]:
                combo.addItem("-", None)
            ref_table, ref_col = self.fk_map[name]
            values = self._load_fk_values(ref_table, ref_col)
            for v in values:
                combo.addItem(str(v), v)
            return combo
        if self._is_date_field(name):
            date = QDateEdit(self)
            date.setCalendarPopup(True)
            date.setDisplayFormat("dd.MM.yyyy")
            date.setDate(QDate.currentDate())
            return date
        if col_type.startswith("INT"):
            line = QLineEdit(self)
            validator = QIntValidator()
            if "skidka" in name.lower():
                validator.setBottom(0)
                validator.setTop(100)
            elif "kolichestvo" in name.lower():
                validator.setBottom(1)
            line.setValidator(validator)
            if col["pk"] and self.mode == "add":
                line.setPlaceholderText("Авто")
            return line
        if col_type.startswith("REAL") or col_type.startswith("FLOAT") or col_type.startswith("DOUBLE"):
            line = QLineEdit(self)
            validator = QDoubleValidator()
            validator.setNotation(QDoubleValidator.StandardNotation)
            if "tsena" in name.lower() or "price" in name.lower():
                validator.setBottom(0.01)
            line.setValidator(validator)
            return line
        line = QLineEdit(self)
        return line
    def _load_fk_values(self, table, column):
        cur = self.conn.cursor()
        cur.execute(f"SELECT {quote_ident(column)} FROM {quote_ident(table)} ORDER BY {quote_ident(column)}")
        return [row[0] for row in cur.fetchall()]
    def _pretty_name(self, name):
        return display_label(name)
    def _is_date_field(self, name):
        n = name.lower()
        return "data" in n or "date" in n
    def _is_file_field(self, name):
        return is_file_field(name)

    def set_values(self, row_data):
        for idx, col in enumerate(self.columns):
            name = col["name"]
            value = row_data[idx]
            widget = self.inputs[name]
            if isinstance(widget, QComboBox):
                self._set_combo_value(widget, value)
                continue
            if isinstance(widget, QDateEdit):
                if value:
                    date = self._parse_date(value)
                    if date.isValid():
                        widget.setDate(date)
                continue
            text = "" if value is None else str(value)
            widget.setText(text)
    def _set_combo_value(self, combo, value):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(0)
    def _parse_date(self, value):
        value = str(value)
        for fmt in ("yyyy-MM-dd", "dd.MM.yyyy", "yyyy/MM/dd"):
            date = QDate.fromString(value, fmt)
            if date.isValid():
                return date
        return QDate.currentDate()
    def get_values(self):
        values = {}
        for col in self.columns:
            name = col["name"]
            col_type = col["type"]
            widget = self.inputs[name]
            if isinstance(widget, QComboBox):
                values[name] = widget.currentData()
                continue
            if isinstance(widget, QDateEdit):
                values[name] = widget.date().toString("yyyy-MM-dd")
                continue
            text = widget.text().strip()
            if text == "":
                values[name] = None
                continue
            if col_type.startswith("INT"):
                values[name] = int(text)
            elif col_type.startswith("REAL") or col_type.startswith("FLOAT") or col_type.startswith("DOUBLE"):
                values[name] = float(text.replace(",", "."))
            else:
                values[name] = text
        return values
    def validate(self):
        values = self.get_values()
        missing = []
        for col in self.columns:
            if not col["notnull"]:
                continue
            value = values[col["name"]]
            if value is None or value == "":
                missing.append(self._pretty_name(col["name"]))
        return missing
class MainWindow(QMainWindow):
    def __init__(self, conn):
        super().__init__()
        self.conn = conn
        self.schema = DbSchema(conn)
        self.current_columns = []
        self.current_rows = []
        self.setWindowTitle("База данных холодильников")
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        top = QHBoxLayout()
        top.setSpacing(12)
        self.logo = QLabel(self)
        self.logo.setFixedSize(100, 100)
        self.logo.setAlignment(Qt.AlignCenter)
        logo_path = Path(__file__).resolve().parent / "HPhoto" / "101.jpg"
        if logo_path.exists():
            pix = QPixmap(str(logo_path)).scaled(
                100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.logo.setPixmap(pix)
        else:
            self.logo.setText("Логотип")
        title = QLabel("Информационная система")
        title_font = QFont("Times New Roman", 16, QFont.Bold)
        title.setFont(title_font)
        top.addWidget(self.logo)
        top.addWidget(title)
        top.addStretch()
        controls = QHBoxLayout()
        controls.setSpacing(8)
        table_label = QLabel("Таблица:")
        self.table_combo = QComboBox()
        self.table_combo.setMinimumWidth(180)
        self.table_combo.currentTextChanged.connect(self.on_table_changed)
        self.add_btn = QPushButton("Добавить запись")
        self.add_btn.clicked.connect(self.add_record)
        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self.refresh_table)
        controls.addWidget(table_label)
        controls.addWidget(self.table_combo)
        controls.addWidget(self.add_btn)
        controls.addWidget(self.refresh_btn)
        top.addLayout(controls)
        root.addLayout(top)
        self.table = QTableWidget(self)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setMinimumSectionSize(120)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setStyleSheet("QTableWidget::item { padding: 6px; }")
        self.table.itemDoubleClicked.connect(self.edit_record)
        root.addWidget(self.table)
        self.setCentralWidget(central)
        self.load_tables()
    def load_tables(self):
        tables = self.schema.list_tables()
        self.table_combo.clear()
        for table in tables:
            self.table_combo.addItem(display_label(table), table)
        if tables:
            self.table_combo.setCurrentIndex(0)
            self.refresh_table()

    def current_table(self):
        table = self.table_combo.currentData()
        if table:
            return table
        return self.table_combo.currentText()
    def on_table_changed(self, _):
        self.refresh_table()
    def refresh_table(self):
        table = self.current_table()
        if not table:
            return
        self.current_columns = self.schema.columns(table)
        self.current_rows = self.fetch_rows(table)
        image_cols = {
            idx for idx, col in enumerate(self.current_columns) if is_file_field(col["name"])
        }
        self.table.clear()
        self.table.setColumnCount(len(self.current_columns))
        self.table.setRowCount(len(self.current_rows))
        self.table.setHorizontalHeaderLabels([display_label(c["name"]) for c in self.current_columns])
        if image_cols:
            self.table.setIconSize(QSize(90, 90))
        for r, row in enumerate(self.current_rows):
            for c, value in enumerate(row):
                if c in image_cols:
                    item = QTableWidgetItem()
                    img_path = self.resolve_image_path(value)
                    if img_path is not None:
                        item.setIcon(QIcon(str(img_path)))
                    if value is not None:
                        item.setToolTip(str(value))
                    self.table.setItem(r, c, item)
                else:
                    item = QTableWidgetItem("" if value is None else str(value))
                    item.setData(Qt.UserRole, value)
                    self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()

    def resolve_image_path(self, value):
        if not value:
            return None
        path = Path(str(value))
        if not path.is_absolute():
            path = BASE_DIR / path
        if path.exists():
            return path
        return None

    def fetch_rows(self, table):
        cols = self.schema.columns(table)
        pk_cols = [c["name"] for c in cols if c["pk"]]
        order_by = ""
        if pk_cols:
            order_by = " ORDER BY " + ", ".join(quote_ident(c) for c in pk_cols)
        cur = self.conn.cursor()
        cur.execute(f"SELECT * FROM {quote_ident(table)}{order_by}")
        return cur.fetchall()
    def add_record(self):
        table = self.current_table()
        if not table:
            return
        columns = self.schema.columns(table)
        fk_map = self.schema.foreign_keys(table)
        dialog = RecordDialog(self.conn, table, columns, fk_map, mode="add", parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return
        values = dialog.get_values()
        try:
            self.insert_record(table, columns, values)
            self.refresh_table()
        except sqlite3.IntegrityError as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось добавить запись.\n{exc}")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось добавить запись.\n{exc}")
    def edit_record(self, item):
        table = self.current_table()
        if not table:
            return
        row_idx = item.row()
        if row_idx < 0 or row_idx >= len(self.current_rows):
            return
        columns = self.current_columns
        fk_map = self.schema.foreign_keys(table)
        row_data = self.current_rows[row_idx]
        dialog = RecordDialog(
            self.conn, table, columns, fk_map, mode="edit", row_data=row_data, parent=self
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        values = dialog.get_values()
        try:
            self.update_record(table, columns, values, row_data)
            self.refresh_table()
        except sqlite3.IntegrityError as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось обновить запись.\n{exc}")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось обновить запись.\n{exc}")
    def insert_record(self, table, columns, values):
        insert_cols = []
        params = []
        for col in columns:
            name = col["name"]
            val = values.get(name)
            if col["pk"] and (val is None or val == ""):
                continue
            insert_cols.append(name)
            params.append(val)
        cols_sql = ", ".join(quote_ident(c) for c in insert_cols)
        placeholders = ", ".join(["?"] * len(insert_cols))
        sql = f"INSERT INTO {quote_ident(table)} ({cols_sql}) VALUES ({placeholders})"
        cur = self.conn.cursor()
        cur.execute(sql, params)
        self.conn.commit()
    def update_record(self, table, columns, values, old_row):
        set_cols = [c["name"] for c in columns if not c["pk"]]
        pk_cols = [c["name"] for c in columns if c["pk"]]
        if not pk_cols:
            raise RuntimeError("Нет первичного ключа для обновления.")
        set_clause = ", ".join(f"{quote_ident(c)}=?" for c in set_cols)
        where_clause = " AND ".join(f"{quote_ident(c)}=?" for c in pk_cols)
        params = [values[c] for c in set_cols]
        pk_values = []
        for idx, col in enumerate(columns):
            if col["name"] in pk_cols:
                pk_values.append(old_row[idx])
        sql = f"UPDATE {quote_ident(table)} SET {set_clause} WHERE {where_clause}"
        cur = self.conn.cursor()
        cur.execute(sql, params + pk_values)
        self.conn.commit()
def build_app():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Times New Roman", 12))

    pal = app.palette()
    pal.setColor(QPalette.Window, QColor("#F7F5F2"))
    pal.setColor(QPalette.Base, QColor("#FFFFFF"))
    pal.setColor(QPalette.AlternateBase, QColor("#F0F4F3"))
    pal.setColor(QPalette.Button, QColor("#DFF1EA"))
    pal.setColor(QPalette.ButtonText, QColor("#1F2A2E"))
    pal.setColor(QPalette.Text, QColor("#1F2A2E"))
    pal.setColor(QPalette.WindowText, QColor("#1F2A2E"))
    pal.setColor(QPalette.Highlight, QColor("#CFE8E6"))
    pal.setColor(QPalette.HighlightedText, QColor("#1F2A2E"))
    app.setPalette(pal)

    app.setStyleSheet(
        """
        QWidget { color: #1F2A2E; }
        QMainWindow { background: #F7F5F2; }
        QTableWidget {
            background: #FFFFFF;
            border: 1px solid #E1E4E6;
            selection-background-color: #CFE8E6;
            selection-color: #1B1F22;
        }
        QHeaderView::section {
            background: #E6ECEB;
            color: #1F2A2E;
            padding: 6px 8px;
            border: none;
            border-bottom: 1px solid #D7DBDE;
        }
        QLineEdit, QComboBox, QDateEdit {
            background: #FFFFFF;
            border: 1px solid #D7DBDE;
            border-radius: 6px;
            padding: 4px 6px;
        }
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
            border: 1px solid #2F6F6D;
        }
        QPushButton {
            background: #DFF1EA;
            color: #1F2A2E;
            border: 1px solid #BFD6CF;
            border-radius: 6px;
            padding: 6px 12px;
        }
        QPushButton:hover { background: #CDE7DE; }
        QPushButton:pressed { background: #B7D8CD; }
        QDialog { background: #F7F5F2; }
        """
    )

    return app
def main():
    db_path = BASE_DIR / "XolodilnikiBD"
    if not db_path.exists():
        print("База данных не найдена:", db_path)
        return
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    app = build_app()
    window = MainWindow(conn)
    window.resize(900, 600)
    window.show()
    exit_code = app.exec_()
    conn.close()
    sys.exit(exit_code)
if __name__ == "__main__":
    main()


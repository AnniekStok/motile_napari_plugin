from PyQt5.QtCore import Qt, pyqtSignal
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class SelectMode(QWidget):
    """Widget to switch between different display modes: selected node(s), track, lineage, all"""

    display_updated = pyqtSignal()
    reset_display = pyqtSignal()

    def __init__(self):
        super().__init__()

        mode_box = QGroupBox("Select visible objects [T]")
        mode_box_layout = QVBoxLayout()

        # create a group of checkboxes to apply selection to
        apply_group_layout = QVBoxLayout()
        apply_group_layout.addWidget(QLabel("Apply to:"))
        self.tree_widget_ch = QCheckBox("Lineage Tree")
        self.tree_widget_ch.stateChanged.connect(self._update_state)
        self.labels_ch = QCheckBox("Highlighted Labels")
        self.labels_ch.stateChanged.connect(self._update_state)
        self.points_ch = QCheckBox("Points")
        self.points_ch.stateChanged.connect(self._update_state)
        apply_group_layout.addWidget(self.tree_widget_ch)
        apply_group_layout.addWidget(self.labels_ch)
        apply_group_layout.addWidget(self.points_ch)

        # Create dropdown menu
        self.selection_combo = QComboBox()
        self.selection_combo.addItem("Selected nodes")
        self.selection_combo.addItem("Current track")
        self.selection_combo.addItem("Current lineage")
        self.selection_combo.addItem("Manual edits")
        self.selection_combo.currentIndexChanged.connect(self._update_display)

        mode_box_layout.addLayout(apply_group_layout)
        mode_box_layout.addWidget(QLabel("Show:"))
        mode_box_layout.addWidget(self.selection_combo)
        mode_box.setLayout(mode_box_layout)

        main_layout = QHBoxLayout()
        main_layout.addWidget(mode_box)

        self.setLayout(main_layout)

    def _update_state(self, state: int):
        """Send signal depending on whether or not the checkbox was checked or unchecked"""

        if state == Qt.Checked:
            self.display_updated.emit()
        else:
            self.reset_display.emit()

    def _update_display(self):
        """Sends a signal to update the display"""

        self.display_updated.emit()

    def _select_next_display_option(self):
        """Selects the next button"""

        # Get the current selection
        checked_id = self.selection_combo.currentIndex()
        next_id = checked_id + 1
        if next_id > 4:
            next_id = 0
        self.selection_combo.setCurrentIndex(next_id)

        self.display_updated.emit()

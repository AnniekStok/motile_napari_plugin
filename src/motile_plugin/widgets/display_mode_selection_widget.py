from PyQt5.QtCore import pyqtSignal
from qtpy.QtWidgets import (
    QButtonGroup,
    QGroupBox,
    QHBoxLayout,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class SelectMode(QWidget):
    """Widget to switch between different display modes: selected node(s), track, lineage, all"""

    mode_updated = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        mode_box = QGroupBox("Select display mode")
        mode_box_layout = QVBoxLayout()

        button_group = QButtonGroup()

        selected_nodes_btn = QRadioButton("Selected nodes")
        track_btn = QRadioButton("Current track")
        lineage_btn = QRadioButton("Current lineage")
        all_btn = QRadioButton("All nodes")

        selected_nodes_btn.clicked.connect(
            lambda: self._update_display("selection")
        )
        track_btn.clicked.connect(lambda: self._update_display("track"))
        lineage_btn.clicked.connect(lambda: self._update_display("lineage"))
        all_btn.clicked.connect(lambda: self._update_display("all"))

        selected_nodes_btn.setChecked(True)

        button_group.addButton(selected_nodes_btn)
        button_group.addButton(track_btn)
        button_group.addButton(lineage_btn)
        button_group.addButton(all_btn)

        mode_box_layout.addWidget(selected_nodes_btn)
        mode_box_layout.addWidget(track_btn)
        mode_box_layout.addWidget(lineage_btn)
        mode_box_layout.addWidget(all_btn)

        mode_box.setLayout(mode_box_layout)

        main_layout = QHBoxLayout()
        main_layout.addWidget(mode_box)

        self.setLayout(main_layout)

    def _update_display(self, mode: str):
        """Sends a signal to update the mode"""

        self.mode_updated.emit(mode)

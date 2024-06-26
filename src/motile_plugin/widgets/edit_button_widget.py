from functools import partial

from PyQt5.QtCore import pyqtSignal
from qtpy.QtWidgets import QGroupBox, QPushButton, QVBoxLayout, QWidget

from ..utils.node_selection import NodeSelectionList


class AnnotationButtons(QWidget):
    """Widget holding the buttons for editing nodes and edges"""

    edge_edit = pyqtSignal(str)
    node_edit = pyqtSignal(str)

    def __init__(self, selected_nodes: NodeSelectionList):
        super().__init__()

        self.selected_nodes = selected_nodes
        self.selected_nodes.list_updated.connect(self._update_buttons)

        # Add buttons to modify nodes
        button_layout = QVBoxLayout()

        node_box = QGroupBox("Modify nodes")
        node_box_layout = QVBoxLayout()
        node_box.setLayout(node_box_layout)

        self.fork_btn = QPushButton("Fork [F] ▼")
        self.fork_btn.clicked.connect(partial(self._edit_node, edit="Fork"))
        self.fork_btn.setEnabled(False)
        node_box_layout.addWidget(self.fork_btn)

        self.close_btn = QPushButton("Close [C] ×")
        self.close_btn.clicked.connect(partial(self._edit_node, edit="Close"))
        self.close_btn.setEnabled(False)
        node_box_layout.addWidget(self.close_btn)

        self.reset_btn = QPushButton("Reset [R] ●")
        self.reset_btn.clicked.connect(partial(self._edit_node, edit="Reset"))
        self.reset_btn.setEnabled(False)
        node_box_layout.addWidget(self.reset_btn)

        button_layout.addWidget(node_box)

        # Add buttons to create or destroy connections
        edge_box = QGroupBox("Modify edges")
        edge_box_layout = QVBoxLayout()

        self.connect_btn = QPushButton("Connect [A]")
        self.connect_btn.clicked.connect(partial(self._edit_edge, edit="Add"))
        self.connect_btn.setEnabled(False)
        edge_box_layout.addWidget(self.connect_btn)

        self.break_btn = QPushButton("Break [B]")
        self.break_btn.clicked.connect(partial(self._edit_edge, edit="Break"))
        self.break_btn.setEnabled(False)
        edge_box_layout.addWidget(self.break_btn)

        edge_box.setLayout(edge_box_layout)
        button_layout.addWidget(edge_box)

        self.setLayout(button_layout)

    def _update_buttons(self) -> None:
        """Enable/disable the buttons depending on the current selection and when connections between selected nodes are possible/impossible"""

        if len(self.selected_nodes) == 1:
            self.fork_btn.setEnabled(True)
            self.close_btn.setEnabled(True)
            self.reset_btn.setEnabled(True)
            self.connect_btn.setEnabled(False)
            self.break_btn.setEnabled(False)
        elif len(self.selected_nodes) == 2 and self._check_connection():
            self.fork_btn.setEnabled(False)
            self.close_btn.setEnabled(False)
            self.reset_btn.setEnabled(False)
            self.connect_btn.setEnabled(True)
            self.break_btn.setEnabled(True)
        else:
            self.fork_btn.setEnabled(False)
            self.close_btn.setEnabled(False)
            self.reset_btn.setEnabled(False)
            self.connect_btn.setEnabled(False)
            self.break_btn.setEnabled(False)

    def _check_connection(self) -> bool:
        """Check if a valid connection (1 time point apart) is possible between the two selected nodes, and if so make sure the one with the smallest time point comes first in self.selected_nodes"""

        tp1, tp2 = self.selected_nodes[0]["t"], self.selected_nodes[1]["t"]

        # Check whether the two nodes are one time point apart
        if not ((tp2 - tp1 == 1) or (tp1 - tp2 == 1)):
            print("these two points are not one time point apart")
            return False

        # Swap nodes to ensure that the one with the smallest time point comes first
        if tp2 < tp1:
            self.selected_nodes.flip()

        return True

    def _edit_edge(self, edit: str) -> None:
        """Emit signal to trigger edge edit event"""

        self.edge_edit.emit(edit)

    def _edit_node(self, edit: str) -> None:
        """Emit signal to trigger node edit event"""

        self.node_edit.emit(edit)

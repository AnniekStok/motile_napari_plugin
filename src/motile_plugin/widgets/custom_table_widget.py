
from qtpy.QtWidgets     import QTableWidget, QTableWidgetItem, QWidget, QGridLayout, QPushButton
from qtpy.QtGui         import QColor
from PyQt5.QtCore       import pyqtSignal
from typing             import List

class TableWidget(QWidget):
    """
    Colored TableWidget displaying data from a dictionary and a custom list of columns. 
    """

    valueClicked = pyqtSignal(str)  # Define a custom signal

    def __init__(self, data:dict, displayed_columns:List):
        super().__init__()

        self._data = data
        self.displayed_columns = displayed_columns

        self._view = QTableWidget()
        self._view.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._view.itemClicked.connect(self._on_item_clicked)
        
        delete_row_btn = QPushButton("Delete selected rows")
        delete_row_btn.clicked.connect(self._delete_row)

        self.setLayout(QGridLayout())
        self.layout().addWidget(delete_row_btn)
        self.layout().addWidget(self._view)

        self.set_content()

    def _add_row(self, new_row: dict):
        """Add a new row to the table"""

        for key in new_row:
            self._data[key].append(new_row[key])
        
        self.set_content()

    def _delete_row(self):
        """Delete the currently selected rows"""

        selected_items = self._view.selectedItems()
        if not selected_items:
            return  # No item selected

        rows_to_delete = set(item.row() for item in selected_items)
        rows_to_delete = sorted(rows_to_delete, reverse=True)  # Delete from the bottom up
   
        for row in rows_to_delete:
            self._view.removeRow(row)
            for key in self._data:
                del self._data[key][row]
    
    def _on_item_clicked(self, item): 
        """Send a signal that a node was clicked"""
            
        self.valueClicked.emit(str(item.text()))

    def set_content(self):
        """
        Update the displayed contents in the QTableWidget
        """

        self._view.clear()
        try:
            self._view.setRowCount(len(next(iter(self._data.values()))))
            self._view.setColumnCount(len(self.displayed_columns))
        except StopIteration:
            pass

        for i, column in enumerate(self.displayed_columns):
            self._view.setHorizontalHeaderItem(i, QTableWidgetItem(column))
            for j, value in enumerate(self._data.get(column)):                
                item = QTableWidgetItem(str(value))
                self._view.setItem(j, i, item)
                # Set background color for the first two columns
                if i == 0: 
                    color1 = QColor(*self._data['Color1'][j])
                    item.setBackground(color1)
                elif i == 1:
                    color2 = QColor(*self._data['Color2'][j])
                    item.setBackground(color2)
        
        self._view.resizeColumnsToContents()
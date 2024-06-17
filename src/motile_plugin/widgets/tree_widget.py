import napari.layers

import numpy            as np
import pyqtgraph        as pg
import pandas           as pd 
import copy 

from PyQt5.QtCore       import Qt
from PyQt5.QtGui        import QMouseEvent
from functools          import partial

from qtpy.QtWidgets     import QHBoxLayout, QWidget, QPushButton, QVBoxLayout, QGroupBox
from typing             import List, Tuple

import networkx as nx

from .custom_table_widget  import TableWidget
from .volume_mode_widget    import VolumeModeWidget
from ..utils.point_tracker     import PointTracker

from ..utils.tree_widget_utils import bind_key_with_condition, extract_sorted_tracks, get_existing_pins, get_existing_forks_endpoints

class LineageTreeWidget(QWidget):
    """Interactive pyqtgraph based lineage tree widget class.
    """

    def __init__(self, viewer):
        super().__init__()

        self.viewer = viewer
        self.forks = []
        self.endpoints = []
        self.selected_labels_layer = None
        self.plane_slider = None

        # Construct the tree view pyqtgraph widget
        self.tree_widget = pg.PlotWidget()
        self.tree_widget.setTitle('Lineage Tree')
        self.tree_widget.setLabel('left', text='Time Point')
        self.tree_widget.getAxis('bottom').setStyle(showValues=False)
        self.g = pg.GraphItem()
        self.g.scatter.sigClicked.connect(self._on_click)
        self.tree_widget.addItem(self.g)

        # Add buttons to modify nodes
        button_layout = QVBoxLayout()
        
        node_box = QGroupBox('Modify nodes')
        node_box_layout = QVBoxLayout()
        node_box.setLayout(node_box_layout)

        self.fork_btn = QPushButton('Fork [F] ▼')
        self.fork_btn.clicked.connect(partial(self._edit_node, edit='Fork'))
        self.fork_btn.setEnabled(False)
        node_box_layout.addWidget(self.fork_btn)
    
        self.close_btn = QPushButton('Close [C] ×')
        self.close_btn.clicked.connect(partial(self._edit_node, edit='Close'))
        self.close_btn.setEnabled(False)
        node_box_layout.addWidget(self.close_btn)

        self.reset_btn = QPushButton('Reset [R] ●')
        self.reset_btn.clicked.connect(partial(self._edit_node, edit='Reset'))
        self.reset_btn.setEnabled(False)
        node_box_layout.addWidget(self.reset_btn)
        
        button_layout.addWidget(node_box)

        # Add buttons to create or destroy connections
        edge_box = QGroupBox('Modify edges')
        edge_box_layout = QVBoxLayout()

        self.connect_btn = QPushButton('Connect [A]')
        self.connect_btn.clicked.connect(partial(self._edit_edge, edit='Add'))
        self.connect_btn.setEnabled(False)
        edge_box_layout.addWidget(self.connect_btn)
        
        self.break_btn = QPushButton('Break [B]')
        self.break_btn.clicked.connect(partial(self._edit_edge, edit='Break'))
        self.break_btn.setEnabled(False)
        edge_box_layout.addWidget(self.break_btn)

        edge_box.setLayout(edge_box_layout)
        button_layout.addWidget(edge_box)

        # Add a table widget to keep accumulate actions before triggering the solver
        self.table_widget = TableWidget(data={"Source": [], "Target": [], "Action": [], "Color1": [], "Color2": []}, displayed_columns=["Source", "Target", "Action"])
        self.table_widget.setMaximumWidth(200)
        self.table_widget.valueClicked.connect(self._on_table_clicked)
        self.selected = []

        self.layout = QHBoxLayout()
        self.layout.addLayout(button_layout)
        self.layout.addWidget(self.tree_widget)
        self.layout.addWidget(self.table_widget)
        self.setLayout(self.layout)

    def _get_pins(self) -> List[Tuple[str, str, bool]]:
        """Extracts the edge edits ('Add', 'Break') from the table, to be used to pin edges as True or False"""

        edits = self.table_widget._data # get the data from the table
        if not len(edits) > 0:
            return None
        else:
            pins = []
            for i in range(len(edits['Source'])):
                source = edits['Source'][i]
                target = edits['Target'][i]
                action = edits['Action'][i]

                if action == "Add":
                    pins.append((source, target, True))
                elif action == "Break":
                    pins.append((source, target, False))

            return pins

    def _update(self, tracks:nx.DiGraph, labels:napari.layers.labels.labels.Labels) -> None:
        """Redraw the pyqtgraph object with the new tracking graph"""

        self.tracks = tracks
        self.track_df = extract_sorted_tracks(tracks, labels)
        self.labels = labels
        self.labels.opacity = 1
        self.point_tracker = PointTracker(self.track_df, self.viewer)
        self.point_tracker.point_selected.connect(self._on_point_selected)

        # Add key bindings for faster annotation        
        bind_key_with_condition(self.viewer, 'A', self.connect_btn, partial(self._edit_edge, edit='Add'))
        bind_key_with_condition(self.viewer, 'B', self.break_btn, partial(self._edit_edge, edit='Break'))
        bind_key_with_condition(self.viewer, 'F', self.fork_btn, partial(self._edit_node, edit='Fork'))
        bind_key_with_condition(self.viewer, 'C', self.close_btn, partial(self._edit_node, edit='Close'))
        bind_key_with_condition(self.viewer, 'R', self.reset_btn, partial(self._edit_node, edit='Reset'))

        pins = get_existing_pins(tracks)
        forks, endpoints = get_existing_forks_endpoints(tracks)

        if len(self.labels.data.shape) == 4: 
            self.selected_labels_layer = self.viewer.add_labels(self.labels.data, name = "Selected Label")
            self.selected_labels_layer.editable = False
            self.selected_labels_layer.show_selected_label = True
            self.selected_labels_layer.blending = 'translucent_no_depth'
            self.selected_labels_layer.depiction = 'volume'
            self.plane_slider = VolumeModeWidget(
                self.viewer, 
                self.labels, 
                self.selected_labels_layer, 
                self.point_tracker.points, 
                self.point_tracker.lines, 
                self.point_tracker.line_colors
            )
            self.viewer.dims.ndisplay = 3
            self.point_tracker.points.blending = 'translucent_no_depth'
            self.layout.insertWidget(0, self.plane_slider)
                                
        pos = []
        pos_colors = []
        adj = []
        adj_colors = []
        symbols = []
        sizes = []

        for _, node in self.track_df.iterrows():      
            if node['node_id'] in forks:
                symbols.append('t')
                pos_colors.append([255, 0, 0, 255]) # edits displayed in red
                sizes.append(13)
            elif node['node_id'] in endpoints:
                symbols.append('x')
                pos_colors.append([255, 0, 0, 255]) # edits displayed in red
                sizes.append(13)
            else:
                symbols.append('o')
                pos_colors.append(node['color'])           
                sizes.append(8)

            pos.append([node['x_axis_pos'], node['t']])
            parent = node['parent_id']
            if parent != 0:
                parent_df = self.track_df[self.track_df['node_id'] == parent]
                if not parent_df.empty:
                    parent_dict = parent_df.iloc[0]
                    adj.append([parent_dict['index'], node['index']])
                    if (parent_dict['node_id'], node['node_id']) in pins:
                        adj_colors.append([255, 0, 0, 255, 255, 1])
                    else:
                        adj_colors.append(parent_dict['color'].tolist() + [255, 1])
                       
        self.pos = np.array(pos)
        self.adj = np.array(adj)
        self.symbols = symbols
        self.symbolBrush = np.array(pos_colors)
        self.pen = np.array(adj_colors)
        self.size = np.array(sizes)

        if len(self.pos) > 0:           
            self.g.setData(pos=self.pos, adj=self.adj, symbol = self.symbols, symbolBrush = self.symbolBrush, size = self.size, pen = self.pen)
        else: 
            self.g.scatter.clear()

    def _on_point_selected(self, node_id: str, modifiers: Qt.KeyboardModifiers) -> None:
        """Connect point selection in the point_tracker to the tree widget"""

        # find the corresponding element in the list of dicts
        node_df = self.track_df[self.track_df['node_id'] == node_id]
        if not node_df.empty:
            self._select_node(node_df, modifiers)

    def _on_click(self, _, points: np.ndarray, ev: QMouseEvent) -> None:
        """Highlight and print the information about the currently selected node"""

        modifiers = ev.modifiers()
        clicked_point = points[0]
        index = clicked_point.index()  # Get the index of the clicked point

        # find the corresponding element in the list of dicts
        node_df = self.track_df[self.track_df['index'] == index]
        if not node_df.empty:
            self._select_node(node_df, modifiers)
    
    def _select_node(self, node_df: pd.DataFrame, modifiers: Qt.KeyboardModifiers) -> None:
        """Handle the current node selection and update visualization in the pyqtgraph and in the labels layer"""

        # if already two objects were selected, reset self.selected so that self.selected does not get a length of 3
        if len(self.selected) == 2:
            self.selected = []

        # extract the selected node 
        node = node_df.iloc[0].to_dict()  # Convert the filtered result to a dictionary

        # Update viewer step (only if the SHIFT key was not used)
        if modifiers != pg.QtCore.Qt.ShiftModifier:
            
            # Check for 'z' key and update step if exists
            step = list(self.viewer.dims.current_step)
            step[0] = node['t']
            if 'z' in node.keys():
                z = node['z']
                step[1] = int(z)       
            self.viewer.dims.current_step = step
            
            # if the viewer is in 3D plane mode, also adjust the plane we are looking at
            if self.plane_slider is not None: 
                if self.plane_slider.mode == 'plane':
                    self.plane_slider._set_plane_value(value=int(z))

            # update the selected label in the selected labels layer            
            self.labels.selected_label = node['track_id']
            if self.selected_labels_layer is not None:
                self.selected_labels_layer.selected_label = node['track_id']
            
        # Update the graph
        size = self.size.copy() # just copy the size here to keep the original self.size intact
        size[node['index']] = size[node['index']] + 5

        # if self.selected already contains another node and the user used SHIFT, add one
        if modifiers == pg.QtCore.Qt.ShiftModifier and len(self.selected) == 1:
            size[self.selected[0]['index']] = size[self.selected[0]['index']] + 5
            self.selected.append(node)
        else: 
            self.selected = [node]
                             
        self.g.setData(pos=self.pos, adj=self.adj, symbolBrush = self.symbolBrush, size = size, symbol = self.symbols, pen = self.pen)

        self._update_buttons()

    def _on_table_clicked(self, value: str) -> None:
        """Jump to the node selected by the user in the table"""
        
        if value not in ["Add", "Break"]:
            node_df = self.track_df[self.track_df['node_id'] == value]
            if not node_df.empty:
                self._select_node(node_df, modifiers = None)
        
    def _update_buttons(self) -> None:
        """Enable/disable the buttons depending on the current selection and when connections between selected nodes are possible/impossible"""

        if len(self.selected) == 1:
            self.fork_btn.setEnabled(True)
            self.close_btn.setEnabled(True)
            self.reset_btn.setEnabled(True)
            self.connect_btn.setEnabled(False)
            self.break_btn.setEnabled(False)
        elif len(self.selected) == 2 and self._check_connection(): 
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
        """Check if a valid connection (1 time point apart) is possible between the two selected nodes, and if so make sure the one with the smallest time point comes first in self.selected"""

        tp1, tp2 = self.selected[0]['t'], self.selected[1]['t']

        # Check whether the two nodes are one time point apart
        if not ((tp2 - tp1 == 1) or (tp1 - tp2 == 1)):
            print('these two points are not one time point apart')
            return False
        
        # Swap nodes to ensure that the one with the smallest time point comes first
        if tp2 < tp1:
            self.selected = [self.selected[1], self.selected[0]]               
        
        return True
    
    def _edit_edge(self, edit: str) -> None:
        """Add a new action (make or break an edge) to the table"""

        node1 = self.selected[0]
        node2 = self.selected[1]

        self.table_widget._add_row({"Source": node1['node_id'], "Target": node2['node_id'], "Action": edit, "Color1": [int(c) for c in node1['color'][:3]], "Color2": [int(c) for c in node2['color'][:3]]})
        
        self.selected = []
        self._update_buttons()
    
    def _edit_node(self, edit: str) -> None:
        """Add a mark to this node: 'Fork' mean this node is dividing so that should have two daughter nodes at the next time point, 
        'Close' means this node is and endpoint and it should have no daughters at the next time point. 
        'Reset' means to remove the 'Fork' or 'Close' mark"""

        node = self.selected[0]

        if edit == 'Fork':
            self.symbols[node['index']] = 't'
            self.size[node['index']] = 13
            self.symbolBrush[node['index']] = [255, 0, 0, 255]
            
            if node['node_id'] in self.endpoints: 
                self.endpoints.remove(node['node_id'])
            
            self.forks.append(node['node_id'])
        
        elif edit == 'Close': 
            self.symbols[node['index']] = 'x'
            self.size[node['index']] = 13
            self.symbolBrush[node['index']] = [255, 0, 0, 255]
            
            if node['node_id'] in self.forks: 
                self.forks.remove(node['node_id'])

            self.endpoints.append(node['node_id'])
        
        else: 
            self.symbols[node['index']] = 'o'
            self.size[node['index']] = 8
            self.symbolBrush[node['index']] = node['color']
            
            if node['node_id'] in self.forks: 
                self.forks.remove(node['node_id'])
            if node['node_id'] in self.endpoints: 
                self.endpoints.remove(node['node_id'])
                
        self.g.setData(pos=self.pos, adj=self.adj, symbol = self.symbols, symbolBrush = self.symbolBrush, size = self.size, pen = self.pen)            
        self.selected = []
        self._update_buttons()


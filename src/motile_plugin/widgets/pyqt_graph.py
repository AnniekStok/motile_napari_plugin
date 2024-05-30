import napari.layers

import numpy            as np
import pyqtgraph        as pg
import pandas           as pd 
import copy 

from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QMouseEvent

from qtpy.QtWidgets     import QHBoxLayout, QWidget
from typing             import List, Dict
from napari.utils       import DirectLabelColormap
from matplotlib.colors  import to_rgba

import networkx as nx
from motile_toolbox.candidate_graph import NodeAttr

def extract_sorted_tracks(solution_nx_graph: nx.DiGraph, labels:napari.layers.labels.labels.Labels) -> pd.DataFrame:
    """
    Extract the information of individual tracks required for constructing the pyqtgraph plot. Follows the same logic as the relabel_segmentation
    function from the Motile toolbox.

    Args:
        solution_nx_graph (nx.DiGraph): NetworkX graph with the solution to use
            for relabeling. Nodes not in the graph will be removed from segmentation.
            Original segmentation IDs and hypothesis IDs have to be stored in the graph
            so we can map them back.
        labels (napari.layers.labels.labels.Labels): the labels layer to which the tracking solution belongs. 
            It is used to extract the corresponding label color for the nodes and edges.        

    Returns:
        List: pd.DataFrame with columns 't', 'node_id', 'track_id', 'color', 'x', 'y', ('z'), 'index', 'parent_id', and 'parent_track_id', 
        containing all information needed to construct the pyqtgraph plot. 
    """

    track_list = []
    counter = 0
    id_counter = 1
    parent_mapping = []

    # Identify parent nodes (nodes with more than one child)
    parent_nodes = [n for (n, d) in solution_nx_graph.out_degree() if d > 1]

    # Make a copy of the graph and remove outgoing edges from parent nodes to isolate tracks
    soln_copy = solution_nx_graph.copy()
    for parent_node in parent_nodes:
        out_edges = solution_nx_graph.out_edges(parent_node)
        soln_copy.remove_edges_from(out_edges)

    # Process each weakly connected component as a separate track
    for node_set in nx.weakly_connected_components(soln_copy):
        # Sort nodes in each weakly connected component by their time attribute to ensure correct order
        sorted_nodes = sorted(node_set, key=lambda node: solution_nx_graph.nodes[node][NodeAttr.TIME.value])
        parent_track_id = None
        for node in sorted_nodes:
            node_data = solution_nx_graph.nodes[node]
            pos = node_data[NodeAttr.POS.value]

            track_dict = {
                't': node_data[NodeAttr.TIME.value],
                'node_id': node,
                'track_id': id_counter,
                'color': labels.colormap.map(id_counter) * 255,
                'x': pos[-1],
                'y': pos[-2],
                'index': counter,
                'parent_id': 0,
                'parent_track_id': 0
            }

            if len(pos) == 3:
                track_dict['z'] = pos[0]

            # Determine parent_id and parent_track_id
            predecessors = list(solution_nx_graph.predecessors(node))
            if predecessors:
                parent_id = predecessors[0]  # There should be only one predecessor in a lineage tree
                track_dict['parent_id'] = parent_id
                if parent_track_id is None: 
                    parent_track_id = [node['track_id'] for node in track_list if node['node_id'] == parent_id][0]
                track_dict['parent_track_id'] = parent_track_id

            else:
                parent_track_id = 0
                track_dict['parent_id'] = 0
                track_dict['parent_track_id'] = parent_track_id
            
            track_list.append(track_dict)
            counter += 1

        parent_mapping.append({'track_id': id_counter, 'parent_track_id': parent_track_id})
        id_counter += 1

    x_axis_order = sort_track_ids(parent_mapping)

    for node in track_list: 
        node['x_axis_pos'] = x_axis_order.index(node['track_id'])
   
    return pd.DataFrame(track_list)

def sort_track_ids(track_list: List[Dict]) -> List[Dict]:
    """
    Sort track IDs such to maintain left-first order in the tree formed by parent-child relationships.
    Used to determine the x-axis order of the tree plot.

    Args:
        track_list (list): List of dictionaries with 'track_id' and 'parent_track_id'.

    Returns:
        list: Ordered list of track IDs for the x-axis.
    """
    
    roots = [node['track_id'] for node in track_list if node['parent_track_id'] == 0]
    x_axis_order = [l for l in roots]

    # Find the children of each of the starting points, and work down the tree.
    while len(roots) > 0:
        children_list = []
        for track_id in roots:
            children = [node['track_id'] for node in track_list if node['parent_track_id'] == track_id]
            for i, c in enumerate(children):
                [children_list.append(c)]
                x_axis_order.insert(x_axis_order.index(track_id) + i, c)
        roots = children_list

    return x_axis_order

class LineageTreeWidget(QWidget):
    """Interactive pyqtgraph based lineage tree widget class.
    """

    def __init__(self, viewer):
        super().__init__()

        self.viewer = viewer
        self.tree_widget = pg.PlotWidget()
        self.tree_widget.setTitle('Lineage Tree')
        self.tree_widget.setLabel('left', text='Time Point')
        self.tree_widget.getAxis('bottom').setStyle(showValues=False)
        self.g = pg.GraphItem()
        self.g.scatter.sigClicked.connect(self._on_click)
        self.tree_widget.addItem(self.g)
        
        self.selected = []

        main_layout = QHBoxLayout()
        main_layout.addWidget(self.tree_widget)
        self.setLayout(main_layout)

    def _update(self, tracks:nx.DiGraph, labels:napari.layers.labels.labels.Labels) -> None:
        """Redraw the pyqtgraph object with the new tracking graph"""

        self.track_df = extract_sorted_tracks(tracks, labels)
        self.labels = labels
        self.labels.opacity = 1
        
        # add callback to clicking on the labels layer to select cells in the pyqtgraph 
        @self.labels.mouse_drag_callbacks.append
        def click(layer, event):
            if event.type == 'mouse_press':  # Check if the event is a mouse press event
                position = event.position
                value = layer.get_value(position,
                    view_direction=event.view_direction,
                    dims_displayed=event.dims_displayed,
                    world=True)
                node_df = self.track_df[(self.track_df['t'] == int(position[0])) & (self.track_df['track_id'] == int(value))]
                if not node_df.empty:
                    modifiers = event.modifiers
                    if isinstance(event.modifiers, tuple):
                        # Convert tuple to Qt.KeyboardModifiers
                        modifiers = self._normalize_modifiers(event.modifiers)
                    self._select_node(node_df, modifiers)
                     
        # create a color dictionary to manipulate opacity of label colors, depending on whether they are currently selected
        self.label_color_dict = self._create_label_color_dict()    

        pos = []
        pos_colors = []
        adj = []
        adj_colors = []

        for index, node in self.track_df.iterrows():      
            pos.append([node['x_axis_pos'], node['t']])
            pos_colors.append(node['color'])               
            parent = node['parent_id']
            if parent != 0:
                parent_df = self.track_df[self.track_df['node_id'] == parent]
                if not parent_df.empty:
                    parent_dict = parent_df.iloc[0]
                    adj.append([parent_dict['index'], node['index']])
                    adj_colors.append(parent_dict['color'].tolist() + [255, 1])
            
        self.pos = np.array(pos)
        self.adj = np.array(adj)
        self.symbols = ['o'] * len(pos)
        self.symbolBrush = np.array(pos_colors)
        self.pen = np.array(adj_colors)
        self.size = np.array([8] * len(pos))

        if len(self.pos) > 0:           
            self.g.setData(pos=self.pos, adj=self.adj, symbols = self.symbols, symbolBrush = self.symbolBrush, size = self.size, pen = self.pen)
        else: 
            self.g.scatter.clear()

    def _on_click(self, item, points: np.ndarray, ev: QMouseEvent) -> None:
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

        # Update viewer step
        step = list(self.viewer.dims.current_step)
        step[0] = node['t']
        
        # Check for 'z' key and update step if exists
        if 'z' in node.keys():
            z = node['z']
            step[1] = int(z)
        
        self.viewer.dims.current_step = step
        self.labels.selected_label = node['track_id']
        
        # Update the graph
        size = self.size.copy()
        size[node['index']] = 13

        # if self.selected already contains another node and the user used SHIFT, add one
        if modifiers == pg.QtCore.Qt.ShiftModifier and len(self.selected) == 1:
            size[self.selected[0]['index']] = 13
            self.selected.append(node)
        else: 
            self.selected = [node]
                                                    
        self.g.setData(pos=self.pos, adj=self.adj, symbolBrush = self.symbolBrush, size = size, symbols = self.symbols, pen = self.pen)

        self._update_label_cmap()

    def _create_label_color_dict(self) -> Dict:
        """Extract the label colors and set opacity to 0.5 to highlight only the selected cell [to be updated with a better highlighting method]"""
        
        color_dict_rgb = {None: (0.0, 0.0, 0.0, 0.0)}

        # Iterate over unique labels
        for label in self.track_df['track_id'].unique():
            color = list(to_rgba(self.labels.get_color(label)))
            color[-1] = 0.5  # Set opacity to 0.5        
            color_dict_rgb[label] = color

        return color_dict_rgb      
    
    def _update_label_cmap(self) -> None:
        """Set the opacity to full for track_ids of selected nodes [to be updated with a better highlighting method, bounding box?]"""
    
        color_dict_rgb = copy.deepcopy(self.label_color_dict)
        selected_labels  = [node['track_id'] for node in self.selected]
        for label in selected_labels:
            color_dict_rgb[label][-1] = 1 # set opacity to full
        self.labels.colormap = DirectLabelColormap(color_dict=color_dict_rgb)

    def _normalize_modifiers(self, modifiers):
        """Normalize the event modifiers to Qt.KeyboardModifiers."""

        if isinstance(modifiers, tuple):
            # Convert to Qt.KeyboardModifiers
            qt_modifiers = Qt.KeyboardModifiers()
            if 'Shift' in modifiers:
                qt_modifiers |= Qt.ShiftModifier
            if 'Ctrl' in modifiers or 'Control' in modifiers:
                qt_modifiers |= Qt.ControlModifier
            if 'Alt' in modifiers:
                qt_modifiers |= Qt.AltModifier
            if 'Meta' in modifiers:
                qt_modifiers |= Qt.MetaModifier
            return qt_modifiers
        return modifiers
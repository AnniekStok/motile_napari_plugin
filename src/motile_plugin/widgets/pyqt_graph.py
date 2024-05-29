import napari.layers

import numpy            as np
import pyqtgraph        as pg
import copy 

from qtpy.QtWidgets     import QHBoxLayout, QWidget
from typing             import List, Dict
from napari.utils       import DirectLabelColormap
from matplotlib.colors  import to_rgba
    
import networkx as nx
from motile_toolbox.candidate_graph import NodeAttr

def extract_sorted_tracks(solution_nx_graph: nx.DiGraph, labels:napari.layers.labels.labels.Labels) -> List[Dict]:
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
        List: List of dictionaries with keys 't', 'node_id', 'track_id', 'color', 'x', 'y', ('z'), 'index', 'parent_id', and 'parent_track_id', 
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
            track_dict = {}
            time_frame = solution_nx_graph.nodes[node][NodeAttr.TIME.value]
            pos = solution_nx_graph.nodes[node][NodeAttr.POS.value]

            track_dict['t'] = time_frame
            track_dict['node_id'] = node
            track_dict['track_id'] = id_counter
            track_dict['color'] = labels.colormap.map(id_counter) * 255
            track_dict['x'] = pos[-1]
            track_dict['y'] = pos[-2]
            if len(pos) == 3:
                track_dict['z'] = pos[0]               
            track_dict['index'] = counter

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

    x_axis_order = determine_label_plot_order(parent_mapping)

    for node in track_list: 
        node['x_axis_pos'] = x_axis_order.index(node['track_id'])
    
    return track_list

def determine_label_plot_order(track_list: List[Dict]) -> List[Dict]:
    """Determines the y-axis order of the tree plot, from the starting points downward"""
    
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
        self.selected_ids = []

        main_layout = QHBoxLayout()
        main_layout.addWidget(self.tree_widget)
        self.setLayout(main_layout)

    def _on_click(self, item, points: np.ndarray, ev) -> None:
        """Highlight and print the information about the currently selected node"""

        # if already two objects were selected, reset self.selected so that self.selected does not get a length of 3
        if len(self.selected) == 2:
            self.selected = []
            self.selected_ids = []
        modifiers = ev.modifiers()

        clicked_point = points[0]
        pos = clicked_point.pos()  # Get the coordinates of the clicked point
        index = clicked_point.index()  # Get the index of the clicked point

        track_id = [node['track_id'] for node in self.track_list if node['index'] == index][0]
        id = [node['node_id'] for node in self.track_list if node['index'] == index][0]
        t = [node['t'] for node in self.track_list if node['index'] == index][0]
               
        print('Node Index:', index)
        print('Node Coordinates:', pos)
        print('this is the track id', track_id)
        print('this is its id', id)
        print('time point', t)
        
        # update the viewer but leave the plot at the current time point
        step = list(self.viewer.dims.current_step)
        step[0] = t
        if 'z' in self.track_list[0].keys():
            z = [node['z'] for node in self.track_list if node['index'] == index][0]
            step[1] = int(z)
        self.viewer.dims.current_step = step
        self.labels.selected_label = track_id
                
        # update the graph
        size = self.size.copy()
        size[index] = 13
       
        if modifiers == pg.QtCore.Qt.ShiftModifier and len(self.selected) == 1:
            size[self.selected[0]] = 13
            self.selected.append(index)
            self.selected_ids.append(id)
        else: 
            self.selected = [index]    
            self.selected_ids = [id]    
                       
        self.g.setData(pos=self.pos, adj=self.adj, symbolBrush = self.symbolBrush, size = size, symbols = self.symbols, pen = self.pen)

        self._update_label_cmap()

    def _create_label_color_dict(self) -> Dict:
        """Extract the label colors and set opacity to 0.5 to highlight only the selected cell [to be updated with a better highlighting method]"""
        
        color_dict_rgb = {None: (0.0, 0.0, 0.0, 0.0)}

        for label in np.unique([node['track_id'] for node in self.track_list]):
            color = list(to_rgba(self.labels.get_color(label)))   
            color[-1] = 0.5 # set opacity to 0.5        
            color_dict_rgb[label] = color

        return color_dict_rgb      
    
    def _update_label_cmap(self) -> None:
        """Set the opacity to full for track_ids of selected nodes [to be updated with a better highlighting method, bounding box?]"""
    
        color_dict_rgb = copy.deepcopy(self.label_color_dict)
        selected_labels  = [node['track_id'] for node in self.track_list if node['node_id'] in self.selected_ids]
        for label in selected_labels:
            color_dict_rgb[label][-1] = 1 # set opacity to full
        self.labels.colormap = DirectLabelColormap(color_dict=color_dict_rgb)

    def _update(self, tracks:nx.DiGraph, labels:napari.layers.labels.labels.Labels) -> None:
        """Redraw the pyqtgraph object with the new tracking graph"""

        self.track_list = extract_sorted_tracks(tracks, labels)
        self.labels = labels
        self.labels.opacity = 1
        self.label_color_dict = self._create_label_color_dict()    

        pos = []
        pos_colors = []
        adj = []
        adj_colors = []

        for node in self.track_list:      
            pos.append([node['x_axis_pos'], node['t']])
            pos_colors.append(node['color'])               
            parent = node['parent_id']
            if parent != 0:
                parent_dict_list = [n for n in self.track_list if n['node_id'] == parent]
                if len(parent_dict_list) > 0:
                    parent_dict = parent_dict_list[0]
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
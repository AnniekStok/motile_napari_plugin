import napari.layers
import pandas                       as pd 
import networkx                     as nx
from typing                         import List, Dict, Tuple, Callable, Any
from napari                         import Viewer
from qtpy.QtWidgets                 import QPushButton
from PyQt5.QtCore                   import Qt


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

def get_existing_pins(solution_nx_graph: nx.DiGraph) -> List[Tuple[str, str]]:
    """Extract a list of the pinned edges from this run.
    
    Args: 
        solution_nx_graph (nx.DiGraph): NetworkX graph with the solution to use
        for relabeling. 
    
    Returns:
        list: List of tuples containing the node_ids for pinned edges (only those with value True, since the ones with value False will not be visible in the graph).

    """

    pinned_edges = []
    for u, v, data in solution_nx_graph.edges(data=True):
        if data.get('pinned') is True:
            pinned_edges.append((u, v))
    
    return pinned_edges

def get_existing_forks_endpoints(solution_nx_graph: nx.DiGraph) -> Tuple[List[str], List[str]]:
    """Extract a list with fork (dividing) nodes and endpoint (dead) nodes
    
    Args: 
        solution_nx_graph (nx.DiGraph): NetworkX graph with the solution to use
        for relabeling. 
    
    Returns:
        tuple: Tuple of lists containing the node_ids for fork and endpoint nodes.

    """

    forks = []
    endpoints = []
    for n, data in solution_nx_graph.nodes(data=True):
        if data.get('fork') is True:
            forks.append(n)
        if data.get('endpoint') is True:
            endpoints.append(n)
    
    return forks, endpoints

def bind_key_with_condition(viewer: Viewer, key: str, button: QPushButton, target_function: Callable[[Any], None]) -> None:
    """Binds a key to a function, only triggering if the button is enabled."""
    
    @viewer.bind_key(key, overwrite = True)
    def wrapped_function(event=None):
        if button.isEnabled():
            target_function()

def normalize_modifiers(modifiers):
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
import napari.layers

import numpy            as np
import networkx         as nx
from functools          import partial
from qtpy.QtWidgets     import QHBoxLayout, QWidget, QVBoxLayout
from typing             import List, Tuple

from .custom_table_widget       import TableWidget
from .volume_mode_widget        import VolumeModeWidget
from .tree_widget               import TreeWidget
from .edit_button_widget        import AnnotationButtons
from .mode_selection_widget     import SelectMode
from ..utils.tree_widget_utils  import bind_key_with_condition, extract_sorted_tracks, get_existing_pins, get_existing_forks_endpoints, create_colormap, create_selection_label_cmap, create_label_color_dict, extract_lineage_tree
from ..utils.node_selection     import NodeSelectionList


class TrackAnnotationWidget(QWidget):
    """Widget for interactive annotation of tracking results. 
    Constructs pyqtgraph-based lineage tree visualization, annotation buttons, and table to append annotations to. 
    """

    def __init__(self, viewer):
        super().__init__()

        # initialize lists for tracking node selection, and markings for division points (forks) and endpoints
        self.viewer = viewer
        self.viewer.dims.events.current_step.connect(self._check_dim_changed)
        
        self.selected_nodes = NodeSelectionList()   
        self.selected_nodes.list_updated.connect(self._set_selected_node)
        self.selected_nodes.list_updated.connect(self._set_current_step)  
        self.selected_nodes.list_updated.connect(self._highlight_selected_nodes)  
        self.forks = []
        self.endpoints = []
        self.base_label_color_dict = None
        self.mode = 'selection'

        # construct tree widget and buttons that reactively respond to changes in the selection of nodes
        self.tree_widget = TreeWidget(self.selected_nodes, self.forks, self.endpoints)
        self.mode_widget = SelectMode()
        self.mode_widget.mode_updated.connect(self._update_mode)
        self.edit_buttons = AnnotationButtons(self.selected_nodes)
        self.edit_buttons.node_edit.connect(self.tree_widget._edit_node)
        self.edit_buttons.edge_edit.connect(self._edit_edge)

        mode_button_layout = QVBoxLayout()
        mode_button_layout.addWidget(self.mode_widget)
        mode_button_layout.addWidget(self.edit_buttons)
       
        # Add a table widget to keep accumulate actions before triggering the solver
        self.table_widget = TableWidget(data={"Source": [], "Target": [], "Action": [], "Color1": [], "Color2": []}, displayed_columns=["Source", "Target", "Action"])
        self.table_widget.setMaximumWidth(200)
        self.table_widget.valueClicked.connect(self._on_table_clicked)

        # For highlighting selected labels
        self.selected_labels_layer = None

        # Used for 3D visualization only
        self.volume_viewer = None
        
        # Add widgets to layout
        self.layout = QHBoxLayout()
        self.layout.addLayout(mode_button_layout)
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
   
    def _set_current_step(self) -> None: 
        """Adjust the current_step of the viewer to jump to the last item of the selected_nodes list"""

        if len(self.selected_nodes) > 0: 
            node = self.selected_nodes[-1]

            # Check for 'z' key and update step if exists
            step = list(self.viewer.dims.current_step)
            step[0] = node['t']
            if 'z' in node.keys():
                z = node['z']
                step[1] = int(z)       
            self.viewer.dims.current_step = step

            # if the viewer is in 3D plane mode, also adjust the plane we are looking at
            if self.volume_viewer is not None: 
                if self.volume_viewer.mode == 'plane':
                    self.volume_viewer._set_plane_value(pos=(int(z), int(node['y']), int(node['x'])))
       
    def _check_dim_changed(self) -> None: 
        """Checks if the time dimensions was updated, and if so, call the _highlight_selected_nodes fucntion"""

        if self.viewer.dims.last_used == 0 and self.mode == 'selection': 
            self._highlight_selected_nodes()

    def _update_mode(self, mode:str) -> None: 
        """Update the display mode of the selected_labels layer"""

        self.mode = mode
        self._highlight_selected_nodes()

    def _set_selected_node(self) -> None:
        """Make the selected node the active label in self.labels"""

        if len(self.selected_nodes) > 0:
            self.labels.selected_label = self.selected_nodes[-1]['track_id']
        else: 
            self.labels.selected_label = 0

    def _highlight_selected_nodes(self) -> None:
        """Highlights labels in the selected_labels layer by changing the opacity"""

        if self.base_label_color_dict is not None:           
            if self.mode == 'selection':
                t = self.viewer.dims.current_step[0]
                nodes = [node for node in self.selected_nodes if node['t'] == t]
                visible = [node['track_id'] for node in nodes]
            elif self.mode == 'track':
                visible = [self.labels.selected_label]  
            elif self.mode == 'lineage':
                node_id = self.track_df.loc[self.track_df['track_id'] == self.labels.selected_label, 'node_id'].iloc[0]
                lineage_nodes = extract_lineage_tree(self.tracks, node_id)
                visible = self.track_df[self.track_df['node_id'].isin(lineage_nodes)]['track_id'].unique()
            else: 
                if self.volume_viewer is not None: 
                    if self.volume_viewer.mode == 'plane':
                        if self.volume_viewer.z_plane_btn.isChecked():
                            slider_position = self.volume_viewer.z_plane_slider.value()
                            visible = np.unique(self.labels.data[self.viewer.dims.current_step[0], slider_position, :, :])

                        elif self.volume_viewer.y_plane_btn.isChecked():
                            slider_position = self.volume_viewer.y_plane_slider.value()
                            visible = np.unique(self.labels.data[self.viewer.dims.current_step[0], :, slider_position, :])

                        elif self.volume_viewer.x_plane_btn.isChecked():
                            slider_position = self.volume_viewer.x_plane_slider.value()
                            visible = np.unique(self.labels.data[self.viewer.dims.current_step[0], :, :, slider_position])
                    else:
                        visible = np.unique(self.labels.data[self.viewer.dims.current_step[0]])
                else:
                    visible = np.unique(self.labels.data[self.viewer.dims.current_step[0]])
                   
            colormap = create_selection_label_cmap(self.base_label_color_dict, visible = visible)           
            self.selected_labels_layer.colormap = colormap
            self.selected_labels_layer.editable = False
            self.selected_labels_layer.mouse_pan = False
            self.selected_labels_layer.mouse_zoom = False
            self.selected_labels_layer.opacity = 0.9     
           
    def _on_table_clicked(self, value: str) -> None:
        """Jump to the node selected by the user in the table"""
        
        if value not in ["Add", "Break"]:
            node_df = self.track_df[self.track_df['node_id'] == value]
            if not node_df.empty:
                node = node_df.iloc[0].to_dict()  # Convert the filtered result to a dictionary
                self.selected_nodes.append(node)
           
    def _edit_edge(self, edit: str) -> None:
        """Add a new action (make or break an edge) to the table"""

        node1 = self.selected_nodes[0]
        node2 = self.selected_nodes[1]

        self.table_widget._add_row({"Source": node1['node_id'], "Target": node2['node_id'], "Action": edit, "Color1": [int(c) for c in node1['color'][:3]], "Color2": [int(c) for c in node2['color'][:3]]})
        self.selected_nodes.reset()   
    
    def _update(self, graph: nx.DiGraph, labels: napari.layers.Labels, tracks_layer: napari.layers.Tracks) -> None:
        """Takes the tracks and labels data generated by Motile and uses it update the annotator widget to display results and allow interactive tracking"""
      
        # construct track_df dataframe holding all information needed to update the pyqtgraph
        self.tracks = graph
        self.track_df = extract_sorted_tracks(graph, labels)

        # retrieve existing pins, forks and endpoints from the track data
        self.pins = get_existing_pins(self.tracks)
        self.forks, self.endpoints = get_existing_forks_endpoints(self.tracks)

        # call the update function on the tree widget        
        self.tree_widget._update(self.track_df, self.pins, self.forks, self.endpoints)

        # update label visualization (additional labels layer will be created to highlight the selected labels)
        self.labels = labels
        self.labels.opacity = 0.6
        self.base_label_color_dict = create_label_color_dict(labels=self.track_df['track_id'].unique(), labels_layer=self.labels)

        # update the tracks_layer with the same colors as the labels layer
        self.tracks_layer = tracks_layer
        colormap_name = 'track_colors'
        create_colormap(tracked_labels=self.labels, name=colormap_name) # it still throws an error even though the colormap is correctly displayed
        self.tracks_layer.colormap = colormap_name

        # create additional labels layer for highlighting/visualization purposes only
        if self.selected_labels_layer is not None: 
            self.viewer.layers.remove(self.selected_labels_layer)
        self.selected_labels_layer = self.viewer.add_labels(self.labels.data, name = "Selected Labels")
        self.selected_labels_layer.editable = False
        self.selected_labels_layer.mouse_pan = False
        self.selected_labels_layer.mouse_zoom = False
        self.selected_labels_layer.opacity = 0.9
      
        # If the data is 3D (+time), add a points layer and 3D plane view option. Points have to be used for selections, 
        # because direct label selection is not possible in plane mode (you end up selecting the invisible labels on top of it that are only visible in volume mode)
        if len(self.labels.data.shape) == 4: 
            
            self.selected_labels_layer.blending = 'translucent_no_depth'
            self.selected_labels_layer.depiction = 'volume'
            colormap = create_selection_label_cmap(self.base_label_color_dict, visible = [])           
            self.selected_labels_layer.colormap = colormap
            self.viewer.dims.ndisplay = 3

            # check if widget exists already from previous run
            if self.volume_viewer is None: 
                self.volume_viewer = VolumeModeWidget(
                    self.viewer, 
                    self.track_df,
                    self.labels, 
                    self.tracks_layer,
                    self.selected_labels_layer, 
                    self.selected_nodes,
                )
                self.layout.insertWidget(0, self.volume_viewer)
            else: 
                self.volume_viewer._update(
                    self.viewer, 
                    self.track_df,
                    self.labels, 
                    self.tracks_layer,
                    self.selected_labels_layer, 
                    self.selected_nodes,
                )
        else: 
            # add callback to clicking directly on the labels layer to select cells in the pyqtgraph 
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
                        node = node_df.iloc[0].to_dict()  # Convert the filtered result to a dictionary
                        self.selected_nodes.append(node, event.modifiers)
            self.viewer.layers.selection.clear()
            self.viewer.layers.selection.add(self.labels)

        # Add key bindings for faster annotation        
        bind_key_with_condition(self.viewer, 'A', self.edit_buttons.connect_btn, partial(self._edit_edge, edit='Add'))
        bind_key_with_condition(self.viewer, 'B', self.edit_buttons.break_btn, partial(self._edit_edge, edit='Break'))
        bind_key_with_condition(self.viewer, 'F', self.edit_buttons.fork_btn, partial(self.tree_widget._edit_node, edit='Fork'))
        bind_key_with_condition(self.viewer, 'C', self.edit_buttons.close_btn, partial(self.tree_widget._edit_node, edit='Close'))
        bind_key_with_condition(self.viewer, 'R', self.edit_buttons.reset_btn, partial(self.tree_widget._edit_node, edit='Reset'))
from functools import partial
from typing import List, Tuple

import napari.layers
import networkx as nx
from PyQt5.QtCore import Qt
from qtpy.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ..utils.node_selection import NodeSelectionList
from ..utils.point_tracker import PointTracker
from ..utils.track_data import TrackData
from ..utils.tree_widget_utils import (
    bind_key_with_condition,
    create_colormap,
    create_label_color_dict,
    create_selection_label_cmap,
    extract_lineage_tree,
    extract_sorted_tracks,
    get_existing_pins,
)
from .custom_table_widget import TableWidget
from .display_mode_selection_widget import SelectMode
from .edit_button_widget import AnnotationButtons
from .tree_widget import TreeWidget
from .volume_mode_widget import VolumeModeWidget


class TrackAnnotationWidget(QWidget):
    """Widget for interactive annotation of tracking results.
    Constructs pyqtgraph-based lineage tree visualization, annotation buttons, and table to append annotations to.
    """

    def __init__(self, viewer):
        super().__init__()

        self.count = 0
        # initialize lists for tracking node selection, and markings for division points (forks) and endpoints
        self.viewer = viewer
        self.viewer.dims.events.current_step.connect(self._check_dim_changed)

        self.track_data = TrackData()
        self.track_data.data_updated.connect(self._user_update)

        self.point_tracker = None

        self.selected_nodes = NodeSelectionList()
        self.selected_nodes.list_updated.connect(self._set_selected_node)
        self.selected_nodes.list_updated.connect(self._set_current_step)
        self.selected_nodes.list_updated.connect(
            self._highlight_selected_nodes
        )
        self.base_label_color_dict = None
        self.mode = "selection"

        # construct tree widget and buttons that reactively respond to changes in the selection of nodes
        self.tree_widget = TreeWidget(self.selected_nodes, self.track_data)

        # add widget for selecting the display mode
        self.mode_widget = SelectMode()
        self.mode_widget.display_updated.connect(
            self._highlight_selected_nodes
        )
        self.mode_widget.reset_display.connect(self._reset_display)

        @viewer.bind_key("T")
        def select_next(viewer):
            self.mode_widget._select_next_display_option()

        self.edit_buttons = AnnotationButtons(self.selected_nodes)
        self.edit_buttons.node_edit.connect(self.tree_widget._edit_node)
        self.edit_buttons.edge_edit.connect(self._edit_edge)

        mode_button_scroll_area = QScrollArea()
        mode_button_layout = QVBoxLayout()
        mode_button_layout.addWidget(self.mode_widget)
        mode_button_layout.addWidget(self.edit_buttons)
        mode_button_widget = QWidget()
        mode_button_widget.setLayout(mode_button_layout)
        mode_button_scroll_area.setWidget(mode_button_widget)
        mode_button_scroll_area.setMaximumWidth(230)

        # Add a table widget to keep accumulate actions before triggering the solver
        table_scroll_area = QScrollArea()
        self.table_widget = TableWidget(
            data={
                "Source": [],
                "Target": [],
                "Action": [],
                "Color1": [],
                "Color2": [],
            },
            displayed_columns=["Source", "Target", "Action"],
        )
        self.table_widget.valueClicked.connect(self._on_table_clicked)
        table_scroll_area.setWidget(self.table_widget)
        table_scroll_area.setMaximumWidth(180)
        table_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # For highlighting selected labels
        self.selected_labels_layer = None

        # Used for 3D visualization only
        self.volume_viewer = None

        # Add widgets to layout
        self.layout = QHBoxLayout()
        self.layout.addWidget(mode_button_scroll_area)
        self.layout.addWidget(self.tree_widget)
        self.layout.addWidget(table_scroll_area)
        self.setLayout(self.layout)
        self.setMinimumHeight(300)

    def _get_pins(self) -> List[Tuple[str, str, bool]]:
        """Extracts the edge edits ('Add', 'Break') from the table, to be used to pin edges as True or False"""

        edits = self.table_widget._data  # get the data from the table
        if not len(edits) > 0:
            return None
        else:
            pins = []
            for i in range(len(edits["Source"])):
                source = edits["Source"][i]
                target = edits["Target"][i]
                action = edits["Action"][i]

                if action == "Add":
                    pins.append((source, target, True))
                elif action == "Break":
                    pins.append((source, target, False))

            return pins

    def _set_current_step(self) -> None:
        """Adjust the current_step of the viewer to jump to the last item of the selected_nodes list"""

        self.viewer.dims.events.current_step.disconnect(
            self._check_dim_changed
        )  # disconnect listening to this event to prevent double call to display update
        if len(self.selected_nodes) > 0:
            node = self.selected_nodes[-1]

            # Check for 'z' key and update step if exists
            step = list(self.viewer.dims.current_step)
            step[0] = node["t"]
            if "z" in node:
                z = node["z"]
                step[1] = int(z)
            self.viewer.dims.current_step = step

            # if the viewer is in 3D plane mode, also adjust the plane we are looking at
            if (
                self.volume_viewer is not None
                and self.volume_viewer.mode == "plane"
            ):
                self.volume_viewer._set_plane_value(
                    pos=(int(z), int(node["y"]), int(node["x"]))
                )
        self.viewer.dims.events.current_step.connect(self._check_dim_changed)

    def _check_dim_changed(self) -> None:
        """Checks if the time dimensions was updated, and if so, call the _highlight_selected_nodes function"""

        if self.viewer.dims.last_used == 0 and self.mode in [
            "selection",
            "edits",
        ]:
            self._highlight_selected_nodes()

    def _set_selected_node(self) -> None:
        """Make the selected node the active label in self.labels"""

        if len(self.selected_nodes) > 0:
            self.labels.selected_label = self.selected_nodes[-1]["track_id"]
        else:
            self.labels.selected_label = 0

    def _reset_display(self) -> None:
        """Resets the display back to 'all'"""

        if not self.mode_widget.tree_widget_ch.isChecked():
            self.tree_widget._update_display(visible="all")
        if not self.mode_widget.labels_ch.isChecked():
            self.selected_labels_layer.colormap = self.base_label_colormap
        if not self.mode_widget.points_ch.isChecked():
            self.point_tracker._update_display(visible="all")

    def _highlight_selected_nodes(self) -> None:
        """Highlights labels in the selected_labels layer by changing the opacity"""

        self.count += 1
        index = self.mode_widget.selection_combo.currentIndex()
        if index == 0:
            self.mode = "selection"
        elif index == 1:
            self.mode = "track"
        elif index == 2:
            self.mode = "lineage"
        else:
            self.mode = "edits"

        if any(
            (
                self.mode_widget.tree_widget_ch.isChecked(),
                self.mode_widget.labels_ch.isChecked(),
                self.mode_widget.points_ch.isChecked(),
            )
        ):
            visible = []
            if self.mode == "selection":
                visible = [node["node_id"] for node in self.selected_nodes]
            elif self.mode == "track":
                if len(self.selected_nodes) > 0:
                    visible = self.track_data.df[
                        (
                            self.track_data.df["track_id"]
                            == self.selected_nodes[0]["track_id"]
                        )
                    ][
                        "node_id"
                    ].tolist()  # take all the node_ids that have the same track_id as the first node from the selected nodes
            elif self.mode == "lineage":
                nodes = [node["node_id"] for node in self.selected_nodes]
                if len(nodes) > 0:
                    visible = extract_lineage_tree(self.tracks, nodes[0])
            else:
                visible = self.track_data.df[self.track_data.df["annotated"]][
                    "node_id"
                ].tolist()
                for pin in self._get_pins():
                    visible.append(pin[0])
                    visible.append(pin[1])

            # find out which widgets/layers to change the display for
            if self.mode_widget.tree_widget_ch.isChecked():
                self.tree_widget._update_display(visible)
            if self.mode_widget.labels_ch.isChecked():
                self._set_label_colormap(visible)
            if self.mode_widget.points_ch.isChecked():
                self.point_tracker._update_display(visible)

    def _set_label_colormap(self, visible):
        """updates the colormap of the selected_labels_layer based on the current selection"""

        if self.mode == "selection" or self.mode == "edits":
            # first check if the nodes in 'visible' are in the current time point
            t = self.viewer.dims.current_step[0]
            track_ids = self.track_data.df[
                self.track_data.df["node_id"].isin(visible)
                & (self.track_data.df["t"] == t)
            ]["track_id"].tolist()
        else:
            track_ids = self.track_data.df[
                self.track_data.df["node_id"].isin(visible)
            ]["track_id"].tolist()

        # colormap can only be adjusted for label values, not for individual objects. Therefore, change the colormap depending on the time point as well.
        if self.base_label_color_dict is not None:
            colormap = create_selection_label_cmap(
                self.base_label_color_dict, visible=track_ids
            )
            self.selected_labels_layer.colormap = colormap

        self.selected_labels_layer.editable = False
        self.selected_labels_layer.mouse_pan = False
        self.selected_labels_layer.mouse_zoom = False
        self.selected_labels_layer.opacity = 0.9

    def _on_table_clicked(self, value: str) -> None:
        """Jump to the node selected by the user in the table"""

        if value not in ["Add", "Break"]:
            node_df = self.track_data.df[
                self.track_data.df["node_id"] == value
            ]
            if not node_df.empty:
                node = node_df.iloc[
                    0
                ].to_dict()  # Convert the filtered result to a dictionary
                self.selected_nodes.append(node)

    def _user_update(self, node_id: str, edit: str):
        """Forward the user edit to the points layer"""

        if self.point_tracker is not None:
            self.point_tracker._user_update(node_id, edit)

    def _edit_edge(self, edit: str) -> None:
        """Add a new action (make or break an edge) to the table"""

        node1 = self.selected_nodes[0]
        node2 = self.selected_nodes[1]

        self.table_widget._add_row(
            {
                "Source": node1["node_id"],
                "Target": node2["node_id"],
                "Action": edit,
                "Color1": [int(c) for c in node1["color"][:3]],
                "Color2": [int(c) for c in node2["color"][:3]],
            }
        )
        self.selected_nodes.reset()

    def _update(
        self,
        graph: nx.DiGraph,
        labels: napari.layers.Labels,
        tracks_layer: napari.layers.Tracks,
    ) -> None:
        """Takes the tracks and labels data generated by Motile and uses it update the annotator widget to display results and allow interactive tracking"""

        # construct track_df dataframe holding all information needed to update the pyqtgraph
        self.tracks = graph
        self.track_data._update_data(extract_sorted_tracks(graph, labels))

        # retrieve existing pins, forks and endpoints from the track data
        self.pins = get_existing_pins(self.tracks)

        # call the update function on the tree widget
        self.tree_widget._update(self.pins)

        # update label visualization (additional labels layer will be created to highlight the selected labels)
        self.labels = labels
        self.labels.opacity = 0.6
        self.base_label_color_dict = create_label_color_dict(
            labels=self.track_data.df["track_id"].unique(),
            labels_layer=self.labels,
        )

        self.base_label_colormap = self.labels.colormap

        # update the tracks_layer with the same colors as the labels layer
        self.tracks_layer = tracks_layer
        colormap_name = "track_colors"
        create_colormap(
            tracked_labels=self.labels, name=colormap_name
        )  # it still throws an error even though the colormap is correctly displayed
        self.tracks_layer.colormap = colormap_name

        # create additional labels layer for highlighting/visualization purposes only
        if self.selected_labels_layer is not None:
            self.viewer.layers.remove(self.selected_labels_layer)
        self.selected_labels_layer = self.viewer.add_labels(
            self.labels.data, name="Highlighted Labels"
        )
        self.selected_labels_layer.editable = False
        self.selected_labels_layer.mouse_pan = False
        self.selected_labels_layer.mouse_zoom = False
        self.selected_labels_layer.opacity = 0.9

        # initiate point tracker
        if self.point_tracker is None:
            self.point_tracker = PointTracker(
                self.track_data, self.selected_nodes, self.viewer
            )
        else:
            self.point_tracker._update()

        # If the data is 3D (+time), add a points layer and 3D plane view option. Points have to be used for selections,
        # because direct label selection is not possible in plane mode (you end up selecting the invisible labels on top of it that are only visible in volume mode)
        if len(self.labels.data.shape) == 4:

            self.selected_labels_layer.blending = "translucent_no_depth"
            self.selected_labels_layer.depiction = "volume"
            colormap = create_selection_label_cmap(
                self.base_label_color_dict, visible=[]
            )
            self.selected_labels_layer.colormap = colormap
            self.viewer.dims.ndisplay = 3

            # check if widget exists already from previous run
            if self.volume_viewer is None:
                self.volume_viewer = VolumeModeWidget(
                    self.viewer,
                    self.track_data.df,
                    self.labels,
                    self.tracks_layer,
                    self.selected_labels_layer,
                    self.selected_nodes,
                    self.point_tracker,
                )
                self.layout.insertWidget(0, self.volume_viewer)
            else:
                self.volume_viewer._update(
                    self.viewer,
                    self.track_data.df,
                    self.labels,
                    self.tracks_layer,
                    self.selected_labels_layer,
                    self.selected_nodes,
                )

        # add callback to clicking directly on the labels layer to select cells in the pyqtgraph
        @self.labels.mouse_drag_callbacks.append
        def click(layer, event):
            if event.type == "mouse_press" and not (
                self.viewer.dims.ndisplay == 3 and layer.depiction == "plane"
            ):  # Check if the event is a mouse press event and do not fire in 3D plane mode because this may select invisible objects on top
                position = event.position
                value = layer.get_value(
                    position,
                    view_direction=event.view_direction,
                    dims_displayed=event.dims_displayed,
                    world=True,
                )

                if value is not None:
                    node_df = self.track_data.df[
                        (self.track_data.df["t"] == int(position[0]))
                        & (self.track_data.df["track_id"] == int(value))
                    ]
                    if not node_df.empty:
                        node = node_df.iloc[
                            0
                        ].to_dict()  # Convert the filtered result to a dictionary
                        self.selected_nodes.append(node, event.modifiers)

        self.viewer.layers.selection.clear()
        self.viewer.layers.selection.add(self.labels)

        # Add key bindings for faster annotation
        bind_key_with_condition(
            self.viewer,
            "A",
            self.edit_buttons.connect_btn,
            partial(self._edit_edge, edit="Add"),
        )
        bind_key_with_condition(
            self.viewer,
            "B",
            self.edit_buttons.break_btn,
            partial(self._edit_edge, edit="Break"),
        )
        bind_key_with_condition(
            self.viewer,
            "F",
            self.edit_buttons.fork_btn,
            partial(self.tree_widget._edit_node, edit="Fork"),
        )
        bind_key_with_condition(
            self.viewer,
            "C",
            self.edit_buttons.close_btn,
            partial(self.tree_widget._edit_node, edit="Close"),
        )
        bind_key_with_condition(
            self.viewer,
            "R",
            self.edit_buttons.reset_btn,
            partial(self.tree_widget._edit_node, edit="Reset"),
        )

    def _get_forks_endpoints(self) -> tuple[list[str], list[str]]:
        """Extract the node_ids that have a fork or endpoint annotation"""

        if not self.track_data.df.empty:
            forks = self.track_data.df[
                (self.track_data.df["state"] == "fork")
                & (self.track_data.df["annotated"])
            ]["node_id"].tolist()
            endpoints = self.track_data.df[
                (self.track_data.df["state"] == "endpoint")
                & (self.track_data.df["annotated"])
            ]["node_id"].tolist()
        else:
            forks = []
            endpoints = []

        return forks, endpoints

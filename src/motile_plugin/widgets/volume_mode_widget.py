        
import napari.layers
import copy

import numpy            as np
import pandas           as pd

from qtpy.QtWidgets     import QWidget, QPushButton, QVBoxLayout,QHBoxLayout
from superqt            import QLabeledSlider
from qtpy               import QtCore

from ..utils.point_tracker     import PointTracker
from ..utils.node_selection  import NodeSelectionList
from ..utils.tree_widget_utils import create_selection_colormap

class VolumeModeWidget(QWidget):
    """Widget for extended 3D visualization purposes only, 
    constructs additional layers and allows switching between plane and volume mode.
    """

    def __init__(
            self,
            viewer: napari.Viewer,
            track_df: pd.DataFrame,
            labels: napari.layers.Labels,
            tracks: napari.layers.Tracks,
            selected_labels: napari.layers.Labels, 
            selected_nodes: NodeSelectionList
            ):
        super().__init__()
        
        self.viewer = viewer
        self.track_df = track_df
        self.labels = labels
        self.tracks = tracks
        self.tracks_data = copy.deepcopy(self.tracks.data) # store for later
        self.tracks_props = copy.deepcopy(self.tracks.properties['track_id']) # store for later
        self.selected_labels = selected_labels
        self.selected_nodes = selected_nodes

        self.mode = 'volume'
        self.point_tracker = PointTracker(self.track_df, self.viewer)
        self.point_tracker.points.blending = 'translucent_no_depth'
        self.viewer.layers.selection.clear()
        self.viewer.layers.selection.add(self.point_tracker.points)

        @self.point_tracker.points.mouse_drag_callbacks.append
        def click(layer, event):
            if event.type == 'mouse_press': 
                point_index = layer.get_value(event.position, 
                    view_direction=event.view_direction,
                    dims_displayed=event.dims_displayed,
                    world=True)
                if point_index is not None:                 
                    node_id = layer.properties['node_id'][point_index]
                    node_df = self.track_df[(self.track_df['node_id'] == node_id)]
                    if not node_df.empty:
                        node = node_df.iloc[0].to_dict()  # Convert the filtered result to a dictionary
                        self.selected_nodes.append(node, event.modifiers)

        self.viewer.dims.events.ndisplay.connect(self.on_ndisplay_changed)
        view_mode_widget_layout = QVBoxLayout()
        
        # Add buttons to switch between plane and volume mode
        button_layout = QVBoxLayout()
        
        plane_volume_layout = QHBoxLayout()
        self.plane_btn = QPushButton('Plane')
        self.plane_btn.setEnabled(False)
        self.plane_btn.clicked.connect(self._set_plane_mode)
        self.volume_btn = QPushButton('Volume')
        self.volume_btn.setEnabled(True)
        self.volume_btn.clicked.connect(self._set_volume_mode)
        plane_volume_layout.addWidget(self.plane_btn)
        plane_volume_layout.addWidget(self.volume_btn)

        current_next_layout = QHBoxLayout()
        self.show_current_btn = QPushButton('Show current')
        self.show_current_btn.setEnabled(False)
        self.show_current_btn.clicked.connect(self._show_current)
        self.show_current_next_btn = QPushButton('Show current + next')
        self.show_current_next_btn.setEnabled(True)
        self.show_current_next_btn.clicked.connect(self._show_current_next)
        current_next_layout.addWidget(self.show_current_btn)
        current_next_layout.addWidget(self.show_current_next_btn)

        button_layout.addLayout(plane_volume_layout)
        button_layout.addLayout(current_next_layout)
        
        # Add a plane slider widget for viewing in 3D
        self.plane_slider = QLabeledSlider(QtCore.Qt.Vertical)
        self.plane_slider.setSingleStep(1)
        self.plane_slider.setTickInterval(1)
        self.plane_slider.setValue(0)
        self.plane_slider.setEnabled(False)
        self.plane_slider.valueChanged.connect(self._set_plane)
        self.plane_slider.setMaximumWidth(20)

        view_mode_widget_layout.addLayout(button_layout)
        view_mode_widget_layout.addWidget(self.plane_slider)
        self.setLayout(view_mode_widget_layout)

        self.on_ndisplay_changed()
    
    def _show_current(self):
        """Show only the points for the current time point"""

        self.point_tracker._switch_mode('single')
        self.show_current_btn.setEnabled(False)
        self.show_current_next_btn.setEnabled(True)
        
        if self.mode == 'plane':
            self._set_plane()

    def _show_current_next(self):
        """Show both the points for the current time point and those for the next"""
        
        self.point_tracker._switch_mode('combined')
        self.show_current_btn.setEnabled(True)
        self.show_current_next_btn.setEnabled(False)

        if self.mode == 'plane':
            self._set_plane()


    def _set_plane_mode(self) -> None:
        """Set the mode to plane, enable slider and change depiction to 'plane' for Image and Labels layers"""

        self.mode = 'plane'
        self.plane_btn.setEnabled(False)
        self.volume_btn.setEnabled(True)
        self.plane_slider.setEnabled(True)

        layers = [l for l in self.viewer.layers if isinstance(l, (napari.layers.Labels, napari.layers.Image)) and l != self.selected_labels]
        for layer in layers:
            layer.depiction = 'plane'
            if isinstance(layer, napari.layers.Labels):
                layer.rendering = 'translucent'
        
        self._set_plane()
        
    def _set_volume_mode(self) -> None: 
        """Set the mode to volume, disable slider and change depiction to 'volume' for Image and Labels layers"""

        self.mode = 'volume'
        self.plane_btn.setEnabled(True)
        self.volume_btn.setEnabled(False)
        self.plane_slider.setEnabled(False)

        layers = [l for l in self.viewer.layers if isinstance(l, (napari.layers.Labels, napari.layers.Image)) and l != self.selected_labels]
        for layer in layers:
            layer.depiction = 'volume'
            if isinstance(layer, napari.layers.Labels):
                layer.rendering = 'iso_categorical'
        
        # show all the points in volume mode
        self.point_tracker.points.shown = True

    def on_ndisplay_changed(self) -> None:
        """Update the buttons depending on the display mode of the viewer. Buttons and slider should only be active in 3D mode"""

        if self.viewer.dims.ndisplay == 2: 
            self.plane_btn.setEnabled(False)
            self.volume_btn.setEnabled(False)
            self.plane_slider.setEnabled(False)
        else:
            self.plane_btn.setEnabled(True)
            self.volume_btn.setEnabled(False)
            self.plane_slider.setEnabled(False)
    
    def _set_plane_value(self, value: int) -> None:
        """Set the plane slider to specific value"""

        self.plane_slider.setValue(value)
        self._set_plane()

    def _set_plane(self) -> None:
        """Adjusts the plane position of Image and Labels layers. Display only points and lines belonging to the visible labels in this plane"""

        layers = [l for l in self.viewer.layers if isinstance(l, (napari.layers.Labels, napari.layers.Image)) and l != self.selected_labels]
        for l in layers: 
            plane_position = self.plane_slider.value()
            pos = l.plane.position
            l.plane.position = (plane_position, pos[1], pos[2])

        # specify which points, lines and tracks to show and which not to show
        labels_shown = np.unique(self.labels.data[self.viewer.dims.current_step[0], plane_position, :, :])
        track_ids = self.point_tracker.points.properties['track_id']
        track_id_mask = np.isin(track_ids, labels_shown)
        self.point_tracker.points.shown = track_id_mask

        track_ids = self.point_tracker.lines.properties['track_id']
        track_id_mask = np.isin(track_ids, labels_shown)
        line_colors = np.array(self.point_tracker.line_colors.copy())
        line_colors[~track_id_mask, 3] = 0     
        self.point_tracker.lines.edge_color = line_colors.tolist()

        track_ids = copy.deepcopy(self.tracks_props)
        original_track_data = copy.deepcopy(self.tracks_data)
        track_id_mask = np.isin(track_ids, labels_shown)
        filtered_track_data = original_track_data[track_id_mask]
        self.tracks.data = filtered_track_data

        # colormap business still to be fixed
        # create_selection_colormap(self.labels, 'selected_labels', list(labels_shown))
        # self.tracks.colormap = 'selected_labels'

        


        



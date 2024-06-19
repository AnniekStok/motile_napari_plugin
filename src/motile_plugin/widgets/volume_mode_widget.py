        
import napari.layers
import copy

import numpy            as np
import pandas           as pd

from qtpy.QtWidgets     import QWidget, QPushButton, QVBoxLayout,QHBoxLayout, QCheckBox, QGroupBox, QLabel, QButtonGroup, QRadioButton
from superqt            import QLabeledSlider
from qtpy               import QtCore
from PyQt5.QtCore       import Qt
from typing             import Tuple

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
        volume_view_box = QGroupBox('3D view')
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

        self.show_combined_timepoints_cb = QCheckBox('Show points t+1')
        self.show_combined_timepoints_cb.stateChanged.connect(self._show_combined_timepoints)

        button_layout.addLayout(plane_volume_layout)
        button_layout.addWidget(self.show_combined_timepoints_cb)
        
        # Add plane sliders for viewing in 3D
        z_layout = QVBoxLayout()
        radiobuttons = QButtonGroup()

        self.z_plane_btn = QRadioButton()
        self.y_plane_btn = QRadioButton()
        self.x_plane_btn = QRadioButton()
        self.z_plane_btn.setChecked(True)  # Set the default option

        self.z_plane_btn.clicked.connect(lambda: self._activate_slider('z'))
        self.y_plane_btn.clicked.connect(lambda: self._activate_slider('y'))
        self.x_plane_btn.clicked.connect(lambda: self._activate_slider('x'))
        
        radiobuttons.addButton(self.z_plane_btn)
        radiobuttons.addButton(self.y_plane_btn)
        radiobuttons.addButton(self.x_plane_btn)
   
        z_label = QLabel('z')
        self.z_plane_slider = QLabeledSlider(QtCore.Qt.Vertical)
        self.z_plane_slider.setSingleStep(1)
        self.z_plane_slider.setTickInterval(1)
        self.z_plane_slider.setValue(0)
        self.z_plane_slider.setEnabled(False)
        self.z_plane_slider.valueChanged.connect(lambda: self._set_plane('z'))
        self.z_plane_slider.setMaximumWidth(20)
        self.z_plane_slider.setMaximum(self.labels.data.shape[1])
        z_layout.addWidget(z_label)
        z_layout.addWidget(self.z_plane_btn)
        z_layout.addWidget(self.z_plane_slider)

        y_layout = QVBoxLayout()
        y_label = QLabel('y')
        self.y_plane_slider = QLabeledSlider(QtCore.Qt.Vertical)
        self.y_plane_slider.setSingleStep(1)
        self.y_plane_slider.setTickInterval(1)
        self.y_plane_slider.setValue(0)
        self.y_plane_slider.setEnabled(False)
        self.y_plane_slider.valueChanged.connect(lambda: self._set_plane('y'))
        self.y_plane_slider.setMaximumWidth(20)
        self.y_plane_slider.setMaximum(self.labels.data.shape[2])
        y_layout.addWidget(y_label)
        y_layout.addWidget(self.y_plane_btn)
        y_layout.addWidget(self.y_plane_slider)

        x_layout = QVBoxLayout()
        x_label = QLabel('x')
        self.x_plane_slider = QLabeledSlider(QtCore.Qt.Vertical)
        self.x_plane_slider.setSingleStep(1)
        self.x_plane_slider.setTickInterval(1)
        self.x_plane_slider.setValue(0)
        self.x_plane_slider.setEnabled(False)
        self.x_plane_slider.valueChanged.connect(lambda: self._set_plane('x'))
        self.x_plane_slider.setMaximumWidth(20)
        self.x_plane_slider.setMaximum(self.labels.data.shape[3])
        x_layout.addWidget(x_label)
        x_layout.addWidget(self.x_plane_btn)
        x_layout.addWidget(self.x_plane_slider)

        slider_layout = QHBoxLayout()
        slider_layout.addLayout(z_layout)
        slider_layout.addLayout(y_layout)
        slider_layout.addLayout(x_layout)
    

        view_mode_widget_layout.addLayout(button_layout)
        view_mode_widget_layout.addLayout(slider_layout)
        volume_view_box.setLayout(view_mode_widget_layout)

        main_layout = QVBoxLayout()
        main_layout.addWidget(volume_view_box)

        self.setLayout(main_layout)
        self.on_ndisplay_changed()
    
    def _update(self, 
            viewer: napari.Viewer,
            track_df: pd.DataFrame,
            labels: napari.layers.Labels,
            tracks: napari.layers.Tracks,
            selected_labels: napari.layers.Labels, 
            selected_nodes: NodeSelectionList
        ):
        """Update the data associated with the widget"""
        
        self.viewer = viewer
        self.track_df = track_df
        self.labels = labels
        self.tracks = tracks
        self.tracks_data = copy.deepcopy(self.tracks.data) # store for later
        self.tracks_props = copy.deepcopy(self.tracks.properties['track_id']) # store for later
        self.selected_labels = selected_labels
        self.selected_nodes = selected_nodes

        self.mode = 'volume'
        self.point_tracker._update(self.track_df, self.viewer)
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

    def _show_combined_timepoints(self):
        """Switch between showing only the points for the current time point or both the currrent and next time point"""

        if self.show_combined_timepoints_cb.isChecked():
            self.point_tracker._switch_mode('combined')
        else: 
            self.point_tracker._switch_mode('single')
       
        if self.mode == 'plane':
            if self.z_plane_btn.isChecked():
                self._set_plane(axis = 'z')
            elif self.y_plane_btn.isChecked():
                self._set_plane(axis = 'y')
            elif self.x_plane_btn.isChecked():
                self._set_plane(axis = 'x')

    def _set_plane_mode(self) -> None:
        """Set the mode to plane, enable slider and change depiction to 'plane' for Image and Labels layers"""

        self.mode = 'plane'
        self.plane_btn.setEnabled(False)
        self.volume_btn.setEnabled(True)
        self.z_plane_btn.setEnabled(True)
        self.y_plane_btn.setEnabled(True)
        self.x_plane_btn.setEnabled(True)
        self.z_plane_slider.setEnabled(True)
        self.y_plane_slider.setEnabled(False)
        self.x_plane_slider.setEnabled(False)

        layers = [l for l in self.viewer.layers if isinstance(l, (napari.layers.Labels, napari.layers.Image)) and l != self.selected_labels]
        for layer in layers:
            layer.depiction = 'plane'
            if isinstance(layer, napari.layers.Labels):
                layer.rendering = 'translucent'
        
        self._set_plane(axis = 'z')
        
    def _set_volume_mode(self) -> None: 
        """Set the mode to volume, disable slider and change depiction to 'volume' for Image and Labels layers"""

        self.mode = 'volume'
        self.plane_btn.setEnabled(True)
        self.volume_btn.setEnabled(False)
        self.z_plane_btn.setEnabled(False)
        self.y_plane_btn.setEnabled(False)
        self.x_plane_btn.setEnabled(False)
        self.z_plane_slider.setEnabled(False)
        self.y_plane_slider.setEnabled(False)
        self.x_plane_slider.setEnabled(False)

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
            self.z_plane_slider.setEnabled(False)
            self.y_plane_slider.setEnabled(False)
            self.x_plane_slider.setEnabled(False)

        else:
            self.plane_btn.setEnabled(True)
            self.volume_btn.setEnabled(False)
            self.z_plane_slider.setEnabled(False)
            self.y_plane_slider.setEnabled(False)
            self.x_plane_slider.setEnabled(False)
    
    def _set_plane_value(self, pos: Tuple) -> None:
        """Set the plane slider to specific value"""

        self.z_plane_slider.setValue(pos[0])
        self.y_plane_slider.setValue(pos[1])
        self.x_plane_slider.setValue(pos[2])

        if self.z_plane_btn.isChecked():
            self._set_plane(axis = 'z')
        elif self.y_plane_btn.isChecked():
            self._set_plane(axis = 'y')
        elif self.x_plane_btn.isChecked():
            self._set_plane(axis = 'x')

    def _activate_slider(self, axis: str) -> None: 
        """Activates or deactivates a plane"""

        layers = [l for l in self.viewer.layers if isinstance(l, (napari.layers.Labels, napari.layers.Image)) and l != self.selected_labels]
        for l in layers: 
            if axis == 'z':
                l.plane.normal = (1, 0, 0)
                self.z_plane_slider.setEnabled(True)               
                self.y_plane_slider.setEnabled(False)
                self.x_plane_slider.setEnabled(False)
                self._set_plane(axis = 'z')
            if axis == 'y':
                l.plane.normal = (0, 1, 0)
                self.z_plane_slider.setEnabled(False)               
                self.y_plane_slider.setEnabled(True)
                self.x_plane_slider.setEnabled(False)
                self._set_plane(axis = 'y')
            if axis == 'x':
                l.plane.normal = (0, 0, 1)
                self.z_plane_slider.setEnabled(False)               
                self.y_plane_slider.setEnabled(False)
                self.x_plane_slider.setEnabled(True)
                self._set_plane(axis = 'x')
         
    def _set_plane(self, axis: str) -> None:
        """Adjusts the plane position of Image and Labels layers. Display only points and lines belonging to the visible labels in this plane"""

        layers = [l for l in self.viewer.layers if isinstance(l, (napari.layers.Labels, napari.layers.Image)) and l != self.selected_labels]
        for l in layers: 
            pos = l.plane.position
            if axis == 'z':
                slider_position = self.z_plane_slider.value()
                l.plane.position = (slider_position, pos[1], pos[2])
                labels_shown = np.unique(self.labels.data[self.viewer.dims.current_step[0], slider_position, :, :])

            if axis == 'y':
                slider_position = self.y_plane_slider.value()
                l.plane.position = (pos[0], slider_position, pos[2])
                labels_shown = np.unique(self.labels.data[self.viewer.dims.current_step[0], :, slider_position, :])

            if axis == 'x':
                slider_position = self.x_plane_slider.value()
                l.plane.position = (pos[0], pos[1], slider_position)
                labels_shown = np.unique(self.labels.data[self.viewer.dims.current_step[0], :, :, slider_position])

        # specify which points, lines and tracks to show and which not to show
        track_ids = self.point_tracker.points.properties['track_id']
        track_id_mask = np.isin(track_ids, labels_shown)
        self.point_tracker.points.shown = track_id_mask

        track_ids = self.point_tracker.lines.properties['track_id']
        track_id_mask = np.isin(track_ids, labels_shown)
        line_colors = np.array(self.point_tracker.line_colors.copy())
        line_colors[~track_id_mask, 3] = 0     
        self.point_tracker.lines.edge_color = line_colors.tolist()

        # track_ids = copy.deepcopy(self.tracks_props)
        # original_track_data = copy.deepcopy(self.tracks_data)
        # track_id_mask = np.isin(track_ids, labels_shown)
        # filtered_track_data = original_track_data[track_id_mask]
        # self.tracks.data = filtered_track_data

        # colormap business still to be fixed
        # create_selection_colormap(self.labels, 'selected_labels', list(labels_shown))
        # self.tracks.colormap = 'selected_labels'

        


        



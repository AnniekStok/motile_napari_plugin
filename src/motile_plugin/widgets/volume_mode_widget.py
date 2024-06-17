        
import napari.layers

import numpy            as np

from qtpy.QtWidgets     import QWidget, QPushButton, QVBoxLayout
from typing             import List
from superqt            import QLabeledSlider
from qtpy               import QtCore


class VolumeModeWidget(QWidget):
    """Widget for switching between volume and plane mode, for 3D visualization purposes only
    """

    def __init__(
            self,
            viewer,
            labels: napari.layers.Labels,
            selected_labels: napari.layers.Labels, 
            points:napari.layers.Points, 
            lines: napari.layers.Shapes, 
            line_colors: List
            ):
        super().__init__()
        
        self.viewer = viewer
        self.points = points
        self.lines = lines
        self.labels = labels
        self.selected_labels = selected_labels
        self.line_colors = line_colors
        self.mode = 'volume'

        self.viewer.dims.events.ndisplay.connect(self.on_ndisplay_changed)
        view_mode_widget_layout = QVBoxLayout()
        
        # Add buttons to switch between plane and volume mode
        button_layout = QVBoxLayout()
        self.plane_btn = QPushButton('Plane')
        self.plane_btn.setEnabled(False)
        self.plane_btn.clicked.connect(self._set_plane_mode)
        self.volume_btn = QPushButton('Volume')
        self.volume_btn.setEnabled(True)
        self.volume_btn.clicked.connect(self._set_volume_mode)
        button_layout.addWidget(self.plane_btn)
        button_layout.addWidget(self.volume_btn)
        
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
        
        # show all the points and lines in volume mode
        self.points.shown = True
        self.lines.edge_color = self.line_colors

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

        # specify which points and lines to show and which not to show
        labels_shown = np.unique(self.labels.data[self.viewer.dims.current_step[0], plane_position, :, :])
        track_ids = self.points.properties['track_id']
        track_id_mask = np.isin(track_ids, labels_shown)
        self.points.shown = track_id_mask

        track_ids = self.lines.properties['track_id']
        track_id_mask = np.isin(track_ids, labels_shown)
        line_colors = np.array(self.line_colors.copy())
        line_colors[~track_id_mask, 3] = 0     
        self.lines.edge_color = line_colors.tolist()

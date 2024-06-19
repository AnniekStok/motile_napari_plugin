# Import necessary modules and create the viewer
%load_ext autoreload
%autoreload 2

from napari import Viewer
# from napari_ndlabelcuration._widget import AnnotateLabels3D
from motile_plugin.widgets.motile_widget import MotileWidget
import numpy as np

import os 
from skimage.io import imread


viewer = Viewer()




# Initial display of the widget
widget = MotileWidget(viewer)

# labels = imread('/Users/AStokkermans/Downloads/HeLa_cells_ultrack_cropped.tif')
labels = imread('/Users/AStokkermans/Downloads/test_3d_tracking.tif')
viewer.add_labels(labels)
viewer.window.add_dock_widget(widget, area='right', name='Motile')



import napari.layers
import pandas                       as pd 
import numpy                        as np
import networkx                     as nx
from PyQt5.QtCore                   import Qt, QObject
from PyQt5.QtCore                   import pyqtSignal

from .tree_widget_utils             import normalize_modifiers


class PointTracker(QObject):
    """Class to construct a points layer and corresponding line layer"""

    point_selected = pyqtSignal(str, object)  # Define a signal to emit the node_id of selected point and keyboard modifier

    def __init__(self, df:pd.DataFrame, viewer: napari.Viewer):
        super(PointTracker, self).__init__()

        self.df = df
        self.viewer = viewer
        self.points = self.construct_points()
        self.points.editable = False
        
        @self.points.mouse_drag_callbacks.append
        def click(layer, event):
            if event.type == 'mouse_press': 
                point_index = layer.get_value(event.position, 
                    view_direction=event.view_direction,
                    dims_displayed=event.dims_displayed,
                    world=True)
                if point_index is not None:                 
                    node_id = layer.properties['node_id'][point_index]
                    modifiers = event.modifiers
                    if isinstance(event.modifiers, tuple):
                        modifiers = normalize_modifiers(event.modifiers)
                    self.point_selected.emit(node_id, modifiers)

        self.lines = self.construct_lines()  
        self.lines.editable = False
        self.lines.interactive = False

    def construct_lines(self) -> napari.layers.Shapes:
        
        # Create lines between points at t and t+1
        lines = []
        self.line_colors = []
        track_ids = []
        for _, node in self.df.iterrows():      
            parent = node['parent_id']
            parent_df = self.df[self.df['node_id'] == parent]
            if not parent_df.empty:
                parent_dict = parent_df.iloc[0]
                start_point = [parent_dict['t'], parent_dict['y'], parent_dict['x']]
                end_point = [parent_dict['t'], node['y'], node['x']]
                if 'z' in self.df.columns:
                    start_point.insert(1, parent_dict['z'])
                    end_point.insert(1, node['z'])
                
                track_ids.append(parent_dict['track_id'])
                lines.append([start_point, end_point])
                self.line_colors.append(parent_dict['color'])
        
        line_properties = {'track_id': track_ids}

        return self.viewer.add_shapes(lines, shape_type='line', edge_color=self.line_colors, edge_width=1, properties = line_properties)

    def construct_points(self) -> napari.layers.Points:
        """Create a point layer for the nodes in the table, showing t and t+1 with different opacities."""

        # Get min and max values for t
        min_t = self.df['t'].min()
        max_t = self.df['t'].max()

        # Extract relevant columns
        points_t = self.df[['t', 'y', 'x']].values

        # Check if 'z' column is present and adjust points accordingly
        if 'z' in self.df.columns:
            points_t = np.column_stack((self.df['t'].values, self.df['z'].values, self.df['y'].values, self.df['x'].values))
        else:
            points_t = self.df[['t', 'y', 'x']].values

        # Extract colors
        colors_t = np.array(self.df['color'].tolist())

        # Create points for t+1
        df_t_plus_1 = self.df.copy()
        df_t_plus_1['t'] -= 1
        df_t_plus_1 = df_t_plus_1[(df_t_plus_1['t'] >= min_t) & (df_t_plus_1['t'] <= max_t)]

        points_t_plus_1 = df_t_plus_1[['t', 'y', 'x']].values
        
        if 'z' in df_t_plus_1.columns:
            points_t_plus_1 = np.column_stack((df_t_plus_1['t'].values, df_t_plus_1['z'].values, df_t_plus_1['y'].values, df_t_plus_1['x'].values))
        else:
            points_t_plus_1 = df_t_plus_1[['t', 'y', 'x']].values

        colors_t_plus_1 = np.array(df_t_plus_1['color'].tolist())

        # Combine points and colors
        combined_points = np.vstack((points_t, points_t_plus_1))
        combined_colors = np.vstack((colors_t, colors_t_plus_1))

        # node ids
        node_ids = self.df['node_id'].values
        node_ids_shift = df_t_plus_1['node_id'].values

        track_ids = self.df['track_id'].values
        track_ids_shift = df_t_plus_1['track_id'].values

        point_properties = {'node_id': np.concatenate((node_ids, node_ids_shift)), 'track_id': np.concatenate((track_ids, track_ids_shift))}

        # Set opacities, 1 for t, 0.5 for t+1
        opacities = np.array([1] * len(points_t) + [0.5] * len(points_t_plus_1))

        edge_colors = np.array(['white'] * len(points_t) + ['black'] * len(points_t_plus_1))

        # Apply opacities to colors
        combined_colors[:, 3] = opacities * 255  # Assuming colors are in RGBA format with values [0, 255]

        # Add points layer to the Napari viewer
        return self.viewer.add_points(combined_points, edge_color = edge_colors, properties = point_properties, face_color=combined_colors / 255, size=5)
        
        
        



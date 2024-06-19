
import napari.layers
import pandas                       as pd 
import numpy                        as np

class PointTracker:
    """Constructs a point layer for 3D + time data, displaying points at the current timepoint, or current timepoint + 1. 
    Also constructs a shapes layer consisting of lines between the points from different time points."""

    def __init__(self, df:pd.DataFrame, viewer: napari.Viewer):
        
        self.df = df
        self.viewer = viewer
        self.display = 'single' # toggle between 'single' for showing just the points for the current time point and 'combined' for also showing the points for t+1

        self.points = self.construct_points()
        self.points.editable = False

        self.lines = self.construct_lines()  
        self.lines.visible = False
        self.lines.editable = False
        self.lines.mouse_pan = False
        self.lines.mouse_zoom = False

    def _update(self, df:pd.DataFrame, viewer: napari.Viewer):
        """Update the points and lines layers"""

        self.df = df
        self.viewer = viewer
        self.display = 'single' # toggle between 'single' for showing just the points for the current time point and 'combined' for also showing the points for t+1

        self.viewer.layers.remove(self.points) # remove old layers
        self.viewer.layers.remove(self.lines) 

        self.points = self.construct_points()
        self.points.editable = False

        self.lines = self.construct_lines()  
        self.lines.visible = False
        self.lines.editable = False
        self.lines.mouse_pan = False
        self.lines.mouse_zoom = False

    def construct_lines(self) -> napari.layers.Shapes:
        """Construct a shapes layer consisting of lines connecting the points from different time points"""
        
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
                self.line_colors.append(parent_dict['color'] / 255)
        
        line_properties = {'track_id': track_ids}
        
        return self.viewer.add_shapes(lines, shape_type='line', edge_color=self.line_colors, edge_width=1, properties = line_properties)

    def construct_points(self) -> napari.layers.Points:
        """Create a point layer for the nodes in the table, showing t and t+1 with different opacities."""

        # Collect point data per time point
        self.colors_t = np.array(self.df['color'].tolist()) / 255
        node_ids = self.df['node_id'].values
        track_ids = self.df['track_id'].values
        self.properties = {'node_id': node_ids, 'track_id': track_ids}
        if 'z' in self.df.columns:
            self.points_t = np.column_stack((self.df['t'].values, self.df['z'].values, self.df['y'].values, self.df['x'].values))
        else:
            self.points_t = self.df[['t', 'y', 'x']].values
      
        # Create additional points for t+1 and combine
        df_shift = self.df.copy()
        df_shift['t'] -= 1

        min_t = self.df['t'].min()
        max_t = self.df['t'].max()
        df_shift = df_shift[(df_shift['t'] >= min_t) & (df_shift['t'] <= max_t)]
        colors_shift = np.array(df_shift['color'].tolist()) / 255
        node_ids_shift = df_shift['node_id'].values
        track_ids_shift = df_shift['track_id'].values     
        if 'z' in df_shift.columns:
            points_shift = np.column_stack((df_shift['t'].values, df_shift['z'].values, df_shift['y'].values, df_shift['x'].values))
        else:
            points_shift = df_shift[['t', 'y', 'x']].values

        self.combined_points = np.vstack((self.points_t, points_shift))
        self.combined_colors = np.vstack((self.colors_t, colors_shift))
        self.combined_properties = {'node_id': np.concatenate((node_ids, node_ids_shift)), 'track_id': np.concatenate((track_ids, track_ids_shift))}

        # Set different opacity and edge colors for the combined points
        self.combined_opacities = np.array([1] * len(self.points_t) + [0.5] * len(points_shift))
        self.combined_edge_colors = np.array(['white'] * len(self.points_t) + ['black'] * len(points_shift))
        self.combined_colors[:, 3] = self.combined_opacities

        # Add points layer (single time point) to the Napari viewer        
        return self.viewer.add_points(self.points_t, edge_color = 'white', properties = self.properties, face_color=self.colors_t, size=5)
    
    def _switch_mode(self, mode: str):
        """Switch between displaying data for a single time point or for two time points combined"""
        
        if mode == "combined":
            self.points.data = self.combined_points
            self.points.edge_color = self.combined_edge_colors
            self.points.properties = self.combined_properties
            self.points.face_color = self.combined_colors 
            self.lines.visible = True
        if mode == "single":
            self.points.data = self.points_t
            self.points.edge_color = 'white'
            self.points.properties = self.properties
            self.points.face_color = self.colors_t 
            self.lines.visible = False
            
        

        
        
        



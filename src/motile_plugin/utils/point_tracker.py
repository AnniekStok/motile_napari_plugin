import napari.layers
import numpy as np
from .track_data import TrackData
from .node_selection import NodeSelectionList

class PointTracker:
    """Constructs a point layer for 3D + time data, displaying points at the current timepoint, or current timepoint + 1.
    Also constructs a shapes layer consisting of lines between the points from different time points.
    """

    def __init__(self, track_data: TrackData, selected_nodes: NodeSelectionList, viewer: napari.Viewer):

        self.track_data = track_data
        self.viewer = viewer
        self.selected_nodes = selected_nodes

        self.points = None
        self.lines = None

        self._update()

    def _update(self) -> None:
        """Update the points and lines layers"""

        self.display = "single"  # toggle between 'single' for showing just the points for the current time point and 'combined' for also showing the points for t+1

        if self.points in self.viewer.layers:
            self.viewer.layers.remove(self.points)  # remove old layers
        if self.lines in self.viewer.layers: 
            self.viewer.layers.remove(self.lines)

        self.points = self._construct_points()
        self.points.editable = False

        @self.points.mouse_drag_callbacks.append
        def click(layer, event):
            if event.type == "mouse_press":
                point_index = layer.get_value(
                    event.position,
                    view_direction=event.view_direction,
                    dims_displayed=event.dims_displayed,
                    world=True,
                )
                if point_index is not None:
                    node_id = layer.properties["node_id"][point_index]
                    node_df = self.track_data.df[
                        (self.track_data.df["node_id"] == node_id)
                    ]
                    if not node_df.empty:
                        node = node_df.iloc[
                            0
                        ].to_dict()  # Convert the filtered result to a dictionary
                        self.selected_nodes.append(node, event.modifiers)

        self.lines = self._construct_lines()
        self.lines.visible = False
        self.lines.editable = False
        self.lines.mouse_pan = False
        self.lines.mouse_zoom = False
    
    def _user_update(self, node_id: str, edit: str) -> None:
        """Handle user edit, update the point visualization"""

        # extract the index to update
        indices = self.track_data.df.index[self.track_data.df['node_id'] == node_id].tolist()
        if len(indices) > 0:
            row_index = indices[0]
            if edit == "fork":
                self.points.symbol[row_index] = 'triangle_down'
                self.points.face_color[row_index] = np.array([1, 0, 0, 1])
            if edit == 'endpoint':
                self.points.symbol[row_index] = 'x'
                self.points.face_color[row_index] = np.array([1, 0, 0, 1])
            if edit == 'intermittent':
                self.points.symbol[row_index] = 'disc'
                self.points.face_color[row_index] = self.track_data.df.loc[row_index, 'color'] / 255
            self.points.refresh()

    def _construct_lines(self) -> napari.layers.Shapes:
        """Construct a shapes layer consisting of lines connecting the points from different time points"""

        # Create lines between points at t and t+1
        lines = []
        self.line_colors = []
        track_ids = []
        for _, node in self.track_data.df.iterrows():
            parent = node["parent_id"]
            parent_df = self.track_data.df[self.track_data.df["node_id"] == parent]
            if not parent_df.empty:
                parent_dict = parent_df.iloc[0]
                start_point = [
                    parent_dict["t"],
                    parent_dict["y"],
                    parent_dict["x"],
                ]
                end_point = [parent_dict["t"], node["y"], node["x"]]
                if "z" in self.track_data.df.columns:
                    start_point.insert(1, parent_dict["z"])
                    end_point.insert(1, node["z"])

                track_ids.append(parent_dict["track_id"])
                lines.append([start_point, end_point])
                self.line_colors.append(parent_dict["color"] / 255)

        line_properties = {"track_id": track_ids}

        return self.viewer.add_shapes(
            lines,
            shape_type="line",
            edge_color=self.line_colors,
            edge_width=1,
            properties=line_properties,
        )

    def _construct_points(self) -> napari.layers.Points:
        """Create a point layer for the nodes in the table, showing t and t+1 with different opacities."""

        edge_color = 'white'
        name = 'new_run_points'
        
        # Collect point data, colors and symbols directly from the track_data dataframe
        colors = np.array(self.track_data.df["color"].tolist()) / 255
        annotate_indices = self.track_data.df[self.track_data.df['annotated'] == True].index # manual edits should be displayed in a different color
        colors[annotate_indices] = np.array([1, 0, 0, 1])
        symbols = np.array(self.track_data.df['symbol'].tolist())
        node_ids = self.track_data.df["node_id"].values
        track_ids = self.track_data.df["track_id"].values
        properties = {"node_id": node_ids, "track_id": track_ids}

        if "z" in self.track_data.df.columns:
            points = np.column_stack(
                (
                    self.track_data.df["t"].values,
                    self.track_data.df["z"].values,
                    self.track_data.df["y"].values,
                    self.track_data.df["x"].values,
                )
            )
        else:
            points = self.track_data.df[["t", "y", "x"]].values

        # Add points layer (single time point) to the Napari viewer
        return self.viewer.add_points(
            points,
            name = name,
            edge_color=edge_color,
            properties=properties,
            face_color=colors,
            size=5,
            symbol = symbols,
        )




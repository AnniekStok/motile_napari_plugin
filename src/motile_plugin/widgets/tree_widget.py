import numpy            as np
import pyqtgraph        as pg
import pandas           as pd 

from PyQt5.QtGui        import QMouseEvent
from qtpy.QtWidgets     import QWidget, QHBoxLayout
from typing             import List

from ..utils.node_selection  import NodeSelectionList
class TreeWidget(QWidget):
    """pyqtgraph-based widget for lineage tree visualization and interactive annotation of nodes and edges"""

    def __init__(self, selected_nodes: NodeSelectionList, forks: List, endpoints: List):
        super().__init__()

        self.selected_nodes = selected_nodes
        self.selected_nodes.list_updated.connect(self._show_selected)

        self.forks = forks
        self.endpoints = endpoints

        # Construct the tree view pyqtgraph widget
        layout = QHBoxLayout()
        self.tree_widget = pg.PlotWidget()
        self.tree_widget.setTitle('Lineage Tree')
        self.tree_widget.setLabel('left', text='Time Point')
        self.tree_widget.getAxis('bottom').setStyle(showValues=False)
        self.g = pg.GraphItem()
        self.g.scatter.sigClicked.connect(self._on_click)
        self.tree_widget.addItem(self.g)
        layout.addWidget(self.tree_widget)

        self.setLayout(layout)

    def _on_click(self, _, points: np.ndarray, ev: QMouseEvent) -> None:
        """Adds the selected point to the selected_nodes list"""

        modifiers = ev.modifiers()
        clicked_point = points[0]
        index = clicked_point.index()  # Get the index of the clicked point

        # find the corresponding element in the list of dicts
        node_df = self.track_df[self.track_df['index'] == index]
        if not node_df.empty:
            # extract the selected node 
            node = node_df.iloc[0].to_dict()  # Convert the filtered result to a dictionary
            self.selected_nodes.append(node, modifiers)
    
    def _show_selected(self):     
        """Update the graph, increasing the size of selected node(s)"""

        size = self.size.copy() # just copy the size here to keep the original self.size intact
        for node in self.selected_nodes: 
            size[node['index']] = size[node['index']] + 5
                     
        self.g.setData(pos=self.pos, adj=self.adj, symbolBrush = self.symbolBrush, size = size, symbol = self.symbols, pen = self.pen)

    def _update(self, tracks: pd.DataFrame, pins: List, forks: List, endpoints: List) -> None:
        """Redraw the pyqtgraph object with the given tracks dataframe"""

        self.track_df = tracks
        self.forks = forks
        self.endpoints = endpoints
        pos = []
        pos_colors = []
        adj = []
        adj_colors = []
        symbols = []
        sizes = []

        for _, node in self.track_df.iterrows():      
            if node['node_id'] in self.forks:
                symbols.append('t')
                pos_colors.append([255, 0, 0, 255]) # edits displayed in red
                sizes.append(13)
            elif node['node_id'] in self.endpoints:
                symbols.append('x')
                pos_colors.append([255, 0, 0, 255]) # edits displayed in red
                sizes.append(13)
            else:
                symbols.append('o')
                pos_colors.append(node['color'])           
                sizes.append(8)

            pos.append([node['x_axis_pos'], node['t']])
            parent = node['parent_id']
            if parent != 0:
                parent_df = self.track_df[self.track_df['node_id'] == parent]
                if not parent_df.empty:
                    parent_dict = parent_df.iloc[0]
                    adj.append([parent_dict['index'], node['index']])
                    if (parent_dict['node_id'], node['node_id']) in pins:
                        adj_colors.append([255, 0, 0, 255, 255, 1]) # pinned edges displayed in red
                    else:
                        adj_colors.append(parent_dict['color'].tolist() + [255, 1])
                       
        self.pos = np.array(pos)
        self.adj = np.array(adj)
        self.symbols = symbols
        self.symbolBrush = np.array(pos_colors)
        self.pen = np.array(adj_colors)
        self.size = np.array(sizes)

        if len(self.pos) > 0:           
            self.g.setData(pos=self.pos, adj=self.adj, symbol = self.symbols, symbolBrush = self.symbolBrush, size = self.size, pen = self.pen)
        else: 
            self.g.scatter.clear()
    
    def _edit_node(self, edit: str) -> None:
        """Add a mark to this node: 'Fork' mean this node is dividing so that should have two daughter nodes at the next time point, 
        'Close' means this node is and endpoint and it should have no daughters at the next time point. 
        'Reset' means to remove the 'Fork' or 'Close' mark"""

        node = self.selected_nodes[0]

        if edit == 'Fork':
            self.symbols[node['index']] = 't'
            self.size[node['index']] = 13
            self.symbolBrush[node['index']] = [255, 0, 0, 255]
            
            if node['node_id'] in self.endpoints: 
                self.endpoints.remove(node['node_id'])
            
            self.forks.append(node['node_id'])
                    
        elif edit == 'Close': 
            self.symbols[node['index']] = 'x'
            self.size[node['index']] = 13
            self.symbolBrush[node['index']] = [255, 0, 0, 255]
            
            if node['node_id'] in self.forks: 
                self.forks.remove(node['node_id'])

            self.endpoints.append(node['node_id'])          
        
        else: 
            # reset node
            self.symbols[node['index']] = 'o'
            self.size[node['index']] = 8
            self.symbolBrush[node['index']] = node['color']
            
            if node['node_id'] in self.forks: 
                self.forks.remove(node['node_id'])
            if node['node_id'] in self.endpoints: 
                self.endpoints.remove(node['node_id'])
                
        self.g.setData(pos=self.pos, adj=self.adj, symbol = self.symbols, symbolBrush = self.symbolBrush, size = self.size, pen = self.pen)            
        self.selected_nodes.reset()
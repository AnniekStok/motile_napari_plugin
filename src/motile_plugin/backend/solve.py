import logging
import time

import numpy as np
from motile import Solver, TrackGraph
from motile.constraints import ExclusiveNodes, MaxChildren, MaxParents, Pin
from motile.costs import Appear, Disappear, EdgeDistance, EdgeSelection, Split
from motile_toolbox.candidate_graph import (
    EdgeAttr,
    NodeAttr,
    get_candidate_graph,
    graph_to_nx,
)

from .solver_params import SolverParams

logger = logging.getLogger(__name__)


def solve(
    solver_params: SolverParams,
    segmentation: np.ndarray,
    on_solver_update=None,
    pinned_edges: list[tuple[str, str, bool]] | None = None,
    forked_nodes: list[str] | None = None,
    endpoint_nodes: list[str] | None = None,
):
    cand_graph, conflict_sets = get_candidate_graph(
        segmentation,
        solver_params.max_edge_distance,
        iou=solver_params.iou is not None,
    )

    if pinned_edges is not None:
        for edge in pinned_edges:
            source_id, target_id, value = edge
            if cand_graph.has_edge(source_id, target_id):
                cand_graph[source_id][target_id]["pinned"] = value
            else:
                cand_graph.add_edge(
                    source_id, target_id, pinned=value, iou=1
                )  # find out how to compute the iou value here.

    if forked_nodes is not None:
        for node in forked_nodes:
            if node in cand_graph.nodes:
                cand_graph.nodes[node]["fork"] = True

    if endpoint_nodes is not None:
        for node in endpoint_nodes:
            if node in cand_graph.nodes:
                cand_graph.nodes[node]["endpoint"] = True

    logger.debug("Cand graph has %d nodes", cand_graph.number_of_nodes())
    solver = construct_solver(cand_graph, solver_params, conflict_sets)
    start_time = time.time()

    solution = solver.solve(verbose=False, on_event=on_solver_update)
    logger.info("Solution took %.2f seconds", time.time() - start_time)

    solution_graph = solver.get_selected_subgraph(solution=solution)
    solution_nx_graph = graph_to_nx(solution_graph)

    return solution_nx_graph


def construct_solver(cand_graph, solver_params, exclusive_sets):
    solver = Solver(
        TrackGraph(cand_graph, frame_attribute=NodeAttr.TIME.value)
    )
    solver.add_constraints(MaxChildren(solver_params.max_children))
    solver.add_constraints(MaxParents(1))
    if exclusive_sets is None or len(exclusive_sets) > 0:
        solver.add_constraints(ExclusiveNodes(exclusive_sets))

    solver.add_constraints(Pin("pinned"))

    if solver_params.appear_cost is not None:
        solver.add_costs(Appear(solver_params.appear_cost))
    if solver_params.disappear_cost is not None:
        solver.add_costs(Disappear(solver_params.disappear_cost))
    if solver_params.division_cost is not None:
        solver.add_costs(Split(constant=solver_params.division_cost))

    if solver_params.distance is not None:
        solver.add_costs(
            EdgeDistance(
                position_attribute=NodeAttr.POS.value,
                weight=solver_params.distance.weight,
                constant=solver_params.distance.constant,
            ),
            name="distance",
        )
    if solver_params.iou is not None:
        solver.add_costs(
            EdgeSelection(
                weight=solver_params.iou.weight,
                attribute=EdgeAttr.IOU.value,
                constant=solver_params.iou.constant,
            ),
            name="iou",
        )
    return solver

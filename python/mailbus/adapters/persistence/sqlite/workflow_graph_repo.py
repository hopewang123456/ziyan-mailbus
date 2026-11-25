"""工作流 Graph 仓储：wf_nodes + wf_node_transitions。"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence

from mailbus.core.workflow.models import WorkflowEdge, WorkflowNode

_NODE_COLUMNS = (
    "workflow_id, version, node_id, name, seq, position_id, node_type,"
    " prompt_template, needs_artifacts_from, max_retries, max_loops,"
    " timeout_seconds, config, pos_x, pos_y"
)
_NODE_VALUES = "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"


class SqliteWorkflowGraphRepository:
    """Graph 的唯一落点；wf_versions.nodes 只读历史。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def load(
        self, workflow_id: str, version: int
    ) -> tuple[list[WorkflowNode], list[WorkflowEdge]]:
        node_rows = self._conn.execute(
            "SELECT * FROM wf_nodes WHERE workflow_id = ? AND version = ?"
            " ORDER BY seq, node_id",
            (workflow_id, version),
        ).fetchall()
        edge_rows = self._conn.execute(
            "SELECT * FROM wf_node_transitions WHERE workflow_id = ? AND version = ?"
            " ORDER BY from_node_id, to_node_id",
            (workflow_id, version),
        ).fetchall()
        nodes = [_graph_node_from_row(row) for row in node_rows]
        edges = [
            WorkflowEdge(
                from_node_id=row["from_node_id"],
                to_node_id=row["to_node_id"],
                condition=row["condition"],
            )
            for row in edge_rows
        ]
        return nodes, edges

    def replace(
        self,
        workflow_id: str,
        version: int,
        nodes: Sequence[WorkflowNode],
        edges: Sequence[WorkflowEdge],
    ) -> None:
        self._conn.execute(
            "DELETE FROM wf_node_transitions WHERE workflow_id = ? AND version = ?",
            (workflow_id, version),
        )
        self._conn.execute(
            "DELETE FROM wf_nodes WHERE workflow_id = ? AND version = ?",
            (workflow_id, version),
        )
        self._insert_nodes(workflow_id, version, nodes)
        self._insert_edges(workflow_id, version, edges)

    def _insert_nodes(
        self, workflow_id: str, version: int, nodes: Sequence[WorkflowNode]
    ) -> None:
        for node in nodes:
            self._conn.execute(
                f"INSERT INTO wf_nodes ({_NODE_COLUMNS}) VALUES {_NODE_VALUES}",
                (
                    workflow_id,
                    version,
                    node.node_id,
                    node.name,
                    node.order,
                    node.position_id,
                    node.node_type,
                    node.prompt_template,
                    json.dumps(list(node.needs_artifacts_from), ensure_ascii=False),
                    node.max_retries,
                    node.max_loops,
                    node.timeout_seconds,
                    None if not node.config else json.dumps(node.config, ensure_ascii=False),
                    node.pos_x,
                    node.pos_y,
                ),
            )

    def _insert_edges(
        self, workflow_id: str, version: int, edges: Sequence[WorkflowEdge]
    ) -> None:
        for edge in edges:
            self._conn.execute(
                "INSERT INTO wf_node_transitions (workflow_id, version,"
                " from_node_id, to_node_id, condition) VALUES (?, ?, ?, ?, ?)",
                (workflow_id, version, edge.from_node_id, edge.to_node_id, edge.condition),
            )

    def copy(
        self, workflow_id: str, source_version: int, target_version: int
    ) -> None:
        self._conn.execute(
            f"INSERT INTO wf_nodes ({_NODE_COLUMNS})"
            " SELECT workflow_id, ?, node_id, name, seq, position_id, node_type,"
            " prompt_template, needs_artifacts_from, max_retries, max_loops,"
            " timeout_seconds, config, pos_x, pos_y FROM wf_nodes"
            " WHERE workflow_id = ? AND version = ?",
            (target_version, workflow_id, source_version),
        )
        self._conn.execute(
            "INSERT INTO wf_node_transitions (workflow_id, version, from_node_id,"
            " to_node_id, condition) SELECT workflow_id, ?, from_node_id, to_node_id,"
            " condition FROM wf_node_transitions WHERE workflow_id = ? AND version = ?",
            (target_version, workflow_id, source_version),
        )

    def bump_revision(self, workflow_id: str, version: int) -> int:
        self._conn.execute(
            "UPDATE wf_versions SET revision = revision + 1"
            " WHERE workflow_id = ? AND version = ?",
            (workflow_id, version),
        )
        row = self._conn.execute(
            "SELECT revision FROM wf_versions WHERE workflow_id = ? AND version = ?",
            (workflow_id, version),
        ).fetchone()
        return int(row["revision"]) if row is not None else 0


def _graph_node_from_row(row: sqlite3.Row) -> WorkflowNode:
    raw_config = row["config"]
    return WorkflowNode(
        node_id=row["node_id"],
        name=row["name"],
        order=row["seq"],
        node_type=row["node_type"],
        position_id=row["position_id"],
        prompt_template=row["prompt_template"],
        needs_artifacts_from=tuple(json.loads(row["needs_artifacts_from"] or "[]")),
        max_retries=row["max_retries"],
        max_loops=row["max_loops"],
        timeout_seconds=row["timeout_seconds"],
        config=json.loads(raw_config) if raw_config else {},
        pos_x=row["pos_x"],
        pos_y=row["pos_y"],
    )

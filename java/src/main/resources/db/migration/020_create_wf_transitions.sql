-- 020 工作流边表 + 旧线性版本回填：start → 首节点 → … → 末节点。
CREATE TABLE IF NOT EXISTS wf_node_transitions (
    workflow_id  TEXT NOT NULL,
    version      INTEGER NOT NULL,
    from_node_id TEXT NOT NULL,
    to_node_id   TEXT NOT NULL,
    condition    TEXT,
    PRIMARY KEY (workflow_id, version, from_node_id, to_node_id)
);

CREATE INDEX IF NOT EXISTS idx_wf_transitions_to
    ON wf_node_transitions (workflow_id, version, to_node_id);

INSERT INTO wf_node_transitions (workflow_id, version, from_node_id, to_node_id, condition)
SELECT v.workflow_id, v.version, 'start', json_extract(n.value, '$.node_id'), NULL
FROM wf_versions v, json_each(v.nodes) n
WHERE json_array_length(v.nodes) > 0
  AND CAST(n.key AS INTEGER) = 0;

INSERT INTO wf_node_transitions (workflow_id, version, from_node_id, to_node_id, condition)
SELECT v.workflow_id, v.version,
       json_extract(a.value, '$.node_id'),
       json_extract(b.value, '$.node_id'),
       NULL
FROM wf_versions v, json_each(v.nodes) a, json_each(v.nodes) b
WHERE CAST(b.key AS INTEGER) = CAST(a.key AS INTEGER) + 1;

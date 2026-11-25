-- 019 工作流节点表 + 旧版本回填。
-- 旧 wf_versions.nodes 只有 {node_id,name,order}，没有 start；自动补一个无副作用的 start 节点，
-- 旧节点顺序后移并按 x=seq*240 铺开坐标，避免编辑器打开时全部叠在原点。
CREATE TABLE IF NOT EXISTS wf_nodes (
    workflow_id          TEXT NOT NULL,
    version              INTEGER NOT NULL,
    node_id              TEXT NOT NULL,
    name                 TEXT NOT NULL,
    seq                  INTEGER NOT NULL,
    position_id          TEXT,
    node_type            TEXT NOT NULL DEFAULT 'agent',
    prompt_template      TEXT,
    needs_artifacts_from TEXT NOT NULL DEFAULT '[]',
    max_retries          INTEGER NOT NULL DEFAULT 3,
    max_loops            INTEGER NOT NULL DEFAULT 3,
    timeout_seconds      INTEGER,
    config               TEXT,
    pos_x                REAL NOT NULL DEFAULT 0,
    pos_y                REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (workflow_id, version, node_id)
);

INSERT INTO wf_nodes (
    workflow_id, version, node_id, name, seq, position_id, node_type,
    prompt_template, needs_artifacts_from, max_retries, max_loops,
    timeout_seconds, config, pos_x, pos_y
)
SELECT v.workflow_id, v.version, 'start', '开始', 0, NULL, 'start',
       NULL, '[]', 3, 3, NULL,
       '{"trigger":{"mode":["manual"]}}', 0, 120
FROM wf_versions v
WHERE NOT EXISTS (
    SELECT 1 FROM json_each(v.nodes) n
    WHERE json_extract(n.value, '$.node_id') = 'start'
);

INSERT INTO wf_nodes (
    workflow_id, version, node_id, name, seq, position_id, node_type,
    prompt_template, needs_artifacts_from, max_retries, max_loops,
    timeout_seconds, config, pos_x, pos_y
)
SELECT v.workflow_id, v.version,
       json_extract(n.value, '$.node_id'),
       json_extract(n.value, '$.name'),
       CAST(json_extract(n.value, '$.order') AS INTEGER) + 1,
       NULL, 'agent', NULL, '[]', 3, 3, NULL, NULL,
       (CAST(json_extract(n.value, '$.order') AS INTEGER) + 1) * 240.0,
       120.0
FROM wf_versions v, json_each(v.nodes) n;

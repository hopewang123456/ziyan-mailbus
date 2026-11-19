import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import {
  ConsolePageHeader,
  ConsoleSection,
  ConsoleTable,
  ConsoleTag,
} from "../../components/console/ConsoleKit";

/** 团队、岗位与工位分配：工位归属直接 PATCH 覆盖层，布局页即时生效。 */

type Team = { team_id: string; name: string };
type Position = { position_id: string; name: string; capabilities: string[] };
type Seat = {
  seat_id: string;
  floor_id: string;
  room_id: string;
  x: number;
  y: number;
  rotation: number;
  team_id?: string | null;
  position_id?: string | null;
};

export function ConsoleTeamsPage({ can }: { can: (capability: string) => boolean }) {
  const [teams, setTeams] = useState<Team[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [seats, setSeats] = useState<Seat[]>([]);
  const [teamName, setTeamName] = useState("");
  const [positionName, setPositionName] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const load = async () => {
    const [t, p, s] = await Promise.all([
      api<Team[]>("/api/org/teams"),
      api<Position[]>("/api/org/positions"),
      api<Seat[]>("/api/org/seats"),
    ]);
    if (t.ok) setTeams(t.data);
    if (p.ok) setPositions(p.data);
    if (s.ok) setSeats(s.data);
    const errors = [t, p, s]
      .filter((result) => !result.ok)
      .map((result) => (result.ok ? "" : result.error));
    if (errors.length) setErr(errors.filter(Boolean).join("; "));
  };

  useEffect(() => {
    void load();
  }, []);

  async function createTeam() {
    const name = teamName.trim();
    if (!name) return;
    setErr("");
    setMsg("");
    const result = await api("/api/org/teams", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setTeamName("");
    setMsg(`已创建团队「${name}」`);
    await load();
  }

  async function createPosition() {
    const name = positionName.trim();
    if (!name) return;
    setErr("");
    setMsg("");
    const result = await api("/api/org/positions", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setPositionName("");
    setMsg(`已创建岗位「${name}」`);
    await load();
  }

  async function assignSeat(seat: Seat, patch: { team_id?: string; position_id?: string }) {
    setErr("");
    setMsg("");
    const result = await api<Seat>(
      `/api/org/seats/${encodeURIComponent(seat.seat_id)}`,
      { method: "PATCH", body: JSON.stringify(patch) },
    );
    if (!result.ok) {
      setErr(result.error);
      return;
    }
    setSeats((rows) =>
      rows.map((row) => (row.seat_id === seat.seat_id ? result.data : row)),
    );
    setMsg(`工位 ${seat.seat_id} 已更新`);
  }

  return (
    <>
      <ConsolePageHeader
        title="团队与工位"
        description="创建团队/岗位，并把工位归属到团队与岗位；孪生布局会按此投影"
      />

      {err && <p className="mb-3 text-xs text-flare">{err}</p>}
      {msg && <p className="mb-3 text-xs text-mint">{msg}</p>}

      <ConsoleSection
        title={`团队（${teams.length}）`}
        actions={
          <span className="flex items-center gap-2">
            <input
              className="w-40 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              placeholder="团队名称"
              disabled={!can("org_manage")}
              value={teamName}
              onChange={(e) => setTeamName(e.target.value)}
            />
            <button
              type="button"
              className="hud-btn text-xs disabled:opacity-40"
              disabled={!can("org_manage")}
              onClick={() => void createTeam()}
            >
              新建
            </button>
          </span>
        }
      >
        <ConsoleTable
          rows={teams}
          rowKey={(row) => row.team_id}
          empty="暂无团队"
          columns={[
            {
              key: "id",
              header: "team_id",
              render: (row) => <span className="font-mono text-[11px]">{row.team_id}</span>,
            },
            { key: "name", header: "名称", render: (row) => row.name },
          ]}
        />
      </ConsoleSection>

      <ConsoleSection
        title={`岗位（${positions.length}）`}
        actions={
          <span className="flex items-center gap-2">
            <input
              className="w-40 rounded border border-rail bg-hull px-2 py-1 text-xs text-frost"
              placeholder="岗位名称"
              disabled={!can("org_manage")}
              value={positionName}
              onChange={(e) => setPositionName(e.target.value)}
            />
            <button
              type="button"
              className="hud-btn text-xs disabled:opacity-40"
              disabled={!can("org_manage")}
              onClick={() => void createPosition()}
            >
              新建
            </button>
          </span>
        }
      >
        <ConsoleTable
          rows={positions}
          rowKey={(row) => row.position_id}
          empty="暂无岗位"
          columns={[
            {
              key: "id",
              header: "position_id",
              render: (row) => <span className="font-mono text-[11px]">{row.position_id}</span>,
            },
            { key: "name", header: "名称", render: (row) => row.name },
            {
              key: "caps",
              header: "能力",
              render: (row) => (
                <span className="flex flex-wrap gap-1">
                  {row.capabilities.length ? (
                    row.capabilities.map((cap) => <ConsoleTag key={cap}>{cap}</ConsoleTag>)
                  ) : (
                    <span className="text-mute">—</span>
                  )}
                </span>
              ),
            },
          ]}
        />
      </ConsoleSection>

      <ConsoleSection title={`工位分配（${seats.length}）`}>
        <ConsoleTable
          rows={seats}
          rowKey={(row) => row.seat_id}
          empty="暂无工位"
          columns={[
            {
              key: "seat",
              header: "工位",
              render: (row) => <span className="font-mono text-[11px]">{row.seat_id}</span>,
            },
            {
              key: "loc",
              header: "位置",
              render: (row) => (
                <span className="text-[11px] text-mute">
                  {row.floor_id} / {row.room_id}
                </span>
              ),
            },
            {
              key: "team",
              header: "团队",
              render: (row) => (
                <select
                  className="rounded border border-rail bg-hull px-1.5 py-0.5 text-[11px] text-frost"
                  value={row.team_id || ""}
                  disabled={!can("org_manage")}
                  onChange={(e) => {
                    if (e.target.value) void assignSeat(row, { team_id: e.target.value });
                  }}
                >
                  <option value="">未分配</option>
                  {teams.map((team) => (
                    <option key={team.team_id} value={team.team_id}>
                      {team.name}
                    </option>
                  ))}
                </select>
              ),
            },
            {
              key: "position",
              header: "岗位",
              render: (row) => (
                <select
                  className="rounded border border-rail bg-hull px-1.5 py-0.5 text-[11px] text-frost"
                  value={row.position_id || ""}
                  disabled={!can("org_manage")}
                  onChange={(e) => {
                    if (e.target.value) {
                      void assignSeat(row, { position_id: e.target.value });
                    }
                  }}
                >
                  <option value="">未分配</option>
                  {positions.map((position) => (
                    <option key={position.position_id} value={position.position_id}>
                      {position.name}
                    </option>
                  ))}
                </select>
              ),
            },
          ]}
        />
      </ConsoleSection>
    </>
  );
}

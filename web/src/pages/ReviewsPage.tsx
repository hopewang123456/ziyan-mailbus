import { useEffect, useState } from "react";
import { api } from "../lib/api";

export function ReviewsPage() {
  const [list, setList] = useState<unknown>(null);
  const [projects, setProjects] = useState<unknown>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    void Promise.all([api("/api/reviews"), api("/api/reviews/projects")]).then(([a, b]) => {
      if (a.ok) setList(a.data);
      else setErr(a.error);
      if (b.ok) setProjects(b.data);
    });
  }, []);

  return (
    <div className="space-y-4">
      <header>
        <p className="hud-label">Sensor logs</p>
        <h2 className="mt-1 font-display text-2xl tracking-wide">Reviews</h2>
      </header>
      {err && <p className="text-sm text-flare">{err}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <pre className="max-h-80 overflow-auto rounded-sm border border-rail bg-hull/50 p-3 text-xs text-mute">
          {list ? JSON.stringify(list, null, 2) : "…"}
        </pre>
        <pre className="max-h-80 overflow-auto rounded-sm border border-rail bg-hull/50 p-3 text-xs text-mute">
          {projects ? JSON.stringify(projects, null, 2) : "…"}
        </pre>
      </div>
    </div>
  );
}

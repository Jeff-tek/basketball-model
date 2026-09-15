import type { Tip } from "../lib/tips";

const num = (v: number | null | undefined): string =>
  typeof v === "number" && Number.isFinite(v) ? String(v) : "–";

const pct1 = (v: number | null | undefined): string => {
  if (typeof v !== "number" || !Number.isFinite(v)) return "–";
  const p = v > 1 ? v / 100 : v;
  return `${(p * 100).toFixed(1)}%`;
};

const pace = (v: number | null | undefined): string =>
  typeof v === "number" && v > 0 ? v.toFixed(1) : "–";

export default function TeamDuel({ t }: { t: Tip }) {
  const h = t.teamMeta?.home;
  const a = t.teamMeta?.away;
  if (!h && !a && !(t.homePace > 0) && !(t.awayPace > 0)) return null;
  const rows: [string, string, string][] = [
    ["Rank", num(h?.rank), num(a?.rank)],
    ["W–L", `${num(h?.wins)}–${num(h?.losses)}`, `${num(a?.wins)}–${num(a?.losses)}`],
    ["Win %", pct1(h?.winPct), pct1(a?.winPct)],
    ["Streak", h?.streak || "–", a?.streak || "–"],
    ["Pace", pace(t.homePace), pace(t.awayPace)],
    ["PF / PA", `${num(h?.pf)} / ${num(h?.pa)}`, `${num(a?.pf)} / ${num(a?.pa)}`],
    ["Form", t.homeForm || "–", t.awayForm || "–"],
  ];
  return (
    <div className="viz-block">
      <div className="viz-title">Team data · this league</div>
      <table className="team-table">
        <thead>
          <tr><th></th><th>{t.home}</th><th>{t.away}</th></tr>
        </thead>
        <tbody>
          {rows.map(([k, hv, av]) => (
            <tr key={k}><td className="team-k">{k}</td><td>{hv}</td><td>{av}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type LeagueTabsProps = {
  leagues: readonly string[];
  active: string;
  counts: Record<string, number>;
  onChange: (league: string) => void;
};

export default function LeagueTabs({ leagues, active, counts, onChange }: LeagueTabsProps) {
  return (
    <div className="league-tabs" role="tablist" aria-label="League">
      {leagues.map((lg) => (
        <button
          key={lg}
          role="tab"
          aria-selected={lg === active}
          className={`league-tab ${lg === active ? "active" : ""}`}
          onClick={() => onChange(lg)}
        >
          {lg}
          {counts[lg] != null && <span className="tab-count">{counts[lg]}</span>}
        </button>
      ))}
    </div>
  );
}
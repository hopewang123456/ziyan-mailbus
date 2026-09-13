export type HudCard = {
  id: string;
  title: string;
  blurb?: string;
};

type Props = {
  cards: HudCard[];
  onOpen: (id: string) => void;
  surface?: "fleet" | "form";
  badges?: Record<string, number>;
};

/** L2 安卓式卡片网格 */
export function HudCardGrid({ cards, onOpen, surface = "form", badges }: Props) {
  return (
    <ul className="cp-card-grid" data-surface={surface}>
      {cards.map((c) => (
        <li key={c.id}>
          <button type="button" className="cp-android-card" onClick={() => onOpen(c.id)}>
            <span className="cp-android-card-title">
              {c.title}
              {badges && badges[c.id] ? (
                <span className="ml-2 inline-flex items-center justify-center rounded-full bg-flare px-1.5 py-0.5 font-mono text-[11px] leading-none text-frost">
                  {badges[c.id] > 99 ? "99+" : badges[c.id]}
                </span>
              ) : null}
            </span>
            {c.blurb && <span className="cp-android-card-blurb">{c.blurb}</span>}
          </button>
        </li>
      ))}
    </ul>
  );
}

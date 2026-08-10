export type HudCard = {
  id: string;
  title: string;
  blurb?: string;
};

type Props = {
  cards: HudCard[];
  onOpen: (id: string) => void;
  surface?: "fleet" | "form";
};

/** L2 安卓式卡片网格 */
export function HudCardGrid({ cards, onOpen, surface = "form" }: Props) {
  return (
    <ul className="cp-card-grid" data-surface={surface}>
      {cards.map((c) => (
        <li key={c.id}>
          <button type="button" className="cp-android-card" onClick={() => onOpen(c.id)}>
            <span className="cp-android-card-title">{c.title}</span>
            {c.blurb && <span className="cp-android-card-blurb">{c.blurb}</span>}
          </button>
        </li>
      ))}
    </ul>
  );
}

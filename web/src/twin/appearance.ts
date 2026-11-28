/**
 * 人物外观：按员工稳定键生成固定的「捏脸」组合。
 * 坐姿（SeatView）与走动（Walker）必须使用同一 seed，保证同一人外观一致。
 */

export type HairStyle = "short" | "long" | "bun" | "bob" | "curly" | "ponytail";
export type Accessory = "none" | "headphones" | "cap" | "beard" | "tie";

export interface PersonAppearance {
  shirt: string;
  shirtAccent: string;
  hair: string;
  skin: string;
  hairStyle: HairStyle;
  accessory: Accessory;
  accessoryColor: string;
  glasses: boolean;
  backpack: boolean;
  /** 体型系数：身体宽度与头围，0.86–1.16 之间拉开差异。 */
  figW: number;
  head: number;
}

const SHIRTS = [
  "#a8c8ee", "#cbb6e8", "#f6c9a0", "#a9d8c4", "#f2b6c6", "#f2d98f",
  "#9fd4e8", "#e8b4a0", "#b8e0a8", "#d8b4e8", "#f0a8a0", "#8fb8d8",
  "#f4dca8", "#c8e8d8", "#e0c8f0", "#f0c8b8",
];

const ACCENTS = [
  "#7fa8d4", "#a98fce", "#d4a574", "#7fb8a0", "#d48fa8", "#d4bc6a",
  "#6fb0c8", "#c89078", "#8fb878", "#b894c8", "#c88080", "#6f98b8",
];

const HAIRS = [
  "#f0d28c", "#f4afcb", "#a9785b", "#c9bbec", "#6e5344", "#c98b65",
  "#3a2e28", "#8a4a2e", "#d8d0c8", "#4a3a5a", "#2a2420", "#b06a3a",
];

const SKINS = ["#fcdcbe", "#f4c69e", "#e8b48c", "#d49a72", "#b87f56", "#f8d0a8"];

const HAIR_STYLES: HairStyle[] = ["short", "long", "bun", "bob", "curly", "ponytail"];

const ACCESSORIES: Accessory[] = ["none", "none", "headphones", "cap", "beard", "tie"];

const ACCESSORY_COLORS = [
  "#4f6d9a", "#8a5a6a", "#3f7a63", "#7a52a0", "#b06a3a", "#2f4a6a", "#a8544f",
];

/** 与 Walker 既有一致的稳定哈希，避免同人外观在版本间漂移。 */
function hash(seed: string): number {
  let n = 0;
  for (let i = 0; i < seed.length; i += 1) n = (n * 31 + seed.charCodeAt(i)) % 9973;
  return n;
}

function pick<T>(list: T[], seed: string, salt: string): T {
  return list[hash(`${seed}:${salt}`) % list.length];
}

/**
 * 生成外观。seed 取 agent_id，公开布局缺失时用 display_name 兜底。
 * 各特征用不同 salt 派生，避免颜色与发型强相关导致「看起来还是同一个人」。
 */
export function personAppearance(seed: string): PersonAppearance {
  const shirt = pick(SHIRTS, seed, "shirt");
  let accent = pick(ACCENTS, seed, "accent");
  if (accent === shirt) accent = SHIRTS[(hash(seed) + 3) % SHIRTS.length];
  const w = hash(`${seed}:build`);
  return {
    shirt,
    shirtAccent: accent,
    hair: pick(HAIRS, seed, "hair"),
    skin: pick(SKINS, seed, "skin"),
    hairStyle: pick(HAIR_STYLES, seed, "style"),
    accessory: pick(ACCESSORIES, seed, "acc"),
    accessoryColor: pick(ACCESSORY_COLORS, seed, "acc-color"),
    glasses: hash(`${seed}:glasses`) % 100 < 34,
    backpack: hash(`${seed}:backpack`) % 100 >= 68,
    figW: 0.86 + (w % 7) * 0.05,
    head: 0.92 + (w % 5) * 0.04,
  };
}

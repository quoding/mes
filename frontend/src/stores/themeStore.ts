import { create } from "zustand";

type Theme = "dark" | "light";

function apply(theme: Theme) {
  document.documentElement.classList.toggle("light", theme === "light");
}

const initial = (localStorage.getItem("theme") as Theme) ?? "dark";
apply(initial);

interface ThemeState {
  theme: Theme;
  toggle: () => void;
}

export const useThemeStore = create<ThemeState>((set) => ({
  theme: initial,
  toggle: () =>
    set((s) => {
      const next: Theme = s.theme === "dark" ? "light" : "dark";
      localStorage.setItem("theme", next);
      apply(next);
      return { theme: next };
    }),
}));

/** 차트 등 SVG 속성은 CSS 변수를 못 쓰므로 테마별 구체 색상을 제공 */
export function useChartTheme() {
  const theme = useThemeStore((s) => s.theme);
  return theme === "light"
    ? { grid: "#dde3ee", tick: "#8593a8", tooltipBg: "rgba(255,255,255,0.97)", tooltipBorder: "#d9e0ec", crit: "#e11d48" }
    : { grid: "#1c2740", tick: "#64748b", tooltipBg: "rgba(13,19,34,0.95)", tooltipBorder: "#1c2740", crit: "#fb7185" };
}

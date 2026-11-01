import { useEffect, useState } from "react";
import { applyTheme, currentTheme, storedTheme, type Theme } from "../theme";

const SUN = (
  <svg viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="8" cy="8" r="3" />
    <path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1" />
  </svg>
);

const MOON = (
  <svg viewBox="0 0 16 16" aria-hidden="true">
    <path d="M13.5 9.6A5.8 5.8 0 0 1 6.4 2.5a5.8 5.8 0 1 0 7.1 7.1Z" />
  </svg>
);

/** Light or dark. Until a choice is made the system setting decides, and follows it as it changes. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(currentTheme);

  useEffect(() => {
    const query = matchMedia("(prefers-color-scheme: dark)");
    const follow = () => {
      if (storedTheme()) return;
      applyTheme(query.matches ? "dark" : "light", false);
      setTheme(currentTheme());
    };
    query.addEventListener("change", follow);
    return () => query.removeEventListener("change", follow);
  }, []);

  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button
      className="icon-button"
      aria-label={`Switch to the ${next} theme`}
      title={`Switch to the ${next} theme`}
      onClick={() => {
        applyTheme(next, true);
        setTheme(next);
      }}
    >
      {theme === "dark" ? SUN : MOON}
    </button>
  );
}

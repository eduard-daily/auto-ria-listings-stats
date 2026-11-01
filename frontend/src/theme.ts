export type Theme = "light" | "dark";

export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function storedTheme(): Theme | null {
  try {
    const value = localStorage.getItem("theme");
    return value === "dark" || value === "light" ? value : null;
  } catch {
    return null; // storage can be blocked; the choice then lasts until the page closes
  }
}

/** Switches the theme; a user's choice is remembered, a follow of the system setting is not. */
export function applyTheme(theme: Theme, remember: boolean): void {
  document.documentElement.dataset.theme = theme;
  if (!remember) return;
  try {
    localStorage.setItem("theme", theme);
  } catch {
    // not remembered
  }
}

import { NavLink, Outlet } from "react-router-dom";
import { NoticeBanner } from "./NoticeBanner";
import { ThemeToggle } from "./ThemeToggle";
import { UpdateButton } from "./UpdateButton";

function Logo() {
  return (
    <svg className="logo" viewBox="0 0 24 24" aria-hidden="true">
      <rect width="24" height="24" rx="6" />
      <path d="M4 16h5v-5h5V7h6" />
    </svg>
  );
}

export function Layout() {
  return (
    <>
      <header className="topbar">
        <div className="container topbar-inner">
          <NavLink to="/" className="brand">
            <Logo />
            <span className="brand-name">ria-stats</span>
          </NavLink>
          <nav className="nav">
            <NavLink to="/" end>
              Listings
            </NavLink>
            <NavLink to="/stats">Stats</NavLink>
            <NavLink to="/settings">Settings</NavLink>
          </nav>
          <div className="topbar-actions">
            <UpdateButton />
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className="container page">
        <NoticeBanner />
        <Outlet />
      </main>
      <footer className="container footer">
        Listing data from <a href="https://auto.ria.com">AUTO.RIA</a>
      </footer>
    </>
  );
}

import { NavLink } from "react-router-dom";

export function Header() {
  return (
    <header className="app-header">
      <span className="app-title">AIC Retrieval</span>
      <nav>
        <NavLink to="/" end>Search</NavLink>
        <NavLink to="/temporal">Temporal</NavLink>
        <NavLink to="/submit">Submit</NavLink>
      </nav>
    </header>
  );
}

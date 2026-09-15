import { Link, NavLink, Outlet } from 'react-router-dom'

import { useCompetitions } from '../api/client'
import { useFavourites } from '../lib/favourites'
import { Crest } from './Crest'
import { SearchBox } from './SearchBox'

export function Layout() {
  const { data: competitions } = useCompetitions()
  const favs = useFavourites()
  const hasFavs = favs.teams.length > 0 || favs.competitions.length > 0

  return (
    <>
      <header className="app-header">
        <div className="app-header__inner">
          <Link to="/" className="brand">
            Chair<span>score</span>
          </Link>
          <SearchBox />
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          {hasFavs && (
            <>
              <div className="sidebar__title">Favourites</div>
              {favs.competitions.map((c) => (
                <NavLink
                  key={`c${c.code}`}
                  to={`/competitions/${c.code}`}
                  className={({ isActive }) => `nav-item${isActive ? ' nav-item--active' : ''}`}
                >
                  <Crest src={c.emblem_url} alt={c.name} />
                  <span className="nav-item__label">{c.name}</span>
                </NavLink>
              ))}
              {favs.teams.map((t) => (
                <NavLink
                  key={`t${t.id}`}
                  to={`/teams/${t.id}`}
                  className={({ isActive }) => `nav-item${isActive ? ' nav-item--active' : ''}`}
                >
                  <Crest src={t.crest_url} alt={t.name} />
                  <span className="nav-item__label">{t.name}</span>
                </NavLink>
              ))}
              <div className="sidebar__sep" />
            </>
          )}

          <div className="sidebar__title">Competitions</div>
          {(competitions ?? []).map((c) => (
            <NavLink
              key={c.code}
              to={`/competitions/${c.code}`}
              className={({ isActive }) => `nav-item${isActive ? ' nav-item--active' : ''}`}
            >
              <Crest src={c.emblem_url} alt={c.name} />
              <span className="nav-item__label">{c.name}</span>
            </NavLink>
          ))}
        </aside>

        <main>
          <Outlet />
        </main>
      </div>
    </>
  )
}

import {
  type FavCompetition,
  type FavTeam,
  toggleFavCompetition,
  toggleFavTeam,
  useFavourites,
} from '../lib/favourites'

export function FavStar(props: { team: FavTeam } | { competition: FavCompetition }) {
  const favs = useFavourites()
  const isTeam = 'team' in props
  const active = isTeam
    ? favs.teams.some((t) => t.id === props.team.id)
    : favs.competitions.some((c) => c.code === props.competition.code)

  return (
    <button
      type="button"
      className={`fav-star${active ? ' fav-star--on' : ''}`}
      aria-pressed={active}
      title={active ? 'Remove from favourites' : 'Add to favourites'}
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        if (isTeam) toggleFavTeam(props.team)
        else toggleFavCompetition(props.competition)
      }}
    >
      {active ? '★' : '☆'}
    </button>
  )
}

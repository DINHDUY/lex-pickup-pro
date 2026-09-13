import { Link } from 'react-router-dom'
import { ArrowRight, Crown, Shield } from 'lucide-react'
import { useClub } from '../api'
import { teamName } from '../lib'
import { Avatar, Badge, ErrorState, FormGuide, Loading, PageHeading, TeamCrest } from '../components/ui'

export function Teams() {
  const club = useClub()
  if (club.loading) return <Loading />
  if (club.error) return <ErrorState error={club.error} />
  return (
    <>
      <PageHeading
        eyebrow="TWO SIDES OF THE SAME STORY"
        title="Rivals for 90 minutes. Mates for life."
        description="Different shirts. The same love of a Saturday morning game."
      />
      <div className="teams-grid">
        {club.stats!.teams.map((team) => {
          const players = club.players.filter((p) => p.team_id === team.id)
          return (
            <section className={`card team-panel team-${team.id}`} key={team.id}>
              <div className="team-panel-hero">
                <span className="eyebrow">LEXINGTON FOOTBALL CLUB</span>
                <TeamCrest team={team.id} size={88} />
                <h2>{team.name}</h2>
                <p>{team.motto}</p>
                <Badge tone={team.id === 1 ? 'green' : 'gold'}>
                  {players.length} players · {players.filter((p) => p.is_captain).length} captain
                  {players.filter((p) => p.is_captain).length === 1 ? '' : 's'}
                </Badge>
              </div>
              <div className="team-record">
                <div>
                  <strong>{team.wins}</strong>
                  <span>WINS</span>
                </div>
                <div>
                  <strong>{team.draws}</strong>
                  <span>DRAWS</span>
                </div>
                <div>
                  <strong>{team.losses}</strong>
                  <span>LOSSES</span>
                </div>
                <div>
                  <strong>{team.goals_for}</strong>
                  <span>GOALS</span>
                </div>
              </div>
              <div className="team-form">
                <span>RECENT FORM</span>
                <FormGuide form={team.form} />
              </div>
              <div className="team-squad">
                <h3>The {teamName(team.id)} squad</h3>
                {players
                  .sort((a, b) => Number(b.is_captain) - Number(a.is_captain))
                  .map((p) => (
                    <Link to={`/players/${p.id}`} key={p.id}>
                      <Avatar player={p} size="sm" />
                      <div>
                        <strong>
                          {p.name}
                          {p.is_captain && <Crown size={13} className="gold-text" />}
                        </strong>
                        <span>{p.positions?.replaceAll(',', ' / ') || 'Not provided'}</span>
                      </div>
                      <span className="squad-number">{p.jersey === null ? '—' : `#${p.jersey}`}</span>
                      <ArrowRight size={15} />
                    </Link>
                  ))}
              </div>
            </section>
          )
        })}
      </div>
      <div className="info-callout">
        <Shield size={22} />
        <div>
          <strong>One shared player pool. Better games for everyone.</strong>
          <p>
            Captains can build mixed sides from confirmed players. Your primary team stays the same, and mixed
            games are excluded from the rivalry record.
          </p>
        </div>
        <Link to="/schedule" className="text-link">
          Find a game
          <ArrowRight size={15} />
        </Link>
      </div>
    </>
  )
}

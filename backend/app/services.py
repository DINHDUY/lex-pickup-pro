from collections import defaultdict
from datetime import timezone

from .domain.club import ClubData
from .domain.records import RSVP, Lineup, Match, MatchEvent, Player, Rating, Team


def iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()


def row_dict(row):
    return row.model_dump(mode="json")


def statistics(db: ClubData, season_id: int | None = None):
    matches = {
        m.id: m
        for m in sorted(
            [row for row in db.records(Match) if row.status == "completed"],
            key=lambda row: row.starts_at,
            reverse=False,
        )
        if season_id is None or m.season_id == season_id
    }
    players = list(db.records(Player))
    stats = {
        p.id: {
            "player_id": p.id,
            "name": p.name,
            "nickname": p.nickname,
            "team_id": p.team_id,
            "jersey": p.jersey,
            "positions": p.positions,
            "photo_url": p.photo_url,
            "games": 0,
            "goals": 0,
            "assists": 0,
            "wins": 0,
            "draws": 0,
            "clean_sheets": 0,
            "ratings": [],
            "form": [],
            "attended_promises": 0,
            "promises": 0,
        }
        for p in players
    }
    assignments = {}
    for lineup in sorted(db.records(Lineup), key=lambda row: (db.get(Match, row.match_id).starts_at, row.id)):
        if lineup.match_id not in matches:
            continue
        assignments[lineup.match_id, lineup.player_id] = lineup
        m, s = (matches[lineup.match_id], stats[lineup.player_id])
        own, opponent = (
            (m.home_score, m.away_score) if lineup.side == "home" else (m.away_score, m.home_score)
        )
        s["games"] += 1
        s["wins"] += own > opponent
        s["draws"] += own == opponent
        s["clean_sheets"] += opponent == 0
        s["form"].append("W" if own > opponent else "D" if own == opponent else "L")
    for event in db.records(MatchEvent):
        if event.match_id in matches and event.kind == "goal":
            stats[event.player_id]["goals"] += 1
            if event.assist_player_id:
                stats[event.assist_player_id]["assists"] += 1
    for rating in db.records(Rating):
        if rating.match_id in matches:
            stats[rating.player_id]["ratings"].append(rating.value)
    for rsvp in db.records(RSVP):
        if rsvp.match_id in matches and rsvp.status == "going":
            stats[rsvp.player_id]["promises"] += 1
            stats[rsvp.player_id]["attended_promises"] += (rsvp.match_id, rsvp.player_id) in assignments
    for s in stats.values():
        ratings = s.pop("ratings")
        s["rating"] = round(sum(ratings) / len(ratings), 1) if ratings else None
        s["win_rate"] = round(s["wins"] / s["games"] * 100) if s["games"] else 0
        s["attendance"] = round(s["games"] / len(matches) * 100) if matches else 0
        s["reliability"] = round(s.pop("attended_promises") / s["promises"] * 100) if s["promises"] else None
        s.pop("promises")
        s["form"] = s["form"][-5:]
    teams = []
    for team in sorted(db.records(Team), key=lambda row: row.id, reverse=False):
        result = {
            **row_dict(team),
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "goals_for": 0,
            "goals_against": 0,
            "form": [],
            "games": 0,
        }
        for m in matches.values():
            if m.kind != "classic":
                continue
            own, other = (m.home_score, m.away_score) if team.id == 1 else (m.away_score, m.home_score)
            result["games"] += 1
            result["wins"] += own > other
            result["draws"] += own == other
            result["losses"] += own < other
            result["goals_for"] += own
            result["goals_against"] += other
            result["form"].append("W" if own > other else "D" if own == other else "L")
        result["form"] = result["form"][-5:]
        teams.append(result)
    trend = defaultdict(lambda: {"matches": 0, "goals": 0, "attendance": 0})
    lineup_counts = defaultdict(int)
    for mid, _ in assignments:
        lineup_counts[mid] += 1
    for m in matches.values():
        key = m.starts_at.strftime("%Y-%m")
        trend[key]["matches"] += 1
        trend[key]["goals"] += m.home_score + m.away_score
        trend[key]["attendance"] += lineup_counts[m.id]
    return {
        "players": sorted(stats.values(), key=lambda s: (-s["goals"], -s["assists"], s["name"])),
        "teams": teams,
        "matches_played": len(matches),
        "total_goals": sum((m.home_score + m.away_score for m in matches.values())),
        "trend": [{"month": month, **values} for month, values in sorted(trend.items())],
    }


def match_summaries(db: ClubData, matches: list[Match], player_id: int):
    ids = [m.id for m in matches]
    responses = defaultdict(list)
    if ids:
        for r in [row for row in db.records(RSVP) if row.match_id in ids]:
            responses[r.match_id].append(r)
    return [
        {
            **row_dict(m),
            "going": sum((r.status == "going" for r in responses[m.id])),
            "going_player_ids": [r.player_id for r in responses[m.id] if r.status == "going"],
            "maybe": sum((r.status == "maybe" for r in responses[m.id])),
            "out": sum((r.status == "out" for r in responses[m.id])),
            "my_rsvp": next((r.status for r in responses[m.id] if r.player_id == player_id), None),
        }
        for m in matches
    ]

# AI-Assited Engineering

The codebase, configuration, docs, and project structure were created through one prompt-driven generation flow without manual reimplementation.

> Cost ~8M input/cache tokens and ~100K output tokens, roughly $20 total.


```text
Build a complete, production-ready web application called "Lex Pickup Pro" (or similar) for managing a recreational pickup soccer club.

### Core Vision
Create a modern, professional-grade club management platform for a regular group of players who organize pickup games. The same pool of players forms two fixed teams — **"Old Gentlemen"** and **"Young Boys"** — that regularly compete against each other or mix for balanced games. Although this is a casual/recreational club, the application must offer polished, data-driven features normally found in professional environments (scheduling, detailed player profiles, performance analytics, availability tracking, etc.).

Members primarily communicate via **Facebook Messenger**. The app should complement (not replace) Messenger by providing structured tools, data, and organization that chat alone cannot deliver. Include easy ways to share links, summaries, or reports into Messenger.

### Target Users
- All club members (players)
- Team captains / organizers for "Old Gentlemen" and "Young Boys"
- Optional admin/organizer role with higher privileges
- Simple role-based access (player, captain, admin)

### Essential Modules & Features

1. **Player Profiles & Roster**
   - Individual player profiles (name, nickname, preferred positions, dominant foot, age group, photo, contact preference)
   - Assignment to primary team ("Old Gentlemen" or "Young Boys") with the ability to play for either side when needed
   - Availability status and preferred playing times
   - Skill self-rating or peer-rating system (optional)
   - Injury / absence notes

2. **Team Management**
   - Dedicated views for **Old Gentlemen** and **Young Boys**
   - Squad lists, captains, and team colors/branding
   - Head-to-head history between the two teams
   - Ability to create mixed/balanced pickup games from the shared player pool

3. **Scheduling & Match Organization**
   - Calendar for regular pickup sessions and special matches
   - Create matches (Old Gentlemen vs Young Boys, or mixed sides)
   - Player availability check-ins (Going / Maybe / Not Going) with automatic reminders
   - Pitch booking notes and location details
   - Recurring game templates (e.g., every Saturday 10am)
   - Easy “Share to Messenger” buttons that generate clean summaries

4. **Match Day Tools**
   - Lineup builder / formation tool (drag-and-drop)
   - Live or post-match score & event entry (goals, assists, clean sheets, etc.)
   - Player ratings after each game
   - Quick match reports that can be copied into Facebook Messenger

5. **Performance Analytics**
   - Individual player stats (games played, goals, assists, win rate, average rating)
   - Team stats for Old Gentlemen vs Young Boys
   - Season leaders and form guides
   - Simple but polished charts and leaderboards
   - Head-to-head player comparisons
   - Attendance and reliability metrics

6. **Availability & Communication Support**
   - Central availability board
   - Automated or one-click notifications that members can forward into the Facebook Messenger group
   - Match reminders and lineup announcements designed to be Messenger-friendly
   - Optional integration notes or webhooks for future Messenger chatbot connection

7. **History & Records**
   - Full match archive
   - Career stats for every player
   - Trophy / achievement system (e.g., “Golden Boot”, “Iron Man”, “Team of the Month”)
   - Season summaries that can be exported or shared

8. **Admin & Club Tools**
   - Easy player onboarding
   - Pitch and equipment notes
   - Basic financial tracking if the group collects money for pitches or balls (optional)
   - Data export (CSV/PDF) for records

### Technical & UX Requirements
- Clean, modern, mobile-first design (most users will open it on their phones between Messenger chats)
- Fast and delightful to use — feels premium despite being for a pickup group
- Dark mode + light mode
- Beautiful data visualizations and leaderboards
- One-click sharing of matches, results, and stats into Facebook Messenger
- Progressive Web App (PWA) capabilities so it can be installed on phones
- Simple authentication (email/password or magic link; optional social login)
- Responsive and works excellently on mobile

### Required Tech Stack
**Frontend**
- Latest React (React 19) with modern toolchain
- Vite as the build tool
- TypeScript
- Tailwind CSS + modern UI component library (e.g. shadcn/ui)
- React Router
- TanStack Query (React Query) for data fetching
- Recharts or similar for analytics visualizations
- PWA support

**Backend**
- Python 3.12
- FastAPI
- SQLAlchemy 2.0 + Alembic for migrations
- PostgreSQL (or SQLite for local development)
- Pydantic v2
- JWT-based authentication
- Proper CORS and security best practices

**Other**
- Clean separation between frontend and backend
- Docker support for easy local development and deployment
- Environment-based configuration
- Comprehensive README with setup instructions for both frontend and backend

### Deliverables
1. Complete source code with clean architecture (separate frontend and backend folders)
2. Database schema and seed data featuring realistic players split between **Old Gentlemen** and **Young Boys**
3. Demo accounts (regular player + captain/admin)
4. Comprehensive README with setup instructions
5. Polished UI that makes a casual pickup group feel professionally organized
6. Clear “Share to Messenger” flows and copy-friendly summaries

Prioritize mobile usability, speed, and features that reduce the chaos of organizing games purely in a Messenger group chat. The app should make captains’ lives easier and give every player clear stats, schedules, and team identity while remaining fun and lightweight.

Start by outlining the system architecture, data models (especially the two-team structure), and main user flows before writing the code.
```



EOF
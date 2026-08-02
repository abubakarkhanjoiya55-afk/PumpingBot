# YouTube Subscriptions & Watchtime Tracker

A full-stack web application to track your YouTube subscriptions and watchtime analytics.

## Features

- **Subscription Management** — Add, edit, remove YouTube channels with categories (Tech, Gaming, Music, etc.)
- **Watch History** — Log videos you watch with duration and timestamps
- **Goals** — Set daily, weekly, or monthly watchtime goals and track progress
- **Analytics** — Interactive charts showing watchtime trends, top channels, and statistics
- **Dashboard** — At-a-glance overview of all your YouTube activity

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + SQLite |
| Frontend | React 18 + Vite |
| Charts | Recharts |
| Styling | Custom CSS (dark theme) |

## Quick Start

### Backend
```bash
cd backend
pip install -r requirements.txt
python3 -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5174` in your browser.

### Docker (optional)
```bash
docker-compose up
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/channels` | List subscribed channels |
| POST | `/api/channels` | Add a channel |
| PUT | `/api/channels/{id}` | Update channel |
| DELETE | `/api/channels/{id}` | Remove channel |
| GET | `/api/watch-logs` | Watch history |
| POST | `/api/watch-logs` | Log a video |
| GET | `/api/goals` | List goals |
| POST | `/api/goals` | Create goal |
| GET | `/api/analytics` | Analytics summary |

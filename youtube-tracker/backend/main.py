from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime, timedelta
import json

from database import get_db, init_db, Channel, WatchLog, Goal
from schemas import (
    ChannelCreate, ChannelUpdate, ChannelResponse,
    WatchLogCreate, WatchLogResponse,
    GoalCreate, GoalResponse,
    AnalyticsSummary, DailyStats, ChannelStats
)

app = FastAPI(title="YouTube Tracker API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    init_db()


# ─── Channel Endpoints ────────────────────────────────────────────────────────

@app.get("/api/channels", response_model=List[ChannelResponse])
def get_channels(
    category: Optional[str] = None,
    active_only: bool = False,
    db: Session = Depends(get_db)
):
    query = db.query(Channel)
    if active_only:
        query = query.filter(Channel.is_active == True)
    if category:
        query = query.filter(Channel.category == category)
    channels = query.order_by(Channel.name).all()

    result = []
    for ch in channels:
        total = db.query(func.sum(WatchLog.duration_minutes)).filter(
            WatchLog.channel_id == ch.id
        ).scalar() or 0.0
        count = db.query(func.count(WatchLog.id)).filter(
            WatchLog.channel_id == ch.id
        ).scalar() or 0

        ch_dict = {
            "id": ch.id,
            "channel_id": ch.channel_id,
            "name": ch.name,
            "description": ch.description,
            "thumbnail_url": ch.thumbnail_url,
            "subscriber_count": ch.subscriber_count,
            "category": ch.category,
            "url": ch.url,
            "subscribed_at": ch.subscribed_at,
            "is_active": ch.is_active,
            "total_watchtime": round(total, 2),
            "video_count": count,
        }
        result.append(ch_dict)
    return result


@app.post("/api/channels", response_model=ChannelResponse)
def create_channel(channel: ChannelCreate, db: Session = Depends(get_db)):
    existing = db.query(Channel).filter(Channel.channel_id == channel.channel_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Channel already subscribed")
    db_channel = Channel(**channel.model_dump())
    db.add(db_channel)
    db.commit()
    db.refresh(db_channel)
    return {**db_channel.__dict__, "total_watchtime": 0.0, "video_count": 0}


@app.get("/api/channels/{channel_id}", response_model=ChannelResponse)
def get_channel(channel_id: int, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    total = db.query(func.sum(WatchLog.duration_minutes)).filter(
        WatchLog.channel_id == ch.id
    ).scalar() or 0.0
    count = db.query(func.count(WatchLog.id)).filter(
        WatchLog.channel_id == ch.id
    ).scalar() or 0
    return {**ch.__dict__, "total_watchtime": round(total, 2), "video_count": count}


@app.put("/api/channels/{channel_id}", response_model=ChannelResponse)
def update_channel(channel_id: int, update: ChannelUpdate, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(ch, field, value)
    db.commit()
    db.refresh(ch)
    total = db.query(func.sum(WatchLog.duration_minutes)).filter(
        WatchLog.channel_id == ch.id
    ).scalar() or 0.0
    count = db.query(func.count(WatchLog.id)).filter(
        WatchLog.channel_id == ch.id
    ).scalar() or 0
    return {**ch.__dict__, "total_watchtime": round(total, 2), "video_count": count}


@app.delete("/api/channels/{channel_id}")
def delete_channel(channel_id: int, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    db.delete(ch)
    db.commit()
    return {"message": "Channel deleted successfully"}


@app.get("/api/categories")
def get_categories(db: Session = Depends(get_db)):
    categories = db.query(Channel.category).distinct().all()
    return [c[0] for c in categories if c[0]]


# ─── WatchLog Endpoints ───────────────────────────────────────────────────────

@app.get("/api/watch-logs", response_model=List[WatchLogResponse])
def get_watch_logs(
    channel_id: Optional[int] = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    query = db.query(WatchLog)
    if channel_id:
        query = query.filter(WatchLog.channel_id == channel_id)
    logs = query.order_by(desc(WatchLog.watched_at)).offset(offset).limit(limit).all()

    result = []
    for log in logs:
        ch = db.query(Channel).filter(Channel.id == log.channel_id).first()
        result.append({
            "id": log.id,
            "channel_id": log.channel_id,
            "video_title": log.video_title,
            "video_url": log.video_url,
            "duration_minutes": log.duration_minutes,
            "watched_at": log.watched_at,
            "notes": log.notes,
            "channel_name": ch.name if ch else "Unknown",
        })
    return result


@app.post("/api/watch-logs", response_model=WatchLogResponse)
def create_watch_log(log: WatchLogCreate, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == log.channel_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")

    log_data = log.model_dump()
    if not log_data.get("watched_at"):
        log_data["watched_at"] = datetime.utcnow()

    db_log = WatchLog(**log_data)
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return {**db_log.__dict__, "channel_name": ch.name}


@app.delete("/api/watch-logs/{log_id}")
def delete_watch_log(log_id: int, db: Session = Depends(get_db)):
    log = db.query(WatchLog).filter(WatchLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Watch log not found")
    db.delete(log)
    db.commit()
    return {"message": "Watch log deleted successfully"}


# ─── Goals Endpoints ──────────────────────────────────────────────────────────

@app.get("/api/goals", response_model=List[GoalResponse])
def get_goals(db: Session = Depends(get_db)):
    goals = db.query(Goal).filter(Goal.is_active == True).all()
    result = []
    now = datetime.utcnow()

    for goal in goals:
        if goal.period == "daily":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif goal.period == "weekly":
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        else:  # monthly
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        progress = db.query(func.sum(WatchLog.duration_minutes)).filter(
            WatchLog.watched_at >= start
        ).scalar() or 0.0

        percent = min(100, round((progress / goal.target_minutes) * 100, 1))
        result.append({
            **goal.__dict__,
            "progress_minutes": round(progress, 2),
            "progress_percent": percent,
        })
    return result


@app.post("/api/goals", response_model=GoalResponse)
def create_goal(goal: GoalCreate, db: Session = Depends(get_db)):
    db_goal = Goal(**goal.model_dump())
    db.add(db_goal)
    db.commit()
    db.refresh(db_goal)
    return {**db_goal.__dict__, "progress_minutes": 0.0, "progress_percent": 0.0}


@app.delete("/api/goals/{goal_id}")
def delete_goal(goal_id: int, db: Session = Depends(get_db)):
    goal = db.query(Goal).filter(Goal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    goal.is_active = False
    db.commit()
    return {"message": "Goal deleted"}


# ─── Analytics Endpoints ──────────────────────────────────────────────────────

@app.get("/api/analytics", response_model=AnalyticsSummary)
def get_analytics(days: int = Query(default=30, le=365), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    since = now - timedelta(days=days)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    total_minutes = db.query(func.sum(WatchLog.duration_minutes)).scalar() or 0.0
    total_videos = db.query(func.count(WatchLog.id)).scalar() or 0
    total_subs = db.query(func.count(Channel.id)).scalar() or 0
    active_subs = db.query(func.count(Channel.id)).filter(Channel.is_active == True).scalar() or 0

    this_week = db.query(func.sum(WatchLog.duration_minutes)).filter(
        WatchLog.watched_at >= week_start
    ).scalar() or 0.0

    this_month = db.query(func.sum(WatchLog.duration_minutes)).filter(
        WatchLog.watched_at >= month_start
    ).scalar() or 0.0

    # Daily stats for last N days
    daily_data = {}
    for i in range(days):
        date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_data[date] = {"date": date, "total_minutes": 0.0, "video_count": 0}

    logs_in_range = db.query(WatchLog).filter(WatchLog.watched_at >= since).all()
    for log in logs_in_range:
        date = log.watched_at.strftime("%Y-%m-%d")
        if date in daily_data:
            daily_data[date]["total_minutes"] += log.duration_minutes
            daily_data[date]["video_count"] += 1

    daily_stats = sorted(daily_data.values(), key=lambda x: x["date"])

    # Channel stats
    channel_rows = db.query(
        WatchLog.channel_id,
        func.sum(WatchLog.duration_minutes).label("total"),
        func.count(WatchLog.id).label("count")
    ).group_by(WatchLog.channel_id).order_by(desc("total")).limit(10).all()

    channel_stats = []
    for row in channel_rows:
        ch = db.query(Channel).filter(Channel.id == row.channel_id).first()
        pct = round((row.total / total_minutes * 100) if total_minutes > 0 else 0, 1)
        channel_stats.append({
            "channel_id": row.channel_id,
            "channel_name": ch.name if ch else "Unknown",
            "total_minutes": round(row.total, 2),
            "video_count": row.count,
            "percentage": pct,
        })

    days_with_data = len([d for d in daily_stats if d["total_minutes"] > 0]) or 1
    avg_daily = round(total_minutes / max(days_with_data, 1), 2)
    top_channel = channel_stats[0]["channel_name"] if channel_stats else None

    return {
        "total_watchtime_minutes": round(total_minutes, 2),
        "total_watchtime_hours": round(total_minutes / 60, 2),
        "total_videos_watched": total_videos,
        "total_subscriptions": total_subs,
        "active_subscriptions": active_subs,
        "avg_daily_minutes": avg_daily,
        "top_channel": top_channel,
        "this_week_minutes": round(this_week, 2),
        "this_month_minutes": round(this_month, 2),
        "daily_stats": daily_stats,
        "channel_stats": channel_stats,
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "YouTube Tracker API"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)

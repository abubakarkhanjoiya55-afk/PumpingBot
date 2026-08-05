from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# Channel Schemas
class ChannelBase(BaseModel):
    name: str
    channel_id: str
    description: Optional[str] = ""
    thumbnail_url: Optional[str] = ""
    subscriber_count: Optional[str] = "0"
    category: Optional[str] = "General"
    url: Optional[str] = ""


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    subscriber_count: Optional[str] = None
    category: Optional[str] = None
    url: Optional[str] = None
    is_active: Optional[bool] = None


class ChannelResponse(ChannelBase):
    id: int
    subscribed_at: datetime
    is_active: bool
    total_watchtime: Optional[float] = 0.0
    video_count: Optional[int] = 0

    class Config:
        from_attributes = True


# WatchLog Schemas
class WatchLogBase(BaseModel):
    video_title: str
    video_url: Optional[str] = ""
    duration_minutes: float = Field(gt=0)
    notes: Optional[str] = ""


class WatchLogCreate(WatchLogBase):
    channel_id: int
    watched_at: Optional[datetime] = None


class WatchLogResponse(WatchLogBase):
    id: int
    channel_id: int
    watched_at: datetime
    channel_name: Optional[str] = None

    class Config:
        from_attributes = True


# Goal Schemas
class GoalBase(BaseModel):
    title: str
    target_minutes: float = Field(gt=0)
    period: str = "weekly"


class GoalCreate(GoalBase):
    pass


class GoalResponse(GoalBase):
    id: int
    created_at: datetime
    is_active: bool
    progress_minutes: Optional[float] = 0.0
    progress_percent: Optional[float] = 0.0

    class Config:
        from_attributes = True


# Analytics Schemas
class DailyStats(BaseModel):
    date: str
    total_minutes: float
    video_count: int


class ChannelStats(BaseModel):
    channel_id: int
    channel_name: str
    total_minutes: float
    video_count: int
    percentage: float


class AnalyticsSummary(BaseModel):
    total_watchtime_minutes: float
    total_watchtime_hours: float
    total_videos_watched: int
    total_subscriptions: int
    active_subscriptions: int
    avg_daily_minutes: float
    top_channel: Optional[str] = None
    this_week_minutes: float
    this_month_minutes: float
    daily_stats: List[DailyStats]
    channel_stats: List[ChannelStats]

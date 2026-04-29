from sqlalchemy import Column, String, Boolean, Integer, JSON
from pydantic import BaseModel
from typing import List, Optional
from database import Base

# SQLAlchemy Model (DB Table)
class Activity(Base):
    __tablename__ = "activities"

    id = Column(String, primary_key=True, index=True)
    date = Column(String, nullable=False)
    time = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, default="")
    location = Column(String, default="")
    observations = Column(String, default="")
    responsible = Column(String, default="")
    external_name = Column(String, default="")
    channels = Column(JSON, default=list) # Stores the list of channels
    done = Column(Boolean, default=False)
    drive_bcr = Column(String, default="")
    drive_santiago = Column(String, default="")
    copy_instagram = Column(String, default="")
    copy_linkedin = Column(String, default="")
    participants = Column(String, default="")
    story_type = Column(String, default="Video")
    conectados_title = Column(String, default="")
    conectados_text = Column(String, default="")
    is_custom = Column(Boolean, default=False)
    order_index = Column(Integer, default=0)

# Pydantic Models (API Validation)
class ActivityBase(BaseModel):
    id: str
    date: str
    time: str
    title: str
    description: Optional[str] = ""
    location: Optional[str] = ""
    observations: Optional[str] = ""
    responsible: Optional[str] = ""
    external_name: Optional[str] = ""
    channels: List[str] = []
    done: Optional[bool] = False
    drive_bcr: Optional[str] = ""
    drive_santiago: Optional[str] = ""
    copy_instagram: Optional[str] = ""
    copy_linkedin: Optional[str] = ""
    participants: Optional[str] = ""
    story_type: Optional[str] = "Video"
    conectados_title: Optional[str] = ""
    conectados_text: Optional[str] = ""
    is_custom: Optional[bool] = False
    order_index: Optional[int] = 0

class ActivityCreate(ActivityBase):
    pass

class ActivityUpdate(BaseModel):
    date: Optional[str] = None
    time: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    observations: Optional[str] = None
    responsible: Optional[str] = None
    external_name: Optional[str] = None
    channels: Optional[List[str]] = None
    done: Optional[bool] = None
    drive_bcr: Optional[str] = None
    drive_santiago: Optional[str] = None
    copy_instagram: Optional[str] = None
    copy_linkedin: Optional[str] = None
    participants: Optional[str] = None
    story_type: Optional[str] = None
    conectados_title: Optional[str] = None
    conectados_text: Optional[str] = None
    is_custom: Optional[bool] = None
    order_index: Optional[int] = None

class ActivityOut(ActivityBase):
    class Config:
        from_attributes = True

class GenerateCopyRequest(BaseModel):
    mode: str  # 'ig' or 'li'
    title: str
    description: Optional[str] = ""
    observations: Optional[str] = ""
    participants_enriched: Optional[str] = ""

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime
import pytz

# 用户模型类，对应数据库表users
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    email = Column(String(100), unique=True, index=True)
    password_hash = Column(String(100))

    conversations = relationship("Conversation", back_populates="user")

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    filename = Column(String(255))
    file_path = Column(String(255))
    transcript_path = Column(String(255))
    notes_path = Column(String(255))
    quiz_path = Column(String(255))
    messages = Column(Text) #存储JSON格式聊天记录
    created_at = Column(
        DateTime, default=lambda: datetime.now(pytz.timezone("Asia/Shanghai"))
    )

    user = relationship("User", back_populates="conversations")

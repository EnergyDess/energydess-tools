from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

SQLALCHEMY_DATABASE_URL = "sqlite:///./app.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)
    display_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Resume(Base):
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False)
    resume_text = Column(Text, default="")


class ToolAccess(Base):
    __tablename__ = "tool_access"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    tool_id = Column(String, nullable=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)

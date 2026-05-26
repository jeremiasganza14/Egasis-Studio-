import os
import datetime
import threading
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), 'outreach.db'))
# Asegurar que el directorio de la base de datos existe (útil para discos persistentes)
db_dir = os.path.dirname(DB_PATH)
if db_dir:
    os.makedirs(db_dir, exist_ok=True)

engine = create_engine(f'sqlite:///{DB_PATH}', connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Global reentrant thread lock for database synchronization to prevent SQLite database is locked errors and nested deadlocks
db_lock = threading.RLock()

class ProcessedBusiness(Base):
    __tablename__ = "processed_businesses"
    
    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, unique=True, index=True, nullable=False)
    scraped_at = Column(DateTime, default=datetime.datetime.utcnow)

class Lead(Base):
    __tablename__ = "leads"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, default="Equipo")
    company = Column(String, default="su empresa")
    source = Column(String, default="manual")  # ej. google_maps, csv
    status = Column(String, default="pending") # pending, sent, failed, replied, do_not_contact
    
    attempt_count = Column(Integer, default=0)
    last_attempt = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    sent_emails = relationship("SentEmail", back_populates="lead")
    replies = relationship("Reply", back_populates="lead")

class SentEmail(Base):
    __tablename__ = "sent_emails"
    
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    sent_at = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String, default="sent") # sent, bounced
    
    lead = relationship("Lead", back_populates="sent_emails")

class Reply(Base):
    __tablename__ = "replies"
    
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    from_email = Column(String, nullable=False)
    subject = Column(String)
    body = Column(Text)
    received_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # AI Classification
    classification = Column(String, default="unclassified") # interested, not_interested, out_of_office, info_requested, unclassified
    priority = Column(String, default="medium") # high, medium, low
    processed_status = Column(String, default="unread") # unread, read, replied, pending_approval
    
    proposed_subject = Column(String, nullable=True)
    proposed_reply = Column(Text, nullable=True)
    
    lead = relationship("Lead", back_populates="replies")

class Learning(Base):
    __tablename__ = "learnings"
    
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Setting(Base):
    __tablename__ = "settings"
    
    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)

# Crear tablas
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper para cargar la configuración
def get_setting(db_session, key, default_value=""):
    setting = db_session.query(Setting).filter(Setting.key == key).first()
    if setting:
        return setting.value
    return default_value

def set_setting(db_session, key, value):
    setting = db_session.query(Setting).filter(Setting.key == key).first()
    if setting:
        setting.value = str(value)
    else:
        new_setting = Setting(key=key, value=str(value))
        db_session.add(new_setting)
    db_session.commit()

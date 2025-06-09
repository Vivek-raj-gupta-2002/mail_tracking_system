from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
import uuid
import io
from datetime import datetime
from sqlalchemy import create_engine, Column, String, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pydantic import BaseModel, EmailStr
import aiosmtplib
from email.message import EmailMessage
from dotenv import load_dotenv
import os
load_dotenv()

app = FastAPI()

# Database setup
DATABASE_URL = "sqlite:///./emails.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Email log model
class EmailLog(Base):
    __tablename__ = "email_logs"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True)
    tracking_id = Column(String, unique=True, index=True)
    sent_at = Column(DateTime)
    opened_at = Column(DateTime, nullable=True)
    ip = Column(String, nullable=True)

Base.metadata.create_all(bind=engine)

# Request model for sending email
class EmailRequest(BaseModel):
    email: EmailStr

# Endpoint to send email
@app.post("/send_email")
async def send_email(request: Request, email_request: EmailRequest):
    db = SessionLocal()
    tracking_id = str(uuid.uuid4())
    host = request.headers.get("host")
    scheme = "https" if request.url.scheme == "https" else "http"
    tracking_url = f"{scheme}://{host}/track/{tracking_id}.png"
    msg = EmailMessage()
    msg["Subject"] = "Tracked Email"
    msg["From"] = os.getenv("EMAIL_DEFAULT_SENDER")
    msg["To"] = email_request.email
    html_body = f"<html><body>Hello!<br><img src='{tracking_url}' width='1' height='1' style='display:none;'></body></html>"
    msg.set_content("Hello! (HTML version required)")
    msg.add_alternative(html_body, subtype="html")
    await aiosmtplib.send(
        msg,
        hostname=os.getenv("EMAIL_HOST"),
        port=587,
        username=os.getenv("EMAIL_USERNAME"),
        password=os.getenv("EMAIL_PASSWORD"),
        start_tls=True
    )
    log = EmailLog(email=email_request.email, tracking_id=tracking_id, sent_at=datetime.utcnow())
    db.add(log)
    db.commit()
    db.close()
    return {"status": "sent", "tracking_id": tracking_id}

# Endpoint to track email opens
@app.get("/track/{tracking_id}.png")
def track_email(tracking_id: str, request: Request):
    db = SessionLocal()
    log = db.query(EmailLog).filter(EmailLog.tracking_id == tracking_id).first()
    if log and log.opened_at is None:
        # Use setattr for both opened_at and ip to avoid type issues
        setattr(log, 'opened_at', datetime.utcnow())
        ip = getattr(request.client, 'host', '') or ''
        setattr(log, 'ip', ip)
        db.commit()
    db.close()
    # 1x1 transparent PNG
    pixel = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0bIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\x0d\n\x2d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    return Response(content=pixel, media_type="image/png")

# Endpoint to get log details
@app.get("/log/{tracking_id}")
def get_log(tracking_id: str):
    db = SessionLocal()
    log = db.query(EmailLog).filter(EmailLog.tracking_id == tracking_id).first()
    db.close()
    if log:
        return {
            "email": log.email,
            "sent_at": log.sent_at,
            "opened_at": log.opened_at,
            "ip": log.ip
        }
    return {"status": "not found"}

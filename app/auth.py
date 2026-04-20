from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Cookie, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
import os

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/admin/token", auto_error=False)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_user_from_token(token: str, db: Session) -> Optional[models.User]:
    payload = decode_token(token)
    if not payload:
        return None
    username = payload.get("sub")
    if not username:
        return None
    return db.query(models.User).filter(models.User.username == username).first()


def get_token_from_request(request: Request) -> Optional[str]:
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        return token[7:]
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def require_admin(request: Request, db: Session = Depends(get_db)) -> models.User:
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    user = get_user_from_token(token, db)
    if not user or user.role not in (models.UserRole.admin, models.UserRole.superadmin):
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    return user


def require_superadmin(request: Request, db: Session = Depends(get_db)) -> models.User:
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    user = get_user_from_token(token, db)
    if not user or user.role != models.UserRole.superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    return user


def require_referee(request: Request, db: Session = Depends(get_db)) -> models.User:
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=302, headers={"Location": "/schiri/login"})
    user = get_user_from_token(token, db)
    if not user or user.role not in (models.UserRole.referee, models.UserRole.admin, models.UserRole.superadmin):
        raise HTTPException(status_code=302, headers={"Location": "/schiri/login"})
    return user


def authenticate_user(username: str, password: str, db: Session) -> Optional[models.User]:
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return None
    return user

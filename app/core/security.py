from datetime import datetime, timedelta, timezone
import jwt

SECRET_KEY = "PLACEHOLDER_SECRET_KEY"
ALGORITHM = "HS256"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Placeholder
    return plain_password == hashed_password

def get_password_hash(password: str) -> str:
    # Placeholder
    return password

def create_access_token(subject: str | int, expires_delta: timedelta | None = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
        
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

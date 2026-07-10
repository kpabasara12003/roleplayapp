#fastapi_server/app/api/users.py
import secrets

from fastapi import APIRouter, HTTPException, Header
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from shared.db.postgres import fetch_one, execute_returning
from shared.models.user import UserRegister, UserLogin, UserOut
from shared.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])
ph = PasswordHasher()


def _generate_api_key() -> str:
    return secrets.token_urlsafe(32)


@router.post("/register", response_model=UserOut, status_code=201)
async def register_user(payload: UserRegister):
    """Register a new user and return an API key."""
    existing = await fetch_one(
        "SELECT id FROM users WHERE username = %s", (payload.username,)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")

    if payload.email:
        email_exists = await fetch_one(
            "SELECT id FROM users WHERE email = %s", (payload.email,)
        )
        if email_exists:
            raise HTTPException(status_code=409, detail="Email already registered")

    password_hash = ph.hash(payload.password)
    api_key = _generate_api_key()

    user = await execute_returning(
        """
        INSERT INTO users (username, password_hash, email, api_key)
        VALUES (%s, %s, %s, %s)
        RETURNING id, username, email, api_key, created_at
        """,
        (payload.username, password_hash, payload.email, api_key),
    )
    if not user:
        raise HTTPException(status_code=500, detail="Failed to create user")

    logger.info("User registered: %s", payload.username)
    return user


@router.post("/login", response_model=UserOut)
async def login_user(payload: UserLogin):
    """Authenticate and return user details including API key."""
    user = await fetch_one(
        """
        SELECT id, username, email, api_key, created_at, password_hash
        FROM users WHERE username = %s
        """,
        (payload.username,),
    )
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    try:
        ph.verify(user["password_hash"], payload.password)
    except VerifyMismatchError:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "api_key": user["api_key"],
        "created_at": user["created_at"],
    }


async def get_current_user(x_api_key: str = Header(...)) -> dict:
    """Dependency to resolve current user from X-API-Key header."""
    user = await fetch_one(
        "SELECT id, username, email, created_at FROM users WHERE api_key = %s",
        (x_api_key,),
    )
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return user

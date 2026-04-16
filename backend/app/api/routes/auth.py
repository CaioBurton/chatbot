from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_db
from app.models.user import User
from app.schemas.document import LoginRequest, TokenResponse
from app.core.security import create_access_token, create_refresh_token

router = APIRouter(prefix="/auth", tags=["auth"])

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pre-computed bcrypt hash used as a dummy target when the requested user does
# not exist.  Running the full bcrypt check even on a miss ensures the response
# time is indistinguishable from a wrong-password case, preventing user
# enumeration via timing side-channels (CWE-208).
_DUMMY_HASH = "$2b$12$GhvMmNVjRW29ulnudl.LbuAnUtN/LRfe1JsBm1Xu6LE3AjsrZ0PXi"


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    # Always run bcrypt (even when the user is not found) so response time is
    # constant regardless of whether the email exists in the database.
    hash_to_check = user.password_hash if user is not None else _DUMMY_HASH
    password_ok = _pwd_context.verify(request.password, hash_to_check)

    if user is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = {"sub": user.email, "role": user.role}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )

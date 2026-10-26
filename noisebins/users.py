import uuid

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, schemas
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, CookieTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from noisebins.config import get_settings
from noisebins.db import get_db
from noisebins.models import OAuthAccount, User

settings = get_settings()


class UserRead(schemas.BaseUser[uuid.UUID]):
    display_name: str | None = None


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    pass


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.secret_key
    verification_token_secret = settings.secret_key

    async def on_after_register(self, user: User, request: Request | None = None):
        return


async def get_user_db(session: AsyncSession = Depends(get_db)):
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)


def get_jwt_strategy() -> JWTStrategy[User, uuid.UUID]:
    return JWTStrategy(
        secret=settings.users_jwt_secret,
        lifetime_seconds=settings.access_token_expire_minutes * 60,
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=BearerTransport(tokenUrl="auth/jwt/login"),
    get_strategy=get_jwt_strategy,
)

# Browser session set by the Noiseport SSO callback. Same JWT strategy, carried in an
# HttpOnly SameSite=Lax cookie so pages and same-origin fetches are authenticated.
cookie_backend = AuthenticationBackend(
    name="cookie",
    transport=CookieTransport(
        cookie_name=settings.session_cookie_name,
        cookie_max_age=settings.access_token_expire_minutes * 60,
        cookie_secure=settings.session_cookie_secure_effective,
        cookie_samesite="lax",
    ),
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend, cookie_backend])
current_active_user = fastapi_users.current_user(active=True)
optional_current_user = fastapi_users.current_user(optional=True, active=True)

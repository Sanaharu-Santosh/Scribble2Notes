"""Who is making this request.

**There is no sign-in yet.** Every request resolves to a single local account,
created on first use. That is a deliberate stopping point rather than an
oversight: hand-rolling password auth for a solo project is a bad trade (see
docs/architecture.md), and wiring a managed provider needs an account and keys
that belong to whoever deploys this.

What matters is that the *schema* is already multi-user. Pages carry an owner,
every query filters by it, and someone else's page returns 404 rather than 403
so its existence doesn't leak. So adding Supabase or Clerk later means replacing
the body of :func:`current_user` with "verify the bearer token, look up or create
the user it names" — not reshaping the database or revisiting every query.

Until then, do not deploy this to a public URL and treat it as private. It isn't
insecure so much as unauthenticated: anyone who can reach the API is the user.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import User


async def current_user(session: AsyncSession) -> User:
    """Resolve the requesting user, creating the local account on first use."""
    email = get_settings().dev_user_email

    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        return existing

    user = User(email=email, display_name="Local user")
    session.add(user)
    await session.flush()  # assigns the id without ending the request's transaction
    return user

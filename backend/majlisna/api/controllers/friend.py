from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.models.friendship import Friendship, FriendshipStatus
from majlisna.api.models.table import User
from majlisna.api.schemas.error import (
    AlreadyFriendsError,
    CannotFriendYourselfError,
    FriendRequestAlreadySentError,
    FriendRequestBlockedError,
    FriendRequestFailedError,
    FriendRequestNotPendingError,
    FriendshipNotFoundError,
    NotYourFriendRequestError,
    NotYourFriendshipError,
    UserNotFoundError,
)
from majlisna.api.schemas.friend import FriendEntry, FriendshipStatusEnum, FriendshipStatusResponse


class FriendController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def send_request(self, requester_id: UUID, addressee_id: UUID) -> Friendship:
        """Send a friend request."""
        if requester_id == addressee_id:
            raise CannotFriendYourselfError()

        # Check addressee exists
        addressee = (await self.session.exec(select(User).where(User.id == addressee_id))).first()
        if not addressee:
            raise UserNotFoundError(user_id=addressee_id)

        # Check for existing friendship in either direction
        existing = (
            await self.session.exec(
                select(Friendship).where(
                    or_(
                        (Friendship.requester_id == requester_id) & (Friendship.addressee_id == addressee_id),
                        (Friendship.requester_id == addressee_id) & (Friendship.addressee_id == requester_id),
                    )
                )
            )
        ).first()

        if existing:
            if existing.status == FriendshipStatus.BLOCKED:
                raise FriendRequestBlockedError()
            if existing.status == FriendshipStatus.ACCEPTED:
                raise AlreadyFriendsError()
            if existing.status == FriendshipStatus.PENDING:
                # If they sent us a request, auto-accept
                if existing.requester_id == addressee_id:
                    existing.status = FriendshipStatus.ACCEPTED
                    existing.updated_at = datetime.now(UTC)
                    self.session.add(existing)
                    await self.session.commit()
                    await self.session.refresh(existing)
                    return existing
                raise FriendRequestAlreadySentError()

        try:
            friendship = Friendship(requester_id=requester_id, addressee_id=addressee_id)
            self.session.add(friendship)
            await self.session.commit()
            await self.session.refresh(friendship)
            return friendship
        except IntegrityError:
            raise FriendRequestFailedError() from None

    async def accept_request(self, friendship_id: UUID, user_id: UUID) -> Friendship:
        """Accept a pending friend request."""
        friendship = await self._get_friendship(friendship_id)
        if friendship.addressee_id != user_id:
            raise NotYourFriendRequestError(action="accept")
        if friendship.status != FriendshipStatus.PENDING:
            raise FriendRequestNotPendingError()
        friendship.status = FriendshipStatus.ACCEPTED
        friendship.updated_at = datetime.now(UTC)
        self.session.add(friendship)
        await self.session.commit()
        await self.session.refresh(friendship)
        return friendship

    async def reject_request(self, friendship_id: UUID, user_id: UUID) -> None:
        """Reject and delete a pending friend request."""
        friendship = await self._get_friendship(friendship_id)
        if friendship.addressee_id != user_id:
            raise NotYourFriendRequestError(action="reject")
        await self.session.delete(friendship)
        await self.session.commit()

    async def remove_friend(self, friendship_id: UUID, user_id: UUID) -> None:
        """Remove an existing friendship."""
        friendship = await self._get_friendship(friendship_id)
        if user_id not in {friendship.requester_id, friendship.addressee_id}:
            raise NotYourFriendshipError()
        await self.session.delete(friendship)
        await self.session.commit()

    async def get_friends(self, user_id: UUID) -> Sequence[FriendEntry]:
        """Get all accepted friends for a user."""
        results = (
            await self.session.exec(
                select(Friendship).where(
                    or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id),
                    Friendship.status == FriendshipStatus.ACCEPTED,
                )
            )
        ).all()

        # Batch-fetch friend usernames in a single query to avoid N+1.
        friend_uids = [f.addressee_id if f.requester_id == user_id else f.requester_id for f in results]
        users = (await self.session.exec(select(User).where(User.id.in_(friend_uids)))).all() if friend_uids else []  # ty: ignore[unresolved-attribute]
        username_by_id = {u.id: u.username for u in users}

        friends: list[FriendEntry] = []
        for f in results:
            friend_uid = f.addressee_id if f.requester_id == user_id else f.requester_id
            username = username_by_id.get(friend_uid)
            if username is not None:
                friends.append(
                    FriendEntry(
                        friendship_id=f.id,
                        user_id=friend_uid,
                        username=username,
                        status=f.status.value,
                    )
                )
        return friends

    async def get_pending_requests(self, user_id: UUID) -> Sequence[FriendEntry]:
        """Get pending friend requests sent TO this user."""
        results = (
            await self.session.exec(
                select(Friendship).where(
                    Friendship.addressee_id == user_id,
                    Friendship.status == FriendshipStatus.PENDING,
                )
            )
        ).all()

        # Batch-fetch requester usernames in a single query to avoid N+1.
        requester_ids = [f.requester_id for f in results]
        users = (await self.session.exec(select(User).where(User.id.in_(requester_ids)))).all() if requester_ids else []  # ty: ignore[unresolved-attribute]
        username_by_id = {u.id: u.username for u in users}

        entries: list[FriendEntry] = []
        for f in results:
            username = username_by_id.get(f.requester_id)
            if username is not None:
                entries.append(
                    FriendEntry(
                        friendship_id=f.id,
                        user_id=f.requester_id,
                        username=username,
                        status=f.status.value,
                    )
                )
        return entries

    async def get_friendship_status(self, current_user_id: UUID, other_user_id: UUID) -> FriendshipStatusResponse:
        """Check friendship status between current user and another user."""
        existing = (
            await self.session.exec(
                select(Friendship).where(
                    or_(
                        (Friendship.requester_id == current_user_id) & (Friendship.addressee_id == other_user_id),
                        (Friendship.requester_id == other_user_id) & (Friendship.addressee_id == current_user_id),
                    )
                )
            )
        ).first()

        if not existing:
            return FriendshipStatusResponse(status=FriendshipStatusEnum.NONE)

        fid = str(existing.id)
        if existing.status == FriendshipStatus.ACCEPTED:
            return FriendshipStatusResponse(status=FriendshipStatusEnum.ACCEPTED, friendship_id=fid)
        if existing.status == FriendshipStatus.BLOCKED:
            return FriendshipStatusResponse(status=FriendshipStatusEnum.BLOCKED, friendship_id=fid)
        # Pending — distinguish direction
        if existing.requester_id == current_user_id:
            return FriendshipStatusResponse(status=FriendshipStatusEnum.PENDING_SENT, friendship_id=fid)
        return FriendshipStatusResponse(status=FriendshipStatusEnum.PENDING_RECEIVED, friendship_id=fid)

    async def _get_friendship(self, friendship_id: UUID) -> Friendship:
        """Get a friendship by ID or raise."""
        result = (await self.session.exec(select(Friendship).where(Friendship.id == friendship_id))).first()
        if not result:
            raise FriendshipNotFoundError()
        return result

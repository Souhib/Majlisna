import random
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError, NoResultFound
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.models.codenames import (
    CodenamesWord,
    CodenamesWordCreate,
    CodenamesWordPack,
    CodenamesWordPackCreate,
)


class CodenamesWordPackNotFoundError(Exception):
    """Raised when a word pack is not found."""

    def __init__(self, pack_id: UUID):
        self.pack_id = pack_id
        super().__init__(f"Word pack with id {pack_id} not found")


class CodenamesWordNotFoundError(Exception):
    """Raised when a word is not found."""

    def __init__(self, word_id: UUID):
        self.word_id = word_id
        super().__init__(f"Word with id {word_id} not found")


class CodenamesWordPackAlreadyExistsError(Exception):
    """Raised when a word pack with the same name already exists."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Word pack with name '{name}' already exists")


class NotEnoughWordsError(Exception):
    """Raised when there are not enough words to fill the board."""

    def __init__(self, requested: int, available: int):
        self.requested = requested
        self.available = available
        super().__init__(f"Not enough words: requested {requested}, available {available}")


class CodenamesController:
    def __init__(self, session: AsyncSession):
        self.session = session

    # --- Word Pack CRUD ---

    async def create_word_pack(self, word_pack_create: CodenamesWordPackCreate) -> CodenamesWordPack:
        """Create a new word pack.

        :param word_pack_create: The word pack data to create.
        :return: The created word pack.
        :raises CodenamesWordPackAlreadyExistsError: If a pack with the same name exists.
        """
        try:
            new_pack = CodenamesWordPack(
                name=word_pack_create.name,
                description=word_pack_create.description,
            )
            self.session.add(new_pack)
            await self.session.commit()
            await self.session.refresh(new_pack)
            return new_pack
        except IntegrityError:
            await self.session.rollback()
            raise CodenamesWordPackAlreadyExistsError(name=word_pack_create.name) from None

    async def get_word_packs(self) -> Sequence[CodenamesWordPack]:
        """Get all word packs.

        :return: List of all word packs.
        """
        return (await self.session.exec(select(CodenamesWordPack))).all()

    async def get_word_pack(self, pack_id: UUID) -> CodenamesWordPack:
        """Get a word pack by ID.

        :param pack_id: The UUID of the word pack.
        :return: The word pack.
        :raises CodenamesWordPackNotFoundError: If the pack is not found.
        """
        try:
            return (await self.session.exec(select(CodenamesWordPack).where(CodenamesWordPack.id == pack_id))).one()
        except NoResultFound:
            raise CodenamesWordPackNotFoundError(pack_id=pack_id) from None

    async def delete_word_pack(self, pack_id: UUID) -> None:
        """Delete a word pack by ID.

        :param pack_id: The UUID of the word pack to delete.
        :raises CodenamesWordPackNotFoundError: If the pack is not found.
        """
        try:
            db_pack = (await self.session.exec(select(CodenamesWordPack).where(CodenamesWordPack.id == pack_id))).one()
            await self.session.delete(db_pack)
            await self.session.commit()
        except NoResultFound:
            raise CodenamesWordPackNotFoundError(pack_id=pack_id) from None

    # --- Word CRUD ---

    async def add_word(self, word_create: CodenamesWordCreate, word_pack_id: UUID) -> CodenamesWord:
        """Add a word to a word pack.

        :param word_create: The word data.
        :param word_pack_id: The UUID of the word pack to add the word to.
        :return: The created word.
        :raises CodenamesWordPackNotFoundError: If the pack is not found.
        """
        # Verify the word pack exists
        await self.get_word_pack(word_pack_id)

        new_word = CodenamesWord(
            word=word_create.word,
            word_pack_id=word_pack_id,
        )
        self.session.add(new_word)
        await self.session.commit()
        await self.session.refresh(new_word)
        return new_word

    async def get_words_by_pack(self, word_pack_id: UUID) -> Sequence[CodenamesWord]:
        """Get all words in a word pack.

        :param word_pack_id: The UUID of the word pack.
        :return: List of words in the pack.
        :raises CodenamesWordPackNotFoundError: If the pack is not found.
        """
        # Verify the word pack exists
        await self.get_word_pack(word_pack_id)

        return (await self.session.exec(select(CodenamesWord).where(CodenamesWord.word_pack_id == word_pack_id))).all()

    async def delete_word(self, word_id: UUID) -> None:
        """Delete a word by ID.

        :param word_id: The UUID of the word to delete.
        :raises CodenamesWordNotFoundError: If the word is not found.
        """
        try:
            db_word = (await self.session.exec(select(CodenamesWord).where(CodenamesWord.id == word_id))).one()
            await self.session.delete(db_word)
            await self.session.commit()
        except NoResultFound:
            raise CodenamesWordNotFoundError(word_id=word_id) from None

    async def get_random_words(self, count: int = 25, pack_ids: list[UUID] | None = None) -> list[CodenamesWord]:
        """Get random words for building a Codenames board.

        :param count: Number of words to retrieve (default 25).
        :param pack_ids: Optional list of word pack IDs to draw from. If None, draws from all active packs.
        :return: List of randomly selected words.
        :raises NotEnoughWordsError: If there aren't enough words available.
        """
        if pack_ids:
            query = select(CodenamesWord).where(CodenamesWord.word_pack_id.in_(pack_ids))  # type: ignore[union-attr]
        else:
            # Get words from all active packs
            active_pack_ids_query = select(CodenamesWordPack.id).where(
                CodenamesWordPack.is_active == True  # noqa: E712
            )
            active_pack_ids = (await self.session.exec(active_pack_ids_query)).all()
            if not active_pack_ids:
                raise NotEnoughWordsError(requested=count, available=0)
            query = select(CodenamesWord).where(CodenamesWord.word_pack_id.in_(active_pack_ids))  # type: ignore[union-attr]

        all_words = list((await self.session.exec(query)).all())

        if len(all_words) < count:
            raise NotEnoughWordsError(requested=count, available=len(all_words))

        return random.sample(all_words, count)

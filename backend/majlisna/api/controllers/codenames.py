from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError, NoResultFound
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.models.codenames import (
    CodenamesWord,
    CodenamesWordCreate,
    CodenamesWordPack,
    CodenamesWordPackCreate,
)
from majlisna.api.utils.draw import in_draw_order
from majlisna.api.utils.rng import rng


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

        Read from the database every time: it used to sit in TTLCache for an hour as
        ORM rows, which a write on another worker never invalidated.

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
        """Get random words for building a Codenames board, in drawn (card) order.

        Reads the candidates' ids and texts, draws, then fetches only the drawn rows.

        :param count: Number of words to retrieve (default 25).
        :param pack_ids: Optional list of word pack IDs to draw from. If None, draws from all active packs.
        :return: List of randomly selected words.
        :raises NotEnoughWordsError: If there aren't enough words available.
        """
        candidates = select(col(CodenamesWord.id), col(CodenamesWord.word))
        if pack_ids:
            candidates = candidates.where(col(CodenamesWord.word_pack_id).in_(pack_ids))
        else:
            candidates = candidates.join(
                CodenamesWordPack, col(CodenamesWord.word_pack_id) == col(CodenamesWordPack.id)
            ).where(col(CodenamesWordPack.is_active).is_(True))
        pool = (await self.session.exec(candidates)).all()

        # Distinct by word TEXT, not by row. The same word can exist in more than one
        # pack — and did: the seed data carried Ikhlas, Tafsir and Tajweed twice — so
        # sampling rows could deal the same word onto two of the 25 cards. That makes
        # the game unplayable rather than merely odd: a one-word clue cannot say which
        # of the two identical cards the spymaster meant, and anything addressing a
        # card by its word (the UI, the E2E suite) hits whichever it finds first.
        # ~4% of boards were affected.
        id_by_text: dict[str, UUID] = {}
        for word_id, text in pool:
            id_by_text.setdefault(text, word_id)

        if len(id_by_text) < count:
            raise NotEnoughWordsError(requested=count, available=len(id_by_text))

        drawn_ids = rng.sample(list(id_by_text.values()), count)
        rows = (await self.session.exec(select(CodenamesWord).where(col(CodenamesWord.id).in_(drawn_ids)))).all()
        words = in_draw_order(rows, drawn_ids)
        # A drawn word deleted between the two reads would leave a hole in the board.
        if len(words) < count:
            raise NotEnoughWordsError(requested=count, available=len(words))
        return words

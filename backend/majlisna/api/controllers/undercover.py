from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError, NoResultFound
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.models.error import (
    TermPairAlreadyExistsError,
    TermPairNotFoundError,
    WordAlreadyExistsError,
    WordNotFoundByIdError,
    WordNotFoundByNameError,
)
from majlisna.api.models.undercover import TermPair, Word, WordCreate, WordUpdate
from majlisna.api.utils.rng import rng


class UndercoverController:
    """Undercover content: words and term pairs.

    The admin lists are read from the database every time. They used to sit in
    TTLCache for an hour as ORM rows — detached rows shared across sessions, and,
    since `invalidate()` reaches one worker in four, a list that kept showing the
    old content after an admin write elsewhere.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_word(self, word_create: WordCreate):
        try:
            new_word = Word(**word_create.model_dump())
            self.session.add(new_word)
            await self.session.commit()
            await self.session.refresh(new_word)
            return new_word
        except IntegrityError:
            raise WordAlreadyExistsError(word=word_create.word) from None

    async def get_words(self) -> Sequence[Word]:
        return (await self.session.exec(select(Word))).all()

    async def get_word_by_id(self, word_id: UUID) -> Word:
        """
        Get a word by its id. If the word does not exist, raise a NoResultFound exception.

        :param word_id: The id of the word to get.
        :type word_id: UUID
        :return: The word.
        :rtype: Word
        """
        try:
            return (await self.session.exec(select(Word).where(Word.id == word_id))).one()
        except NoResultFound:
            raise WordNotFoundByIdError(word_id=word_id) from None

    async def get_word_by_word(self, word: str) -> Word:
        try:
            return (await self.session.exec(select(Word).where(Word.word == word))).one()
        except NoResultFound:
            raise WordNotFoundByNameError(word=word) from None

    async def delete_word(self, word_id: UUID) -> None:
        db_word = (await self.session.exec(select(Word).where(Word.id == word_id))).one()
        await self.session.delete(db_word)
        await self.session.commit()

    async def update_word(self, word_id: UUID, word_update: WordUpdate) -> Word:
        try:
            db_word = (await self.session.exec(select(Word).where(Word.id == word_id))).one()
        except NoResultFound:
            raise WordNotFoundByIdError(word_id=word_id) from None
        db_word_data = word_update.model_dump(exclude_unset=True)
        db_word.sqlmodel_update(db_word_data)
        self.session.add(db_word)
        await self.session.commit()
        await self.session.refresh(db_word)
        return db_word

    async def get_words_by_category(self, category: str) -> Sequence[Word]:
        return (await self.session.exec(select(Word).where(Word.category == category))).all()

    async def create_term_pair(self, word1_id: UUID, word2_id: UUID) -> TermPair:
        try:
            new_term_pair = TermPair(word1_id=word1_id, word2_id=word2_id)
            self.session.add(new_term_pair)
            await self.session.commit()
            await self.session.refresh(new_term_pair)
            return new_term_pair
        except IntegrityError:
            raise TermPairAlreadyExistsError(term1=str(word1_id), term2=str(word2_id)) from None

    async def get_term_pairs(self) -> Sequence[TermPair]:
        return (await self.session.exec(select(TermPair))).all()

    async def get_term_pair_by_id(self, term_pair_id: UUID) -> TermPair:
        try:
            return (await self.session.exec(select(TermPair).where(TermPair.id == term_pair_id))).one()
        except NoResultFound:
            raise TermPairNotFoundError(term_pair_id=term_pair_id) from None

    async def get_random_term_pair(self) -> TermPair:
        """Draw a term pair: read the pairs' keys, then fetch the one drawn.

        :raises NoResultFound: If there is no term pair.
        """
        keys = (await self.session.exec(select(TermPair.word1_id, TermPair.word2_id))).all()
        if not keys:
            raise NoResultFound
        word1_id, word2_id = rng.choice(keys)
        return (
            await self.session.exec(
                select(TermPair).where(TermPair.word1_id == word1_id, TermPair.word2_id == word2_id)
            )
        ).one()

    async def delete_term_pair(self, term_pair_id: UUID) -> None:
        try:
            db_term_pair = (await self.session.exec(select(TermPair).where(TermPair.id == term_pair_id))).one()
            await self.session.delete(db_term_pair)
            await self.session.commit()
        except NoResultFound:
            raise TermPairNotFoundError(term_pair_id=term_pair_id) from None

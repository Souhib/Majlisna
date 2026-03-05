"""Route-level tests for the undercover endpoints (/api/v1/undercover)."""

import uuid
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from starlette.testclient import TestClient

from ipg.api.controllers.undercover import UndercoverController
from ipg.api.models.undercover import TermPair, Word
from ipg.api.schemas.error import TermPairNotFoundError, WordNotFoundByIdError, WordNotFoundByNameError
from ipg.dependencies import get_undercover_controller


class TestWords:
    """Tests for the /api/v1/undercover/words endpoints."""

    def test_create_word_success(self, test_app: FastAPI, client: TestClient):
        """Creating a word with valid data returns 201 and all Word fields."""
        # Arrange
        word_id = uuid.uuid4()
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.create_word = AsyncMock(
            return_value=Word(
                id=word_id,
                word="mosque",
                category="islamic",
                short_description="Place of worship",
                long_description="A place where Muslims gather for prayer",
            )
        )
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.post(
            "/api/v1/undercover/words",
            json={
                "word": "mosque",
                "category": "islamic",
                "short_description": "Place of worship",
                "long_description": "A place where Muslims gather for prayer",
            },
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == str(word_id)
        assert data["word"] == "mosque"
        assert data["category"] == "islamic"
        assert data["short_description"] == "Place of worship"
        assert data["long_description"] == "A place where Muslims gather for prayer"

        test_app.dependency_overrides.clear()

    def test_create_word_validation_error(self, test_app: FastAPI, client: TestClient):
        """Creating a word with missing required fields returns 422."""
        # Arrange
        mock_controller = Mock(spec=UndercoverController)
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.post(
            "/api/v1/undercover/words",
            json={},
        )

        # Assert
        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "ValidationError"
        assert data["error_key"] == "errors.api.validation"

        test_app.dependency_overrides.clear()

    def test_get_all_words_success(self, test_app: FastAPI, client: TestClient):
        """Fetching all words returns 200 and a list of Word objects."""
        # Arrange
        word1_id = uuid.uuid4()
        word2_id = uuid.uuid4()
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.get_words = AsyncMock(
            return_value=[
                Word(
                    id=word1_id,
                    word="mosque",
                    category="islamic",
                    short_description="Place of worship",
                    long_description="A place where Muslims gather for prayer",
                ),
                Word(
                    id=word2_id,
                    word="quran",
                    category="islamic",
                    short_description="Holy book",
                    long_description="The holy book of Islam",
                ),
            ]
        )
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.get("/api/v1/undercover/words")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == str(word1_id)
        assert data[0]["word"] == "mosque"
        assert data[0]["category"] == "islamic"
        assert data[0]["short_description"] == "Place of worship"
        assert data[0]["long_description"] == "A place where Muslims gather for prayer"
        assert data[1]["id"] == str(word2_id)
        assert data[1]["word"] == "quran"

        test_app.dependency_overrides.clear()

    def test_get_all_words_empty(self, test_app: FastAPI, client: TestClient):
        """Fetching all words when none exist returns 200 and an empty list."""
        # Arrange
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.get_words = AsyncMock(return_value=[])
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.get("/api/v1/undercover/words")

        # Assert
        assert response.status_code == 200
        assert response.json() == []

        test_app.dependency_overrides.clear()

    def test_get_word_by_id_success(self, test_app: FastAPI, client: TestClient):
        """Fetching a word by ID returns 200 and all Word fields."""
        # Arrange
        word_id = uuid.uuid4()
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.get_word_by_id = AsyncMock(
            return_value=Word(
                id=word_id,
                word="hajj",
                category="pillars",
                short_description="Pilgrimage",
                long_description="Annual Islamic pilgrimage to Mecca",
            )
        )
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.get(f"/api/v1/undercover/words/{word_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(word_id)
        assert data["word"] == "hajj"
        assert data["category"] == "pillars"
        assert data["short_description"] == "Pilgrimage"
        assert data["long_description"] == "Annual Islamic pilgrimage to Mecca"

        test_app.dependency_overrides.clear()

    def test_get_word_by_id_not_found(self, test_app: FastAPI, client: TestClient):
        """Fetching a non-existent word by ID returns 404."""
        # Arrange
        word_id = uuid.uuid4()
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.get_word_by_id = AsyncMock(side_effect=WordNotFoundByIdError(word_id=word_id))
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.get(f"/api/v1/undercover/words/{word_id}")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "WordNotFoundByIdError"
        assert data["error_key"] == "errors.api.wordNotFoundById"

        test_app.dependency_overrides.clear()

    def test_get_word_by_word_success(self, test_app: FastAPI, client: TestClient):
        """Searching a word by name returns 200 and the Word object."""
        # Arrange
        word_id = uuid.uuid4()
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.get_word_by_word = AsyncMock(
            return_value=Word(
                id=word_id,
                word="zakat",
                category="pillars",
                short_description="Charity",
                long_description="Obligatory charitable giving in Islam",
            )
        )
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.get("/api/v1/undercover/words/search/zakat")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(word_id)
        assert data["word"] == "zakat"
        assert data["category"] == "pillars"
        assert data["short_description"] == "Charity"
        assert data["long_description"] == "Obligatory charitable giving in Islam"

        test_app.dependency_overrides.clear()

    def test_get_word_by_word_not_found(self, test_app: FastAPI, client: TestClient):
        """Searching for a non-existent word by name returns 404."""
        # Arrange
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.get_word_by_word = AsyncMock(side_effect=WordNotFoundByNameError(word="nonexistent"))
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.get("/api/v1/undercover/words/search/nonexistent")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "WordNotFoundByNameError"
        assert data["error_key"] == "errors.api.wordNotFoundByName"

        test_app.dependency_overrides.clear()

    def test_delete_word_success(self, test_app: FastAPI, client: TestClient):
        """Deleting an existing word returns 204 with no content."""
        # Arrange
        word_id = uuid.uuid4()
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.delete_word = AsyncMock(return_value=None)
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.delete(f"/api/v1/undercover/words/{word_id}")

        # Assert
        assert response.status_code == 204
        mock_controller.delete_word.assert_awaited_once_with(word_id)

        test_app.dependency_overrides.clear()

    def test_delete_word_not_found(self, test_app: FastAPI, client: TestClient):
        """Deleting a non-existent word returns 404."""
        # Arrange
        word_id = uuid.uuid4()
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.delete_word = AsyncMock(side_effect=WordNotFoundByIdError(word_id=word_id))
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.delete(f"/api/v1/undercover/words/{word_id}")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "WordNotFoundByIdError"
        assert data["error_key"] == "errors.api.wordNotFoundById"

        test_app.dependency_overrides.clear()


class TestTermPairs:
    """Tests for the /api/v1/undercover/termpair endpoints."""

    def test_create_term_pair_success(self, test_app: FastAPI, client: TestClient):
        """Creating a term pair with valid word IDs returns 201 and all TermPair fields."""
        # Arrange
        term_pair_id = uuid.uuid4()
        word1_id = uuid.uuid4()
        word2_id = uuid.uuid4()
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.create_term_pair = AsyncMock(
            return_value=TermPair(
                id=term_pair_id,
                word1_id=word1_id,
                word2_id=word2_id,
            )
        )
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.post(
            "/api/v1/undercover/termpair",
            json={"word1_id": str(word1_id), "word2_id": str(word2_id)},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == str(term_pair_id)
        assert data["word1_id"] == str(word1_id)
        assert data["word2_id"] == str(word2_id)

        test_app.dependency_overrides.clear()

    def test_get_all_term_pairs_success(self, test_app: FastAPI, client: TestClient):
        """Fetching all term pairs returns 200 and a list of TermPair objects."""
        # Arrange
        tp1_id = uuid.uuid4()
        tp2_id = uuid.uuid4()
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.get_term_pairs = AsyncMock(
            return_value=[
                TermPair(id=tp1_id, word1_id=uuid.uuid4(), word2_id=uuid.uuid4()),
                TermPair(id=tp2_id, word1_id=uuid.uuid4(), word2_id=uuid.uuid4()),
            ]
        )
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.get("/api/v1/undercover/termpair")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == str(tp1_id)
        assert data[1]["id"] == str(tp2_id)

        test_app.dependency_overrides.clear()

    def test_get_all_term_pairs_empty(self, test_app: FastAPI, client: TestClient):
        """Fetching all term pairs when none exist returns 200 and an empty list."""
        # Arrange
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.get_term_pairs = AsyncMock(return_value=[])
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.get("/api/v1/undercover/termpair")

        # Assert
        assert response.status_code == 200
        assert response.json() == []

        test_app.dependency_overrides.clear()

    def test_get_term_pair_by_id_success(self, test_app: FastAPI, client: TestClient):
        """Fetching a term pair by ID returns 200 and all TermPair fields."""
        # Arrange
        term_pair_id = uuid.uuid4()
        word1_id = uuid.uuid4()
        word2_id = uuid.uuid4()
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.get_term_pair_by_id = AsyncMock(
            return_value=TermPair(
                id=term_pair_id,
                word1_id=word1_id,
                word2_id=word2_id,
            )
        )
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.get(f"/api/v1/undercover/termpair/{term_pair_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(term_pair_id)
        assert data["word1_id"] == str(word1_id)
        assert data["word2_id"] == str(word2_id)

        test_app.dependency_overrides.clear()

    def test_get_term_pair_by_id_not_found(self, test_app: FastAPI, client: TestClient):
        """Fetching a non-existent term pair by ID returns 404."""
        # Arrange
        term_pair_id = uuid.uuid4()
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.get_term_pair_by_id = AsyncMock(side_effect=TermPairNotFoundError(term_pair_id=term_pair_id))
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.get(f"/api/v1/undercover/termpair/{term_pair_id}")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "TermPairNotFoundError"
        assert data["error_key"] == "errors.api.termPairNotFound"

        test_app.dependency_overrides.clear()

    def test_get_random_term_pair_success(self, test_app: FastAPI, client: TestClient):
        """Fetching a random term pair returns 200 and a TermPair object."""
        # Arrange
        term_pair_id = uuid.uuid4()
        word1_id = uuid.uuid4()
        word2_id = uuid.uuid4()
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.get_random_term_pair = AsyncMock(
            return_value=TermPair(
                id=term_pair_id,
                word1_id=word1_id,
                word2_id=word2_id,
            )
        )
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.get("/api/v1/undercover/termpair/search/random")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(term_pair_id)
        assert data["word1_id"] == str(word1_id)
        assert data["word2_id"] == str(word2_id)

        test_app.dependency_overrides.clear()

    def test_get_random_term_pair_not_found(self, test_app: FastAPI, client: TestClient):
        """Fetching a random term pair when none exist returns 404."""
        # Arrange
        term_pair_id = uuid.uuid4()
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.get_random_term_pair = AsyncMock(side_effect=TermPairNotFoundError(term_pair_id=term_pair_id))
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.get("/api/v1/undercover/termpair/search/random")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "TermPairNotFoundError"
        assert data["error_key"] == "errors.api.termPairNotFound"

        test_app.dependency_overrides.clear()

    def test_delete_term_pair_success(self, test_app: FastAPI, client: TestClient):
        """Deleting an existing term pair returns 204 with no content."""
        # Arrange
        term_pair_id = uuid.uuid4()
        mock_controller = Mock(spec=UndercoverController)
        mock_controller.delete_term_pair = AsyncMock(return_value=None)
        test_app.dependency_overrides[get_undercover_controller] = lambda: mock_controller

        # Act
        response = client.delete(f"/api/v1/undercover/termpair/{term_pair_id}")

        # Assert
        assert response.status_code == 204
        mock_controller.delete_term_pair.assert_awaited_once_with(term_pair_id)

        test_app.dependency_overrides.clear()

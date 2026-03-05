"""Route-level tests for the codenames endpoints (/api/v1/codenames)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from ipg.api.controllers.codenames import (
    CodenamesController,
    CodenamesWordPackNotFoundError,
)
from ipg.api.models.codenames import CodenamesWord, CodenamesWordPack
from ipg.dependencies import get_codenames_controller


class TestWordPacks:
    """Tests for the /api/v1/codenames/word-packs endpoints."""

    def test_create_word_pack_success(self, test_app: FastAPI, client: TestClient):
        """Creating a word pack with valid data returns 201 and all CodenamesWordPack fields."""
        # Arrange
        pack_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_controller = Mock(spec=CodenamesController)
        mock_controller.create_word_pack = AsyncMock(
            return_value=CodenamesWordPack(
                id=pack_id,
                name="Islamic Terms",
                description="Words related to Islam",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        test_app.dependency_overrides[get_codenames_controller] = lambda: mock_controller

        # Act
        response = client.post(
            "/api/v1/codenames/word-packs",
            json={
                "name": "Islamic Terms",
                "description": "Words related to Islam",
            },
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == str(pack_id)
        assert data["name"] == "Islamic Terms"
        assert data["description"] == "Words related to Islam"
        assert data["is_active"] is True
        assert "created_at" in data
        assert "updated_at" in data

        test_app.dependency_overrides.clear()

    def test_create_word_pack_validation_error(self, test_app: FastAPI, client: TestClient):
        """Creating a word pack with missing required fields returns 422."""
        # Arrange
        mock_controller = Mock(spec=CodenamesController)
        test_app.dependency_overrides[get_codenames_controller] = lambda: mock_controller

        # Act
        response = client.post(
            "/api/v1/codenames/word-packs",
            json={},
        )

        # Assert
        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "ValidationError"
        assert data["error_key"] == "errors.api.validation"

        test_app.dependency_overrides.clear()

    def test_get_word_packs_success(self, test_app: FastAPI, client: TestClient):
        """Fetching all word packs returns 200 and a list of CodenamesWordPack objects."""
        # Arrange
        pack1_id = uuid.uuid4()
        pack2_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_controller = Mock(spec=CodenamesController)
        mock_controller.get_word_packs = AsyncMock(
            return_value=[
                CodenamesWordPack(
                    id=pack1_id,
                    name="Prophets",
                    description="Names of prophets",
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                ),
                CodenamesWordPack(
                    id=pack2_id,
                    name="Pillars",
                    description="Five pillars of Islam",
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        test_app.dependency_overrides[get_codenames_controller] = lambda: mock_controller

        # Act
        response = client.get("/api/v1/codenames/word-packs")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == str(pack1_id)
        assert data[0]["name"] == "Prophets"
        assert data[0]["description"] == "Names of prophets"
        assert data[0]["is_active"] is True
        assert data[1]["id"] == str(pack2_id)
        assert data[1]["name"] == "Pillars"

        test_app.dependency_overrides.clear()

    def test_get_word_packs_empty(self, test_app: FastAPI, client: TestClient):
        """Fetching all word packs when none exist returns 200 and an empty list."""
        # Arrange
        mock_controller = Mock(spec=CodenamesController)
        mock_controller.get_word_packs = AsyncMock(return_value=[])
        test_app.dependency_overrides[get_codenames_controller] = lambda: mock_controller

        # Act
        response = client.get("/api/v1/codenames/word-packs")

        # Assert
        assert response.status_code == 200
        assert response.json() == []

        test_app.dependency_overrides.clear()

    def test_get_word_pack_by_id_success(self, test_app: FastAPI, client: TestClient):
        """Fetching a word pack by ID returns 200 and all CodenamesWordPack fields."""
        # Arrange
        pack_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_controller = Mock(spec=CodenamesController)
        mock_controller.get_word_pack = AsyncMock(
            return_value=CodenamesWordPack(
                id=pack_id,
                name="Islamic Terms",
                description="Words related to Islam",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        test_app.dependency_overrides[get_codenames_controller] = lambda: mock_controller

        # Act
        response = client.get(f"/api/v1/codenames/word-packs/{pack_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(pack_id)
        assert data["name"] == "Islamic Terms"
        assert data["description"] == "Words related to Islam"
        assert data["is_active"] is True
        assert "created_at" in data
        assert "updated_at" in data

        test_app.dependency_overrides.clear()

    def test_get_word_pack_not_found(self, test_app: FastAPI, client: TestClient):
        """Fetching a non-existent word pack by ID raises CodenamesWordPackNotFoundError."""
        # Arrange
        pack_id = uuid.uuid4()
        mock_controller = Mock(spec=CodenamesController)
        mock_controller.get_word_pack = AsyncMock(side_effect=CodenamesWordPackNotFoundError(pack_id=pack_id))
        test_app.dependency_overrides[get_codenames_controller] = lambda: mock_controller

        # Act & Assert
        with pytest.raises(CodenamesWordPackNotFoundError) as exc_info:
            client.get(f"/api/v1/codenames/word-packs/{pack_id}")

        assert str(pack_id) in str(exc_info.value)

        test_app.dependency_overrides.clear()

    def test_delete_word_pack_success(self, test_app: FastAPI, client: TestClient):
        """Deleting an existing word pack returns 204 with no content."""
        # Arrange
        pack_id = uuid.uuid4()
        mock_controller = Mock(spec=CodenamesController)
        mock_controller.delete_word_pack = AsyncMock(return_value=None)
        test_app.dependency_overrides[get_codenames_controller] = lambda: mock_controller

        # Act
        response = client.delete(f"/api/v1/codenames/word-packs/{pack_id}")

        # Assert
        assert response.status_code == 204
        mock_controller.delete_word_pack.assert_awaited_once_with(pack_id)

        test_app.dependency_overrides.clear()

    def test_delete_word_pack_not_found(self, test_app: FastAPI, client: TestClient):
        """Deleting a non-existent word pack raises CodenamesWordPackNotFoundError."""
        # Arrange
        pack_id = uuid.uuid4()
        mock_controller = Mock(spec=CodenamesController)
        mock_controller.delete_word_pack = AsyncMock(side_effect=CodenamesWordPackNotFoundError(pack_id=pack_id))
        test_app.dependency_overrides[get_codenames_controller] = lambda: mock_controller

        # Act & Assert
        with pytest.raises(CodenamesWordPackNotFoundError) as exc_info:
            client.delete(f"/api/v1/codenames/word-packs/{pack_id}")

        assert str(pack_id) in str(exc_info.value)

        test_app.dependency_overrides.clear()


class TestWords:
    """Tests for the /api/v1/codenames word endpoints."""

    def test_add_word_to_pack_success(self, test_app: FastAPI, client: TestClient):
        """Adding a word to a pack returns 201 and all CodenamesWord fields."""
        # Arrange
        pack_id = uuid.uuid4()
        word_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_controller = Mock(spec=CodenamesController)
        mock_controller.add_word = AsyncMock(
            return_value=CodenamesWord(
                id=word_id,
                word="minaret",
                word_pack_id=pack_id,
                created_at=now,
                updated_at=now,
            )
        )
        test_app.dependency_overrides[get_codenames_controller] = lambda: mock_controller

        # Act
        response = client.post(
            f"/api/v1/codenames/word-packs/{pack_id}/words",
            json={"word": "minaret"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == str(word_id)
        assert data["word"] == "minaret"
        assert data["word_pack_id"] == str(pack_id)
        assert "created_at" in data
        assert "updated_at" in data

        test_app.dependency_overrides.clear()

    def test_get_words_by_pack_success(self, test_app: FastAPI, client: TestClient):
        """Fetching words for a pack returns 200 and a list of CodenamesWord objects."""
        # Arrange
        pack_id = uuid.uuid4()
        word1_id = uuid.uuid4()
        word2_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_controller = Mock(spec=CodenamesController)
        mock_controller.get_words_by_pack = AsyncMock(
            return_value=[
                CodenamesWord(
                    id=word1_id,
                    word="minaret",
                    word_pack_id=pack_id,
                    created_at=now,
                    updated_at=now,
                ),
                CodenamesWord(
                    id=word2_id,
                    word="mihrab",
                    word_pack_id=pack_id,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        test_app.dependency_overrides[get_codenames_controller] = lambda: mock_controller

        # Act
        response = client.get(f"/api/v1/codenames/word-packs/{pack_id}/words")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == str(word1_id)
        assert data[0]["word"] == "minaret"
        assert data[0]["word_pack_id"] == str(pack_id)
        assert data[1]["id"] == str(word2_id)
        assert data[1]["word"] == "mihrab"

        test_app.dependency_overrides.clear()

    def test_get_words_by_pack_empty(self, test_app: FastAPI, client: TestClient):
        """Fetching words for a pack with no words returns 200 and an empty list."""
        # Arrange
        pack_id = uuid.uuid4()
        mock_controller = Mock(spec=CodenamesController)
        mock_controller.get_words_by_pack = AsyncMock(return_value=[])
        test_app.dependency_overrides[get_codenames_controller] = lambda: mock_controller

        # Act
        response = client.get(f"/api/v1/codenames/word-packs/{pack_id}/words")

        # Assert
        assert response.status_code == 200
        assert response.json() == []

        test_app.dependency_overrides.clear()

    def test_delete_word_success(self, test_app: FastAPI, client: TestClient):
        """Deleting an existing word returns 204 with no content."""
        # Arrange
        word_id = uuid.uuid4()
        mock_controller = Mock(spec=CodenamesController)
        mock_controller.delete_word = AsyncMock(return_value=None)
        test_app.dependency_overrides[get_codenames_controller] = lambda: mock_controller

        # Act
        response = client.delete(f"/api/v1/codenames/words/{word_id}")

        # Assert
        assert response.status_code == 204
        mock_controller.delete_word.assert_awaited_once_with(word_id)

        test_app.dependency_overrides.clear()

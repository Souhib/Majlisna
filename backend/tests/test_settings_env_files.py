"""The `.env` selector names the environment with MAJLISNA_ENV, and Settings accepts it.

`.env` is both the selector `_get_env_file` reads and the first file Settings loads. Since
BaseSettings forbids extra inputs, the selector's own line must be a field: it used to be a
field named after the project's former name, absorbing a line from before the rename, so a
`.env` carrying `MAJLISNA_ENV=` (the variable the selector actually reads) failed to load.
"""

from pathlib import Path

import pytest

from majlisna.settings import Settings


def test_a_selector_naming_majlisna_env_loads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Prepare: the selector and a development file, in a directory of their own
    (tmp_path / ".env").write_text("MAJLISNA_ENV=development\n")
    (tmp_path / ".env.development").write_text("DATABASE_URL=sqlite+aiosqlite:///:memory:\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MAJLISNA_ENV", raising=False)

    # Act
    settings = Settings(_env_file=(".env", ".env.development"))  # ty: ignore[unknown-argument]

    # Assert
    assert settings.majlisna_env == "development"


def test_no_setting_keeps_the_former_project_name() -> None:
    assert not [name for name in Settings.model_fields if "ipg" in name.lower()]

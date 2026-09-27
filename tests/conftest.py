from pathlib import Path

import pytest

from stack_integration.storage import ArtifactStore, ControllerDatabase


@pytest.fixture
def database(tmp_path: Path):
    value = ControllerDatabase(tmp_path / "controller.db")
    yield value
    value.close()


@pytest.fixture
def artifacts(tmp_path: Path, database: ControllerDatabase):
    return ArtifactStore(tmp_path / "artifacts", database)

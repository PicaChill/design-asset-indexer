from pathlib import Path

import pytest

from tests.generate_fixtures import generate_fixture_tree


@pytest.fixture()
def fixture_tree(tmp_path: Path) -> Path:
    return generate_fixture_tree(tmp_path / "synthetic")

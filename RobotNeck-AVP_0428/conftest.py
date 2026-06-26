from pathlib import Path

import pytest


@pytest.fixture
def tmp_path(tmpdir):
    return Path(str(tmpdir))

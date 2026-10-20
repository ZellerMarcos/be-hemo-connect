import os
from unittest.mock import patch

import pytest

os.environ["APP_ENV"] = "test"


@pytest.fixture
def real_rate_limits():
    """Seleciona explicitamente testes com os contadores reais."""


@pytest.fixture(autouse=True)
def isolate_rate_limits(request):
    if "real_rate_limits" in request.fixturenames:
        yield
    else:
        with patch("app.security.rate_limit.enforce_rate_limit"):
            yield

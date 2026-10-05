import pytest


@pytest.fixture
def layout():
    return {"profile": "posix-case-sensitive-v1", "interpreter": "/venv/bin/python",
            "scheme": {"purelib": "/venv/lib/site-packages", "platlib": "/venv/lib/site-packages",
                       "scripts": "/venv/bin", "headers": "/venv/include", "data": "/venv"}}

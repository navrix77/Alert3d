"""Тести не залежать від даних сервера: нічне самонавчання (data/learned_places.json) на сервері змінює словник,
і тести, що перевіряють вибір тезок, падали б там (09.11: «Степне» 47.8 замість 47.0 → автооновлення відхиляло нові збірки)."""
import pathlib
import tempfile

import pytest


@pytest.fixture(autouse=True, scope="session")
def _no_learned_places():
    from app import dictlearn, parser
    old = dictlearn.LEARNED
    dictlearn.LEARNED = pathlib.Path(tempfile.gettempdir()) / "no-learned-places-for-tests.json"
    parser.reload_learned()
    yield
    dictlearn.LEARNED = old
    parser.reload_learned()

"""Param-model validation — placeholder ids are rejected before ever
reaching the network (2026-07-17 incident: article_id="unknown" was
dispatched straight to the backend and 404'd)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from pydantic import ValidationError

from params import ArticleIdParams, ProjectIdParams


@pytest.mark.parametrize("junk", ["unknown", "UNKNOWN", "null", "undefined", "", "   ", "n/a"])
def test_article_id_rejects_placeholders(junk):
    with pytest.raises(ValidationError):
        ArticleIdParams(article_id=junk)


def test_article_id_accepts_a_real_looking_id():
    params = ArticleIdParams(article_id="22222222-2222-2222-2222-222222222222")
    assert params.article_id == "22222222-2222-2222-2222-222222222222"


@pytest.mark.parametrize("junk", ["unknown", "null", ""])
def test_project_id_rejects_placeholders(junk):
    with pytest.raises(ValidationError):
        ProjectIdParams(project_id=junk)

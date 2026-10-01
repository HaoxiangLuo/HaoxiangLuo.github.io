#!/usr/bin/env python3
"""Tests for the shared, configurable model client.

The endpoint, key and model are configuration because GitHub Models — the
provider these scripts originally used — was retired on 2026-07-30. These cases
use a stubbed urlopen: no network, no provider account, no credit.
"""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import model_client  # noqa: E402

ENV_KEYS = ("TRANSLATE_BASE_URL", "TRANSLATE_API_KEY", "TRANSLATE_MODEL", "GITHUB_TOKEN")


class FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes, status: int = 200) -> None:
        super().__init__(payload)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.saved = {key: os.environ.pop(key, None) for key in ENV_KEYS}

    def tearDown(self) -> None:
        for key, value in self.saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value

    def test_no_provider_configured_by_default(self):
        self.assertFalse(model_client.configured())

    def test_base_url_alone_configures_a_provider(self):
        os.environ["TRANSLATE_BASE_URL"] = "https://api.example.com/v1"
        self.assertTrue(model_client.configured())
        self.assertEqual(model_client.endpoint(), "https://api.example.com/v1/chat/completions")

    def test_api_key_alone_configures_a_provider(self):
        os.environ["TRANSLATE_API_KEY"] = "sk-test"
        self.assertTrue(model_client.configured())

    def test_bare_github_token_is_not_a_provider(self):
        os.environ["GITHUB_TOKEN"] = "gho_example"
        self.assertFalse(model_client.configured())
        self.assertEqual(model_client.api_key(), "gho_example")

    def test_explicit_key_wins_over_github_token(self):
        os.environ["GITHUB_TOKEN"] = "gho_example"
        os.environ["TRANSLATE_API_KEY"] = "sk-test"
        self.assertEqual(model_client.api_key(), "sk-test")

    def test_endpoint_keeps_a_full_url(self):
        os.environ["TRANSLATE_BASE_URL"] = "https://api.example.com/v1/chat/completions"
        self.assertEqual(model_client.endpoint(), "https://api.example.com/v1/chat/completions")

    def test_model_defaults_and_overrides(self):
        self.assertEqual(model_client.model(), "gpt-4o-mini")
        os.environ["TRANSLATE_MODEL"] = "llama-3.3-70b"
        self.assertEqual(model_client.model(), "llama-3.3-70b")


class ChatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.saved = {key: os.environ.pop(key, None) for key in ENV_KEYS}
        os.environ["TRANSLATE_BASE_URL"] = "https://api.example.com/v1"
        os.environ["TRANSLATE_API_KEY"] = "sk-test"
        self.original = model_client.urllib.request.urlopen
        self.sent: list[dict] = []

    def tearDown(self) -> None:
        model_client.urllib.request.urlopen = self.original
        for key, value in self.saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value

    def stub(self, reply: str | None = None, body: bytes | None = None):
        payload = body if body is not None else json.dumps(
            {"choices": [{"message": {"content": reply}}]}
        ).encode("utf-8")

        def fake(request, *args, **kwargs):
            self.sent.append(json.loads(request.data.decode("utf-8")))
            return FakeResponse(payload)

        model_client.urllib.request.urlopen = fake

    def test_reply_is_returned(self):
        self.stub("联合国儿童基金会实习生")
        self.assertEqual(model_client.chat([{"role": "user", "content": "hi"}]), "联合国儿童基金会实习生")
        self.assertEqual(self.sent[0]["model"], "gpt-4o-mini")

    def test_response_format_is_forwarded(self):
        self.stub("{}")
        model_client.chat([{"role": "user", "content": "hi"}], response_format={"type": "json_object"})
        self.assertEqual(self.sent[0]["response_format"], {"type": "json_object"})

    def test_non_json_body_is_reported(self):
        # The retired GitHub Models host answers like this for every request.
        self.stub(body=b"OK")
        with self.assertRaises(model_client.ModelUnavailable) as ctx:
            model_client.chat([{"role": "user", "content": "hi"}])
        self.assertIn("non-JSON", str(ctx.exception))

    def test_http_error_body_is_reported(self):
        def fake(request, *args, **kwargs):
            raise urllib.error.HTTPError(
                "https://api.example.com/v1/chat/completions", 401, "Unauthorized",
                {"Content-Type": "application/json"}, None,
            )

        model_client.urllib.request.urlopen = fake
        with self.assertRaises(model_client.ModelUnavailable) as ctx:
            model_client.chat([{"role": "user", "content": "hi"}])
        self.assertIn("HTTP 401", str(ctx.exception))

    def test_reply_without_a_choice_is_reported(self):
        self.stub(body=json.dumps({"error": "no choices"}).encode("utf-8"))
        with self.assertRaises(model_client.ModelUnavailable) as ctx:
            model_client.chat([{"role": "user", "content": "hi"}])
        self.assertIn("without a choice", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

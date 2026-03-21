from __future__ import annotations

import base64
import unittest
from unittest.mock import AsyncMock, patch

import aiohttp

from paperfeeder.chat import LLMClient


class _FakeContent:
    def __init__(self, chunks: list[bytes], error: Exception | None = None) -> None:
        self._chunks = chunks
        self._error = error

    def iter_chunked(self, _size: int):
        async def _generator():
            for chunk in self._chunks:
                yield chunk
            if self._error is not None:
                raise self._error

        return _generator()


class _FakeResponse:
    def __init__(self, plan: dict) -> None:
        self.status = plan.get("status", 200)
        self.content = _FakeContent(plan.get("chunks", []), plan.get("stream_error"))
        self.headers = plan.get("headers", {})
        self.request_info = None
        self.history = ()


class _FakeRequest:
    def __init__(self, plan: dict) -> None:
        self._plan = plan

    async def __aenter__(self):
        enter_error = self._plan.get("enter_error")
        if enter_error is not None:
            raise enter_error
        return _FakeResponse(self._plan)

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeSession:
    created_kwargs: list[dict] = []
    plans: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        self._plan = self.plans.pop(0)
        self.created_kwargs.append(kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, url: str, **kwargs):
        self._plan["url"] = url
        self._plan["request_kwargs"] = kwargs
        return _FakeRequest(self._plan)


class PdfDownloadTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        _FakeSession.created_kwargs = []
        _FakeSession.plans = []

    async def test_pdf_download_retries_payload_error_and_uses_proxy_env(self) -> None:
        _FakeSession.plans = [
            {
                "status": 200,
                "chunks": [b"%PDF-1.7\npartial"],
                "stream_error": aiohttp.ClientPayloadError("broken payload"),
            },
            {
                "status": 200,
                "chunks": [b"%PDF-1.7\ncomplete"],
            },
        ]
        client = LLMClient(api_key="test")

        with patch("paperfeeder.chat.aiohttp.ClientSession", _FakeSession), patch(
            "paperfeeder.chat.asyncio.sleep", new=AsyncMock()
        ) as sleep_mock:
            pdf_base64 = await client._url_to_base64_async("https://arxiv.org/pdf/test.pdf", max_pages=0)

        self.assertEqual(base64.standard_b64decode(pdf_base64), b"%PDF-1.7\ncomplete")
        self.assertEqual(len(_FakeSession.created_kwargs), 2)
        self.assertTrue(_FakeSession.created_kwargs[0]["trust_env"])
        self.assertIn("User-Agent", _FakeSession.created_kwargs[0]["headers"])
        sleep_mock.assert_awaited_once()

    async def test_pdf_download_retries_temporary_http_status(self) -> None:
        _FakeSession.plans = [
            {"status": 503, "chunks": []},
            {"status": 200, "chunks": [b"%PDF-1.4\nok"]},
        ]
        client = LLMClient(api_key="test")

        with patch("paperfeeder.chat.aiohttp.ClientSession", _FakeSession), patch(
            "paperfeeder.chat.asyncio.sleep", new=AsyncMock()
        ):
            pdf_base64 = await client._url_to_base64_async("https://arxiv.org/pdf/test.pdf", max_pages=0)

        self.assertEqual(base64.standard_b64decode(pdf_base64), b"%PDF-1.4\nok")

    async def test_pdf_download_rejects_non_pdf_body(self) -> None:
        _FakeSession.plans = [
            {"status": 200, "chunks": [b"<html>not a pdf</html>"]},
        ]
        client = LLMClient(api_key="test")

        with patch("paperfeeder.chat.aiohttp.ClientSession", _FakeSession):
            pdf_base64 = await client._url_to_base64_async("https://example.com/not-pdf", max_pages=0)

        self.assertIsNone(pdf_base64)


if __name__ == "__main__":
    unittest.main()
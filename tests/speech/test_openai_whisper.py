"""Tests for OpenAI Whisper API speech backend."""

from unittest.mock import MagicMock, patch

import pytest

from openjarvis.core.registry import SpeechRegistry
from openjarvis.speech._stubs import TranscriptionResult
from openjarvis.speech.openai_whisper import OpenAIWhisperBackend


@pytest.fixture(autouse=True)
def _register_openai_whisper():
    """Re-register after any registry clear."""
    if not SpeechRegistry.contains("openai"):
        SpeechRegistry.register_value("openai", OpenAIWhisperBackend)


def test_openai_whisper_registers():
    assert SpeechRegistry.contains("openai")


def test_openai_whisper_transcribe():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Hello from OpenAI"
    mock_response.language = "en"
    mock_response.duration = 2.0
    mock_client.audio.transcriptions.create.return_value = mock_response

    with patch("openjarvis.speech.openai_whisper.OpenAI", return_value=mock_client):
        from openjarvis.speech.openai_whisper import OpenAIWhisperBackend

        backend = OpenAIWhisperBackend(api_key="test-key")
        result = backend.transcribe(b"fake audio", format="wav")

        assert isinstance(result, TranscriptionResult)
        assert result.text == "Hello from OpenAI"
        assert result.language == "en"


def test_openai_whisper_health():
    with patch("openjarvis.speech.openai_whisper.OpenAI"):
        from openjarvis.speech.openai_whisper import OpenAIWhisperBackend

        backend = OpenAIWhisperBackend(api_key="test-key")
        assert backend.health() is True


def test_openai_whisper_health_no_key():
    with patch("openjarvis.speech.openai_whisper.OpenAI"):
        from openjarvis.speech.openai_whisper import OpenAIWhisperBackend

        backend = OpenAIWhisperBackend.__new__(OpenAIWhisperBackend)
        backend._client = None
        backend._api_key = ""
        assert backend.health() is False


# Éden: modelo de transcrição configurável e idioma por modelo.
def _mock_client():
    mock_client = MagicMock()
    mock_response = MagicMock(spec=["text"])
    mock_response.text = "Olá"
    mock_client.audio.transcriptions.create.return_value = mock_response
    return mock_client


def test_openai_default_model_is_whisper_1():
    mock_client = _mock_client()
    with patch("openjarvis.speech.openai_whisper.OpenAI", return_value=mock_client):
        backend = OpenAIWhisperBackend(api_key="test-key")
        backend.transcribe(b"fake audio", format="webm", language="pt")
    kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
    assert kwargs["model"] == "whisper-1"
    assert kwargs["language"] == "pt"
    assert kwargs["response_format"] == "verbose_json"


def test_openai_gpt_transcribe_sends_languages_list():
    mock_client = _mock_client()
    with patch("openjarvis.speech.openai_whisper.OpenAI", return_value=mock_client):
        backend = OpenAIWhisperBackend(api_key="test-key", model="gpt-transcribe")
        result = backend.transcribe(b"fake audio", format="mp4", language="pt")
    kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-transcribe"
    assert "language" not in kwargs
    assert kwargs["extra_body"] == {"languages": ["pt"]}
    assert kwargs["response_format"] == "json"
    assert kwargs["file"].name == "audio.mp4"
    assert result.text == "Olá"
    assert result.duration_seconds == 0.0


def test_openai_gpt4o_transcribe_uses_json_and_language():
    mock_client = _mock_client()
    with patch("openjarvis.speech.openai_whisper.OpenAI", return_value=mock_client):
        backend = OpenAIWhisperBackend(api_key="test-key", model="gpt-4o-mini-transcribe")
        backend.transcribe(b"fake audio", format="webm", language="pt")
    kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
    assert kwargs["language"] == "pt"
    assert kwargs["response_format"] == "json"

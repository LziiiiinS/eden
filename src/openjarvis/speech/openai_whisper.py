"""OpenAI Whisper API speech-to-text backend (cloud)."""

from __future__ import annotations

import io
import os
from typing import List, Optional

from openjarvis.core.registry import SpeechRegistry
from openjarvis.speech._stubs import SpeechBackend, TranscriptionResult

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment, misc]


@SpeechRegistry.register("openai")
class OpenAIWhisperBackend(SpeechBackend):
    """Cloud speech-to-text using OpenAI Whisper API."""

    backend_id = "openai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "whisper-1",
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        # Éden: modelo configurável ([speech] openai_model). Padrão original: whisper-1.
        self._model = model or "whisper-1"
        self._client: Optional[OpenAI] = None
        if self._api_key and OpenAI is not None:
            self._client = OpenAI(api_key=self._api_key)

    def transcribe(
        self,
        audio: bytes,
        *,
        format: str = "wav",
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe audio using OpenAI's Whisper API."""
        if self._client is None:
            raise RuntimeError("OpenAI client not initialized (missing API key?)")

        ext = format if not format.startswith(".") else format[1:]
        audio_file = io.BytesIO(audio)
        audio_file.name = f"audio.{ext}"

        kwargs: dict = {"model": self._model, "file": audio_file}
        if self._model.startswith("whisper"):
            if language:
                kwargs["language"] = language
            kwargs["response_format"] = "verbose_json"
        elif self._model.startswith("gpt-transcribe"):
            # Éden: o gpt-transcribe recebe o idioma como lista ("languages"),
            # que substitui o campo "language". Vai em extra_body para funcionar
            # mesmo com versões do SDK que ainda não conhecem o campo.
            if language:
                kwargs["extra_body"] = {"languages": [language]}
            kwargs["response_format"] = "json"
        else:
            # Éden: gpt-4o-transcribe e gpt-4o-mini-transcribe só devolvem json/text.
            if language:
                kwargs["language"] = language
            kwargs["response_format"] = "json"

        response = self._client.audio.transcriptions.create(**kwargs)

        return TranscriptionResult(
            text=getattr(response, "text", str(response)),
            language=getattr(response, "language", None),
            confidence=None,
            duration_seconds=getattr(response, "duration", 0.0),
            segments=[],
        )

    def health(self) -> bool:
        return self._client is not None and bool(self._api_key)

    def supported_formats(self) -> List[str]:
        return ["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"]

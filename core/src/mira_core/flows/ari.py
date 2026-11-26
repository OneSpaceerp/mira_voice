"""The ARI calls the Mira Flow engine makes on a channel in its Stasis application."""

from typing import Any

import httpx

from mira_core.config import Settings


class IvrAri:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.client = httpx.AsyncClient(
            base_url=settings.ari_url,
            auth=(settings.ari_user, settings.ari_password.get_secret_value()),
            timeout=10.0,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def _post(self, path: str, **params: Any) -> httpx.Response:
        r = await self.client.post(path, params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r

    async def answer(self, channel: str) -> None:
        await self._post(f"/channels/{channel}/answer")

    async def play(self, channel: str, media: str, lang: str, playback_id: str) -> None:
        await self._post(
            f"/channels/{channel}/play", media=media, lang=lang, playbackId=playback_id
        )

    async def stop_playback(self, playback_id: str) -> None:
        r = await self.client.delete(f"/playbacks/{playback_id}")
        if r.status_code not in (200, 204, 404):  # 404: it had just finished
            r.raise_for_status()

    async def set_variable(self, channel: str, variable: str, value: str) -> None:
        await self._post(f"/channels/{channel}/variable", variable=variable, value=value)

    async def continue_in_dialplan(self, channel: str, context: str, extension: str) -> None:
        await self._post(
            f"/channels/{channel}/continue", context=context, extension=extension, priority=1
        )

    async def hangup(self, channel: str) -> None:
        r = await self.client.delete(f"/channels/{channel}", params={"reason": "normal"})
        if r.status_code not in (200, 204, 404):
            r.raise_for_status()

    async def record(self, channel: str, name: str, max_seconds: int) -> None:
        await self._post(
            f"/channels/{channel}/record",
            name=name,
            format="wav",
            maxDurationSeconds=max_seconds,
            maxSilenceSeconds=10,
            ifExists="fail",
            beep="true",
            terminateOn="#",
        )

    # ---- stored recordings (voicemail playback through the API) ----

    async def recording_file(self, name: str) -> bytes | None:
        r = await self.client.get(f"/recordings/stored/{name}/file")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.content

    async def delete_recording(self, name: str) -> None:
        r = await self.client.delete(f"/recordings/stored/{name}")
        if r.status_code not in (200, 204, 404):
            r.raise_for_status()

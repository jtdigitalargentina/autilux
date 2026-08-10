import json
import urllib.error
import urllib.request

from app.core.settings import settings


class TwentyClient:
    def __init__(self):
        self.base_url = settings.TWENTY_URL.rstrip("/")
        self.api_key = settings.TWENTY_API_KEY

    def _request(self, method: str, path: str, data: dict | None = None):
        url = f"{self.base_url}{path}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        body = None

        if data is not None:
            body = json.dumps(data).encode("utf-8")

        request = urllib.request.Request(
            url=url,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                content = response.read().decode("utf-8")

                if not content:
                    return None

                return json.loads(content)

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8")
            raise RuntimeError(
                f"Twenty API error {exc.code}: {detail}"
            ) from exc

        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Could not connect to Twenty: {exc.reason}"
            ) from exc

    def list_people(self, limit: int = 10):
        return self._request(
            "GET",
            f"/rest/people?limit={limit}",
        )

    def list_companies(self, limit: int = 10):
        return self._request(
            "GET",
            f"/rest/companies?limit={limit}",
        )

    def list_opportunities(self, limit: int = 10):
        return self._request(
            "GET",
            f"/rest/opportunities?limit={limit}",
        )


twenty_client = TwentyClient()

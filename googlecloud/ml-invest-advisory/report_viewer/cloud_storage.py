"""
Cloud Storage access (beta) for the report viewer, always as the signed-in user.

Purpose:
  Lists and downloads the HTML reports with the Cloud Storage JSON API. Every call takes the signed-in user's
  OAuth access token; this module holds no credentials of its own. So Cloud Storage IAM decides what each user can
  read, the same check storage.cloud.google.com makes: a user without access gets Cloud Storage's 403.

Requirements:
  Python 3.10+, standard library only.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

API_BASE = 'https://storage.googleapis.com/storage/v1'
TIMEOUT_SECONDS = 30


class CloudStorageError(Exception):
    """A Cloud Storage request failed; status is its HTTP status (e.g. 401, 403, 404), or 502 if it was unreachable."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class CloudStorage:
    def __init__(self, bucket: str, prefix: str):
        self.bucket = bucket
        self.prefix = prefix

    def list_html_objects(self, access_token: str) -> list[dict]:
        """The *.html objects under the prefix, in any sub-folder, as {'name', 'updated', 'size'}."""
        objects, page_token = [], None
        while True:
            params = {'prefix': self.prefix, 'fields': 'items(name,updated,size),nextPageToken'}
            if page_token:
                params['pageToken'] = page_token
            page = json.loads(self._get(f'{self._bucket_url()}/o?{urllib.parse.urlencode(params)}', access_token))
            objects += [item for item in page.get('items', []) if item['name'].endswith('.html')]
            page_token = page.get('nextPageToken')
            if not page_token:
                return objects

    def download(self, path: str, access_token: str) -> bytes:
        """The content of the object prefix + path (e.g. 'yang/daily-report-yang-llm-generated.html')."""
        object_name = urllib.parse.quote(self.prefix + path, safe='')
        return self._get(f'{self._bucket_url()}/o/{object_name}?alt=media', access_token)

    def _bucket_url(self) -> str:
        return f'{API_BASE}/b/{urllib.parse.quote(self.bucket, safe="")}'

    @staticmethod
    def _get(url: str, access_token: str) -> bytes:
        request = urllib.request.Request(url, headers={'Authorization': f'Bearer {access_token}'})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            raise CloudStorageError(error.code, f'Cloud Storage returned HTTP {error.code}') from error
        except urllib.error.URLError as error:
            raise CloudStorageError(502, f'Cloud Storage is unreachable: {error.reason}') from error

"""Small GitHub Contents/Tree API client, invoked server-side only.

A fine-grained personal access token with Contents: Read and write for the
specific repository is required for admin writes. Never send it to the browser.
"""
from __future__ import annotations

import base64
import json
from urllib.parse import quote

import requests


class GithubError(Exception):
    pass


class GithubStore:
    def __init__(self, repository: str, branch: str = 'main', token: str = ''):
        if '/' not in repository or len(repository.split('/')) != 2:
            raise GithubError('GITHUB_REPO должен быть в формате owner/StudySpace.')
        self.repository = repository
        self.branch = branch
        self.token = token
        self.api = f'https://api.github.com/repos/{repository}'
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': 'StudySpace-Portal',
        })
        if token:
            self.session.headers['Authorization'] = f'Bearer {token}'

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        try:
            response = self.session.request(method, url, timeout=35, **kwargs)
        except requests.RequestException as exc:
            raise GithubError('Не удалось подключиться к GitHub. Попробуйте ещё раз.') from exc
        if not response.ok and response.status_code != 404:
            try:
                message = response.json().get('message', 'GitHub API error')
            except ValueError:
                message = 'GitHub API error'
            if response.status_code in (401, 403):
                raise GithubError('GitHub отказал в доступе. Проверь GITHUB_TOKEN и права Contents: Read and write.')
            raise GithubError(f'GitHub HTTP {response.status_code}: {message}')
        return response

    def _content_url(self, path: str) -> str:
        return f'{self.api}/contents/{quote(path, safe="/")}'

    def read_catalog(self) -> dict:
        response = self.request('GET', self._content_url('catalog.json'), params={'ref': self.branch})
        if response.status_code == 404:
            raise GithubError('В репозитории отсутствует catalog.json.')
        payload = response.json()
        if payload.get('encoding') == 'base64':
            contents = base64.b64decode(payload['content']).decode('utf-8')
        else:
            raise GithubError('Не удалось прочитать catalog.json.')
        return json.loads(contents)

    def tree(self) -> list[dict]:
        response = self.request('GET', f'{self.api}/git/trees/{quote(self.branch, safe="")}', params={'recursive': 1})
        if response.status_code == 404:
            raise GithubError('Не найдена ветка GitHub.')
        data = response.json()
        if data.get('truncated'):
            raise GithubError('Дерево GitHub слишком большое для автоматического каталога.')
        return data.get('tree', [])

    def get_sha(self, path: str) -> str | None:
        response = self.request('GET', self._content_url(path), params={'ref': self.branch})
        if response.status_code == 404:
            return None
        return response.json().get('sha')

    def write_file(self, path: str, data: bytes, message: str, *, replace: bool = False) -> dict:
        if not self.token:
            raise GithubError('GITHUB_TOKEN не настроен.')
        current_sha = self.get_sha(path)
        if current_sha and not replace:
            raise GithubError(f'Файл уже существует: {path}. Включи замену файлов, если нужно перезаписать.')
        body = {
            'message': message,
            'branch': self.branch,
            'content': base64.b64encode(data).decode('ascii'),
        }
        if current_sha:
            body['sha'] = current_sha
        response = self.request('PUT', self._content_url(path), json=body)
        if response.status_code == 404:
            raise GithubError('Путь или ветка GitHub не найдены.')
        if response.status_code not in (200, 201):
            raise GithubError(f'GitHub не сохранил файл ({response.status_code}).')
        return response.json()

    def ensure_folder(self, path: str) -> None:
        filename = f'{path.rstrip("/")}/.gitkeep'
        if self.get_sha(filename) is None:
            self.write_file(filename, b'', f'Create StudySpace folder {path}')

    def delete_file(self, path: str, sha: str, message: str) -> None:
        # A git delete: the file stays recoverable from repository history.
        if not self.token:
            raise GithubError('GITHUB_TOKEN не настроен.')
        response = self.request('DELETE', self._content_url(path), json={'message': message, 'branch': self.branch, 'sha': sha})
        if response.status_code == 404:
            raise GithubError('Файл уже удалён или не найден.')

    def recent_files(self, since_iso: str, limit: int = 30) -> dict[str, str]:
        """Paths added under materials/uploads since a date -> 'YYYY-MM-DD' of the first addition seen.

        One request per commit, so only the latest `limit` commits are inspected.
        Admin type changes (copy + delete) are skipped so moved files are not shown as new.
        """
        response = self.request('GET', f'{self.api}/commits', params={
            'sha': self.branch, 'path': 'materials/uploads', 'since': since_iso, 'per_page': limit})
        if response.status_code == 404:
            return {}
        added: dict[str, str] = {}
        for commit in response.json():
            if commit.get('commit', {}).get('message', '').startswith('StudySpace: move'):
                continue
            date = commit['commit']['committer']['date'][:10]
            detail = self.request('GET', f'{self.api}/commits/{commit["sha"]}')
            for changed in detail.json().get('files', []) if detail.ok else []:
                if changed.get('status') in ('added', 'renamed'):
                    added.setdefault(changed['filename'], date)  # newest commit first
        return added

    def raw_url(self, path: str) -> str:
        return f'https://raw.githubusercontent.com/{self.repository}/{quote(self.branch, safe="")}/{quote(path, safe="/")}'

    def raw_bytes(self, path: str, sha: str) -> bytes:
        # This portal is public. Versioned raw URL prevents stale content after replacing a file.
        url = self.raw_url(path)
        try:
            response = requests.get(url, params={'rev': sha}, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise GithubError('Не удалось скачать материал из GitHub.') from exc
        return response.content

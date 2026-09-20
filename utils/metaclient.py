import random
import re
import time
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlsplit, urlunsplit
import requests

from config import Settings, get_conf
from utils.logging import logger


class MetaError(RuntimeError):
    def __init__(self, status=None, code=None, subcode=None, reason='request_failed', message=None):
        self.status, self.code, self.subcode, self.message = status, code, subcode, message
        detail = f' message={message}' if message else ''
        super().__init__(f'{reason} http_status={status} meta_code={code} meta_subcode={subcode}{detail}')


class MetaClient:
    def __init__(self, version, session=None, sleep=time.sleep):
        if not re.fullmatch(r'v\d+\.\d+', version):
            raise ValueError('Invalid API version')
        self.base = f'https://graph.facebook.com/{version}'
        self.session = session or requests.Session()
        self.sleep = sleep
        self.pages = 0

    def close(self):
        self.session.close()

    def get(self, endpoint, access_token, params=None):
        """Explicit credentials/watermark even for endpoints with full refresh semantics."""
        url = endpoint if endpoint.startswith('https://') else f'{self.base}/{endpoint.lstrip("/")}'
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.hostname != 'graph.facebook.com' or parts.port not in (None, 443) or parts.username or parts.password:
            raise MetaError(reason='unsafe_pagination_host')
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.update(params or {})
        # Do not send credentials supplied by paging.next. Use the caller's token.
        query.pop('access_token', None)
        query.pop('appsecret_proof', None)
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
        for attempt in range(6):
            status = code = subcode = None
            error_message = None
            retry = False
            delay = min(60, 2 ** attempt + random.random())
            try:
                response = self.session.get(url, params=query, headers={'Authorization': f'Bearer {access_token}'}, timeout=(10, 60), allow_redirects=False)
                status = response.status_code
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                if not isinstance(payload, dict):
                    raise MetaError(status=status, reason='invalid_response_shape')
                error = payload.get('error') or {}
                if not isinstance(error, dict):
                    raise MetaError(status=status, reason='invalid_error_shape')
                code = error.get('code') if isinstance(error.get('code'), int) else None
                subcode = error.get('error_subcode') if isinstance(error.get('error_subcode'), int) else None
                error_message = error.get('message') if isinstance(error.get('message'), str) else None
                if 200 <= status < 300 and 'error' not in payload:
                    if not payload:
                        raise MetaError(status=status, reason='empty_or_invalid_json')
                    self.pages += 1

                    for header in ('x-app-usage', 'x-ad-account-usage', 'x-business-use-case-usage'):
                        if header in response.headers:
                            values = re.findall(r'"(?:call_count|total_cputime|total_time|estimated_time_to_regain_access)"\s*:\s*(\d+)', response.headers[header])
                            if values and max(map(int, values)) >= 90:
                                logger.warning("Meta usage is high for %s: %s", header, max(map(int, values)))
                    return payload
                account_limit_reached = code == 17 and subcode == 2446079
                data_size_rejected = (
                    code == 1
                    and error_message is not None
                    and "reduce the amount of data" in error_message.lower()
                )
                retry = (
                    not account_limit_reached
                    and not data_size_rejected
                    and (
                        status in (429, 500, 502, 503, 504)
                        or code in (1, 2, 4, 613, 80000, 80004)
                        or error.get('is_transient') is True
                    )
                )
                retry_after = response.headers.get('Retry-After', '')
                if retry_after.isdigit():
                    delay = min(60, max(delay, int(retry_after)))
                else:
                    try:
                        retry_date = parsedate_to_datetime(retry_after)
                        delay = min(60, max(delay, retry_date.timestamp() - time.time()))
                    except (TypeError, ValueError, OverflowError):
                        pass
            except (requests.Timeout, requests.ConnectionError):
                retry = True
            except requests.RequestException:
                raise MetaError(reason='transport_error') from None
            if not retry or attempt == 5:
                raise MetaError(status, code, subcode, message=error_message) from None
            logger.warning("Retrying Meta request after %.1f seconds (attempt %d/6)", delay, attempt + 1)
            self.sleep(delay)
        raise AssertionError('unreachable')

    def paginate(self, endpoint, access_token, params=None):
        seen = set()
        while endpoint:
            #time.sleep(1)
            if endpoint in seen:
                raise MetaError(reason='pagination_cycle')
            seen.add(endpoint)
            data = self.get(endpoint, access_token, params)
            if not isinstance(data.get('data'), list):
                raise MetaError(reason='missing_data_array')
            yield data['data']
            paging = data.get('paging') or {}
            endpoint = paging.get('next')
            if endpoint is not None and not isinstance(endpoint, str):
                raise MetaError(reason='invalid_pagination_link')
            params = None


def get_client(settings: Settings | None = None) -> MetaClient:
    settings = settings or get_conf()
    return MetaClient(settings.api_version)

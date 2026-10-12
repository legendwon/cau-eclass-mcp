"""
CAU-ON API Client (Proprietary LMS)
Provides interface to CAU's custom e-class platform API

Updated with discovered endpoints from 04_CAU_ON_API_Discovery_0307.md (2026-03-07)
Fixed with exact browser request matching (2026-03-08)
"""

from typing import List, Dict, Optional, Any
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import requests
import logging

logger = logging.getLogger(__name__)
import httpx


# Default mapping if config.json is missing (Empty by default for security/generic use)
DEFAULT_COURSE_FOLDER_MAP = {
    # "course_id": "Johnny_Decimal_Folder_Name"
}


class CAUOnClient:
    """Client for CAU-ON proprietary API"""

    def __init__(self, auth_session: requests.Session):
        """
        Initialize CAU-ON API client

        Args:
            auth_session: Authenticated requests.Session with valid cookies from auth.py
        """
        self.session = auth_session
        self.base_url = 'https://eclass3.cau.ac.kr'
        self._session_initialized = False
        
        # Load configuration from config.json
        self.config = self._load_config()

        # Create httpx client for HTTP/2 support
        # Note: cookies will be updated from session on each request
        self.http2_client = httpx.Client(
            http2=True,
            timeout=30.0,
            follow_redirects=True
        )

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from config.json in the project root"""
        # Try to find config.json in project root
        # Path relative to this file: src/cau_eclass_mcp/cau_on_client.py -> 프로젝트 루트
        locations = [
            Path.cwd() / 'config.json',
            Path(__file__).parent.parent.parent / 'config.json',
        ]
        
        for loc in locations:
            if loc.exists():
                try:
                    with open(loc, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception as e:
                    logger.debug("CAU API progress")
        
        return {}

    def _get_course_folder_name(self, course_id: str) -> str:
        """Get the folder name for a course from config or default mapping"""
        course_map = self.config.get('course_map', DEFAULT_COURSE_FOLDER_MAP)
        return course_map.get(str(course_id), f"99_Unknown_Course_{course_id}")

    def close(self):
        """Close HTTP/2 client and release resources"""
        if self.http2_client:
            self.http2_client.close()

    def __del__(self):
        """Cleanup on garbage collection"""
        try:
            self.close()
        except Exception:
            pass

    @staticmethod
    def _convert_utc_to_kst(utc_time_str: str) -> str:
        """
        Convert UTC timestamp to KST (Korea Standard Time)

        Args:
            utc_time_str: ISO 8601 UTC timestamp (e.g., "2026-03-09T15:00:00Z")

        Returns:
            KST timestamp string (e.g., "2026-03-10 00:00:00 KST")
        """
        if not utc_time_str:
            return utc_time_str

        try:
            # Parse UTC timestamp
            if utc_time_str.endswith('Z'):
                utc_time = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
            else:
                utc_time = datetime.fromisoformat(utc_time_str)

            # Convert to KST (UTC+9)
            kst_time = utc_time.astimezone(timezone(timedelta(hours=9)))

            # Format as readable string
            return kst_time.strftime('%Y-%m-%d %H:%M:%S KST')

        except (ValueError, AttributeError):
            # If parsing fails, return original string
            return utc_time_str

    def _get_csrf_token(self) -> Optional[str]:
        """
        Extract CSRF token from session cookies

        Returns:
            CSRF token string or None if not found
        """
        from urllib.parse import unquote

        # Get _csrf_token cookie and URL-decode it for the header
        # The cookie value is stored URL-encoded in the jar, but the header
        # must contain the decoded value (as seen in browser DevTools)
        token = self.session.cookies.get('_csrf_token')
        if token:
            return unquote(token)

        # Fallback: search for any cookie with '_csrf' in name
        for cookie in self.session.cookies:
            if '_csrf' in cookie.name.lower():
                return unquote(cookie.value)

        return None

    def _ensure_session_initialized(self) -> None:
        """
        Ensure session is properly initialized by visiting dashboard.

        The CAU e-class system requires visiting the dashboard page before
        API calls will work. This sets up necessary session state on the server side.
        """
        if self._session_initialized:
            return

        # Visit dashboard to initialize server-side session state
        try:
            response = self.session.get(
                f'{self.base_url}/learningx/dashboard',
                timeout=10,
                allow_redirects=True
            )

            if response.status_code == 200:
                self._session_initialized = True
            else:
                raise Exception(f"Dashboard visit failed with status {response.status_code}")

        except Exception as e:
            raise Exception(f"Failed to initialize session: {e}")

    def _make_request(self, method: str, url: str, **kwargs):
        """
        Make HTTP/2 request matching successful browser request EXACTLY

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL
            **kwargs: Additional arguments

        Returns:
            httpx.Response object
        """
        # Ensure session is initialized before making API calls
        self._ensure_session_initialized()

        # Get FRESH cookies from requests.Session (includes cookies added after login)
        self.http2_client.cookies.update(self.session.cookies)

        # Headers matching successful browser request (from 성공.md)
        # This is EXACTLY what Chrome sends when accessing API URL directly
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'ko,en-US;q=0.9,en;q=0.8',
            'Sec-Ch-Ua': '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-User': '?1',
            'Sec-Fetch-Dest': 'document',
            'Upgrade-Insecure-Requests': '1',
            'Priority': 'u=0, i'
        }

        # DO NOT add:
        # - X-Requested-With (browser doesn't send it)
        # - X-Csrf-Token (browser doesn't send it)
        # - Referer (browser doesn't send it)
        # - Origin (browser doesn't send it)

        # Merge any custom headers
        custom_headers = kwargs.pop('headers', {})
        headers.update(custom_headers)

        # Use httpx for HTTP/2 support with FRESH cookies
        response = self.http2_client.request(method, url, headers=headers, **kwargs)
        self.session.cookies.update(self.http2_client.cookies.jar)
        return response

    def _parse_json_response(self, response):
        """
        Parse JSON response, handling Canvas's while(1); prefix

        Canvas LMS adds 'while(1);' prefix to JSON responses to prevent JSON hijacking.
        We need to strip this before parsing.

        Args:
            response: httpx.Response object

        Returns:
            Parsed JSON data
        """
        import json

        text = response.text

        # Remove while(1); prefix if present (Canvas JSON hijacking protection)
        if text.startswith('while(1);'):
            text = text[9:]  # Remove 'while(1);'

        return json.loads(text)

    def get_courses(self) -> List[Dict]:
        """
        Fetch active courses from favorites

        Returns:
            List of course dictionaries with 'id', 'name', 'course_code', 'term', etc.

        Endpoint: GET /api/v1/users/self/favorites/courses
        """
        endpoint = f'{self.base_url}/api/v1/users/self/favorites/courses'
        params = {
            'include[]': 'term',
            'exclude[]': 'enrollments',
            'sort': 'nickname'
        }

        try:
            response = self._make_request('GET', endpoint, params=params, timeout=10)
            response.raise_for_status()

            # Response is a JSON array of course objects (with while(1); prefix)
            data = self._parse_json_response(response)

            # Handle different response structures
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and 'courses' in data:
                return data['courses']
            elif isinstance(data, dict) and 'data' in data:
                return data['data']
            else:
                logger.debug("CAU API progress")
                return []

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.debug("CAU API progress")
                raise RuntimeError("API endpoint not found. Check if you're logged in.")
            else:
                logger.debug("CAU API progress")
                raise
        except requests.exceptions.RequestException as e:
            logger.debug("CAU API progress")
            raise
        except ValueError as e:
            logger.debug("CAU API progress")
            raise

    def get_course_announcements(self, course_id: str, limit: int = 20) -> List[Dict]:
        """
        Fetch course announcements

        Args:
            course_id: Course ID
            limit: Maximum number of announcements to return (default: 20)

        Returns:
            List of announcement dictionaries with 'id', 'title', 'posted_at', etc.

        Endpoint: GET /api/v1/announcements
        """
        endpoint = f'{self.base_url}/api/v1/announcements'

        # Calculate date range (from 1900 to now)
        end_date = datetime.now().strftime('%Y-%m-%d')

        params = {
            'context_codes[]': f'course_{course_id}',
            'per_page': min(limit, 100),  # API max is usually 100
            'page': 1,
            'start_date': '1900-01-01',
            'end_date': end_date,
            'active_only': 'true',
            'include[]': ['sections', 'sections_user_count']
        }

        try:
            response = self._make_request('GET', endpoint, params=params, timeout=10)
            response.raise_for_status()

            data = self._parse_json_response(response)

            # Handle different response structures
            if isinstance(data, list):
                return data[:limit]
            elif isinstance(data, dict) and 'announcements' in data:
                return data['announcements'][:limit]
            elif isinstance(data, dict) and 'items' in data:
                return data['items'][:limit]
            else:
                logger.debug("CAU API progress")
                return []

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.debug("CAU API progress")
                return []
            else:
                logger.debug("CAU API progress")
                raise
        except Exception as e:
            logger.debug("CAU API progress")
            raise

    def get_course_assignments(self, course_id: str) -> List[Dict]:
        """
        Fetch course assignments along with the user's submission status.

        Args:
            course_id: Course ID

        Returns:
            List of assignment dictionaries including a 'submission' object for the user.

        Endpoint: GET /api/v1/courses/{course_id}/assignments?include[]=submission
        """
        endpoint = f'{self.base_url}/api/v1/courses/{course_id}/assignments'
        params = {
            'include[]': 'submission',
            'per_page': 50
        }

        try:
            response = self._make_request('GET', endpoint, params=params, timeout=10)
            response.raise_for_status()

            data = self._parse_json_response(response)

            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and 'assignments' in data:
                return data['assignments']
            elif isinstance(data, dict) and 'items' in data:
                return data['items']
            else:
                logger.debug("CAU API progress")
                return []

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.debug("CAU API progress")
                return []
            else:
                logger.debug("CAU API progress")
                raise
        except Exception as e:
            logger.debug("CAU API progress")
            raise

    def get_modules(self, course_id: str) -> List[Dict]:
        """
        Fetch course modules (주차별 강의 목록)

        Args:
            course_id: Course ID

        Returns:
            List of module dictionaries with items included

        Endpoint: GET /api/v1/courses/{course_id}/modules?include[]=items&include[]=content_details
        """
        endpoint = f'{self.base_url}/api/v1/courses/{course_id}/modules'
        params = {
            'include[]': ['items', 'content_details'],
            'per_page': 100
        }

        try:
            response = self._make_request('GET', endpoint, params=params, timeout=10)
            response.raise_for_status()

            data = self._parse_json_response(response)

            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and 'modules' in data:
                return data['modules']
            else:
                logger.debug("CAU API progress")
                return []

        except Exception as e:
            logger.debug("CAU API progress")
            raise

    def get_learningx_modules(self, course_id: str) -> List[Dict]:
        """
        Fetch detailed course modules using LearningX API (Weekly view)
        """
        endpoint = f'{self.base_url}/learningx/api/v1/courses/{course_id}/modules'
        params = {'include_detail': 'true'}
        
        try:
            jwt_token = self.session.cookies.get('xn_api_token')
            headers = {'Authorization': f'Bearer {jwt_token}'} if jwt_token else {}
            
            response = self._make_request('GET', endpoint, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            return self._parse_json_response(response)
        except Exception as e:
            logger.debug("CAU API progress")
            raise

    def get_ocs_content_info(self, content_id: str) -> Optional[Dict]:
        """
        Fetch and parse VOD content information from OCS (Commons)
        """
        import xml.etree.ElementTree as ET
        endpoint = f'https://ocs.cau.ac.kr/viewer/ssplayer/uniplayer_support/content.php'
        params = {'content_id': content_id}
        
        try:
            response = self._make_request('GET', endpoint, params=params, timeout=10)
            response.raise_for_status()
            
            root = ET.fromstring(response.text)
            info = {}
            
            # Extract basic info
            playing_info = root.find('.//content_playing_info')
            if playing_info is not None:
                info['content_id'] = playing_info.findtext('content_id')
                info['content_type'] = playing_info.findtext('content_type')
                info['main_uri'] = playing_info.findtext('content_uri')
            
            # Extract media URLs (CDN links)
            media_uris = []
            for media in root.findall('.//media'):
                media_type = media.get('type', 'default')
                for uri in media.findall('media_uri'):
                    media_uris.append({
                        'type': media_type,
                        'method': uri.get('method'),
                        'target': uri.get('target'),
                        'url': uri.text
                    })
            info['media_uris'] = media_uris
            
            # Extract title
            metadata = root.find('.//content_metadata')
            if metadata is not None:
                info['title'] = metadata.findtext('title')
                
            return info
        except Exception as e:
            logger.debug("CAU API progress")
            raise

    def get_attendance_item(self, course_id: str, item_id: str) -> Optional[Dict]:
        """
        Fetch attendance/lecture item details (수강 정보)

        Args:
            course_id: Course ID
            item_id: Attendance item ID (from module external_url)

        Returns:
            Attendance item dictionary with lecture status, due dates, etc.

        Endpoint: GET /learningx/api/v1/courses/{course_id}/attendance_items/{item_id}

        Note: This endpoint requires Authorization header with JWT from xn_api_token cookie
        """
        endpoint = f'{self.base_url}/learningx/api/v1/courses/{course_id}/attendance_items/{item_id}'

        try:
            # Get JWT token from xn_api_token cookie
            jwt_token = self.session.cookies.get('xn_api_token')

            # Custom headers for learningx API
            custom_headers = {
                'Accept': '*/*',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Dest': 'empty',
                'Referer': 'https://eclass3.cau.ac.kr/learningx/lti/lecture'
            }

            # Add Authorization header if JWT token is available
            if jwt_token:
                custom_headers['Authorization'] = f'Bearer {jwt_token}'

            response = self._make_request('GET', endpoint, headers=custom_headers, timeout=10)
            response.raise_for_status()

            data = self._parse_json_response(response)

            # Convert UTC timestamps to KST for better readability
            if data:
                time_fields = ['unlock_at', 'due_at', 'lock_at']
                for field in time_fields:
                    if field in data and data[field]:
                        data[field] = self._convert_utc_to_kst(data[field])

            return data

        except Exception as e:
            logger.debug("CAU API progress")
            raise

    def get_course_files(self, course_id: str) -> List[Dict]:
        """
        Fetch all files for a course.

        Args:
            course_id: Course ID

        Returns:
            List of file dictionaries.
            
        Endpoint: GET /api/v1/courses/{course_id}/files
        """
        endpoint = f'{self.base_url}/api/v1/courses/{course_id}/files'
        params = {
            'per_page': 100,
            'sort': 'created_at',
            'order': 'desc'
        }

        try:
            response = self._make_request('GET', endpoint, params=params, timeout=10)
            response.raise_for_status()

            data = self._parse_json_response(response)

            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and 'files' in data:
                return data['files']
            else:
                return []

        except Exception as e:
            logger.debug("CAU API progress")
            raise

    def find_course_by_name(self, course_name: str) -> Optional[str]:
        """
        Find course ID by course name (fuzzy match)

        Args:
            course_name: Course name to search for (supports partial match)

        Returns:
            Course ID if found, None otherwise
        """
        courses = self.get_courses()

        if not courses:
            return None

        # Try exact match first
        for course in courses:
            name = course.get('name', course.get('title', ''))
            if name == course_name:
                return str(course.get('id', course.get('course_id', '')))

        # Try case-insensitive partial match
        course_name_lower = course_name.lower()
        for course in courses:
            name = course.get('name', course.get('title', ''))
            if course_name_lower in name.lower():
                return str(course.get('id', course.get('course_id', '')))

        return None

    def get_file_info(self, course_id: str, file_id: str) -> Optional[Dict]:
        """
        Get file metadata (name, size, content-type, etc.)

        Args:
            course_id: Course ID
            file_id: File ID

        Returns:
            File metadata dictionary

        Endpoint: GET /api/v1/courses/{course_id}/files/{file_id}
        """
        endpoint = f'{self.base_url}/api/v1/courses/{course_id}/files/{file_id}'

        try:
            response = self._make_request('GET', endpoint, timeout=10)
            response.raise_for_status()

            data = self._parse_json_response(response)
            return data

        except Exception as e:
            logger.debug("CAU API progress")
            raise

    def _get_auto_save_path(self, course_id: str, filename: str) -> str:
        """
        Generate save path strictly following Obsidian Johnny Decimal rules.
        Path: {base_dir}/{NN_course_name}/90_자료/{XX_filename}
        """
        import os
        import re
        from pathlib import Path

        # Try environment variable, then config.json, then default path
        base_dir = os.environ.get('CAU_ECLASS_DOWNLOAD_DIR')
        if not base_dir:
            base_dir = self.config.get('download_dir')

        if base_dir:
            base = Path(base_dir)
        else:
            base = Path.home() / 'Downloads' / 'eclass'

        folder_name = self._get_course_folder_name(course_id)
        target_dir = base / folder_name / '90_자료'
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Auto-numbering logic: Find the highest existing prefix (e.g., 01_, 02_)
        max_num = 0
        pattern = re.compile(r'^(\d+)_')
        try:
            for f in target_dir.iterdir():
                if f.is_file():
                    match = pattern.match(f.name)
                    if match:
                        num = int(match.group(1))
                        if num > max_num:
                            max_num = num
        except FileNotFoundError:
            pass
        
        next_num = max_num + 1
        new_filename = f"{next_num:02d}_{filename}"
        
        return str(target_dir / new_filename)

    def _validate_save_path(self, save_path: str) -> str:
        """
        Validate and sanitize file save path to prevent path traversal.

        Args:
            save_path: Requested save path

        Returns:
            Validated absolute path

        Raises:
            ValueError: If path is outside allowed directories
        """
        import os
        from pathlib import Path

        # Resolve to absolute path (resolves .., symlinks, etc.)
        resolved = Path(save_path).resolve()

        # Allowed base directories
        home = Path.home()
        allowed_bases = [
            home / "Downloads",
            home / "Documents",
            home / "Desktop",
            Path(os.environ.get('TEMP', '')),
            Path(os.environ.get('TMP', '')),
        ]

        # Add custom download directory if configured via env var or config.json
        custom_dir = os.environ.get('CAU_ECLASS_DOWNLOAD_DIR') or self.config.get('download_dir')
        if custom_dir:
            allowed_bases.append(Path(custom_dir))

        # Check if resolved path is under an allowed directory
        for base in allowed_bases:
            try:
                if base.exists() and resolved.is_relative_to(base.resolve()):
                    return str(resolved)
            except (ValueError, OSError, AttributeError):
                continue

        raise ValueError(
            f"Save path must be under ~/Downloads, ~/Documents, ~/Desktop, configured path, or CAU_ECLASS_DOWNLOAD_DIR. "
            f"Got: {resolved}"
        )

    def download_file(self, course_id: str, file_id: str, save_path: str = None, filename: str = None) -> bool:
        """
        Download a file from e-class

        Args:
            course_id: Course ID
            file_id: File ID
            save_path: Local path to save the file (optional, auto-routed if None)
            filename: Filename hint for auto-routing

        Returns:
            True if download successful, False otherwise

        Endpoint: GET /courses/{course_id}/files/{file_id}/download
        """
        # Auto-routing if save_path is not provided
        if save_path is None:
            fname = filename or file_id
            save_path = self._get_auto_save_path(course_id, fname)

        # Validate save path to prevent path traversal
        try:
            save_path = self._validate_save_path(save_path)
        except ValueError as e:
            logger.debug("CAU API progress")
            return False

        endpoint = f'{self.base_url}/courses/{course_id}/files/{file_id}/download'

        try:
            # Use stream=True for large files
            response = self._make_request('GET', endpoint, timeout=60)
            response.raise_for_status()

            # Write to file
            import os
            os.makedirs(os.path.dirname(save_path), exist_ok=True)

            with open(save_path, 'wb') as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    f.write(chunk)

            return True

        except Exception as e:
            logger.debug("CAU API progress")
            return False

    @staticmethod
    def extract_attachments_from_html(html_message: str) -> List[Dict]:
        """
        Extract file attachments from announcement HTML message

        Args:
            html_message: HTML content from announcement message

        Returns:
            List of attachment dictionaries with 'file_id', 'course_id', 'filename', 'url'

        Example HTML:
            <a class="instructure_file_link"
               href="/courses/139454/files/9991440/download?wrap=1"
               data-api-endpoint="https://eclass3.cau.ac.kr/api/v1/courses/139454/files/9991440"
               title="MOTnS_w1_Introduction.pdf">
        """
        import re
        from html.parser import HTMLParser

        attachments = []

        class FileExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.files = []

            def handle_starttag(self, tag, attrs):
                if tag == 'a':
                    attrs_dict = dict(attrs)
                    if 'instructure_file_link' in attrs_dict.get('class', ''):
                        # Extract file info
                        href = attrs_dict.get('href', '')
                        title = attrs_dict.get('title', '')
                        api_endpoint = attrs_dict.get('data-api-endpoint', '')

                        # Parse course_id and file_id from href or API endpoint
                        # Pattern: /courses/{course_id}/files/{file_id}/download
                        match = re.search(r'/courses/(\d+)/files/(\d+)', href)
                        if match:
                            course_id = match.group(1)
                            file_id = match.group(2)

                            self.files.append({
                                'file_id': file_id,
                                'course_id': course_id,
                                'filename': title,
                                'url': href,
                                'api_endpoint': api_endpoint
                            })

        parser = FileExtractor()
        try:
            parser.feed(html_message)
            attachments = parser.files
        except Exception as e:
            logger.debug("CAU API progress")

        return attachments

    def get_todo_items(self) -> List[Dict]:
        """Fetch unified todo items (assignments, quizzes, lectures) across all courses"""
        endpoint = f'{self.base_url}/api/v1/users/self/todo'
        try:
            response = self._make_request('GET', endpoint, timeout=10)
            response.raise_for_status()
            return self._parse_json_response(response)
        except Exception as e:
            logger.debug("CAU API progress")
            raise

    def get_conversations(self, limit: int = 10) -> List[Dict]:
        """Fetch personal messages/conversations"""
        endpoint = f'{self.base_url}/api/v1/conversations'
        params = {'interacted_only': 1, 'per_page': limit}
        try:
            response = self._make_request('GET', endpoint, params=params, timeout=10)
            response.raise_for_status()
            return self._parse_json_response(response)
        except Exception as e:
            logger.debug("CAU API progress")
            raise

    def get_activity_stream(self) -> List[Dict]:
        """Fetch recent activity stream across all courses"""
        endpoint = f'{self.base_url}/api/v1/users/self/activity_stream'
        try:
            response = self._make_request('GET', endpoint, timeout=10)
            response.raise_for_status()
            return self._parse_json_response(response)
        except Exception as e:
            logger.debug("CAU API progress")
            raise

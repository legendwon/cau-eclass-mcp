"""
Authentication tests for CAU SSO login

Tests verify that Python login creates API-enabled sessions.
Requires valid CAU credentials (from keyring, env vars, or interactive prompt).
"""

import pytest
pytestmark = pytest.mark.live
from cau_eclass_mcp.auth import CauAuthenticator
from cau_eclass_mcp.cau_on_client import CAUOnClient
from cau_eclass_mcp.utils.credentials import get_credentials


class TestAuthentication:
    """Test CAU SSO authentication"""

    @pytest.fixture
    def credentials(self):
        """Load credentials from keyring/env/prompt"""
        return get_credentials()

    @pytest.fixture
    def authenticator(self, credentials):
        """Create authenticator instance"""
        return CauAuthenticator(credentials['username'], credentials['password'])

    def test_login_succeeds(self, authenticator):
        """Test that login completes without errors"""
        result = authenticator.login(debug=False)
        assert result is True, "Login should succeed with valid credentials"

    def test_normandy_session_exists(self, authenticator):
        """Test that _normandy_session cookie is created"""
        authenticator.login(debug=False)
        normandy_cookie = authenticator.session.cookies.get('_normandy_session')
        assert normandy_cookie is not None, "_normandy_session cookie should exist"

    def test_normandy_session_length(self, authenticator):
        """Test that _normandy_session has expected length (API-enabled)"""
        authenticator.login(debug=False)
        normandy_cookie = authenticator.session.cookies.get('_normandy_session')
        # API-enabled session should be ~421 chars, non-API is ~208 chars
        assert len(normandy_cookie) > 400, f"Session length {len(normandy_cookie)} too short for API-enabled"

    def test_api_access_works(self, authenticator):
        """Test that API calls work with authenticated session"""
        authenticator.login(debug=False)
        client = CAUOnClient(authenticator.session)

        courses = client.get_courses()
        assert isinstance(courses, list), "Should return a list of courses"
        assert len(courses) > 0, "Should have at least one course"

    def test_dashboard_access(self, authenticator):
        """Test that dashboard API works"""
        authenticator.login(debug=False)
        client = CAUOnClient(authenticator.session)

        courses = client.get_courses()
        assert isinstance(courses, list), "Courses should be a list"


class TestCredentialManagement:
    """Test credential loading mechanisms"""

    def test_credentials_loaded(self):
        """Test that credentials can be loaded"""
        creds = get_credentials()
        assert 'username' in creds, "Credentials should have username"
        assert 'password' in creds, "Credentials should have password"
        assert len(creds['username']) > 0, "Username should not be empty"
        assert len(creds['password']) > 0, "Password should not be empty"


@pytest.mark.slow
class TestStability:
    """Stability tests for repeated logins"""

    def test_multiple_logins(self):
        """Test that login can be performed multiple times successfully"""
        creds = get_credentials()
        num_runs = 3

        for i in range(num_runs):
            auth = CauAuthenticator(creds['username'], creds['password'])
            result = auth.login(debug=False)
            assert result is True, f"Login {i+1}/{num_runs} should succeed"

            # Verify API access
            client = CAUOnClient(auth.session)
            courses = client.get_courses()
            assert len(courses) > 0, f"Run {i+1}: Should have courses"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

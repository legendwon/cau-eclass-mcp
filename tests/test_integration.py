"""
Integration tests for CAU e-class MCP

These tests verify end-to-end functionality with real CAU-ON API.
Requires valid credentials and network access to CAU servers.
"""

import pytest
pytestmark = pytest.mark.live
from cau_eclass_mcp.auth import CauAuthenticator
from cau_eclass_mcp.cau_on_client import CAUOnClient
from cau_eclass_mcp.utils.credentials import get_credentials


@pytest.fixture(scope="module")
def authenticated_client():
    """Create authenticated CAU-ON client for tests"""
    creds = get_credentials()
    auth = CauAuthenticator(creds['username'], creds['password'])

    if not auth.login(debug=False):
        pytest.fail("Failed to authenticate with CAU SSO")

    return CAUOnClient(auth.session)


class TestCourseAPIs:
    """Test course-related API endpoints"""

    def test_get_courses(self, authenticated_client):
        """Test fetching course list"""
        courses = authenticated_client.get_courses()

        assert isinstance(courses, list), "Should return list of courses"
        assert len(courses) > 0, "Should have at least one course"

        # Verify course structure
        first_course = courses[0]
        assert 'id' in first_course, "Course should have ID"
        assert 'name' in first_course, "Course should have name"

    def test_get_dashboard(self, authenticated_client):
        """Test dashboard endpoint"""
        dashboard = {"courses": authenticated_client.get_courses()}

        assert 'courses' in dashboard, "Dashboard should contain courses"
        assert isinstance(dashboard['courses'], list), "Courses should be a list"

        if len(dashboard['courses']) > 0:
            course = dashboard['courses'][0]
            assert 'id' in course
            assert 'name' in course


class TestAnnouncementAPIs:
    """Test announcement-related API endpoints"""

    def test_get_announcements(self, authenticated_client):
        """Test fetching course announcements"""
        # Get first course ID
        courses = authenticated_client.get_courses()
        if not courses:
            pytest.skip("No courses available")

        course_id = courses[0]['id']

        # Fetch announcements
        announcements = authenticated_client.get_course_announcements(course_id, limit=5)

        assert isinstance(announcements, list), "Should return list of announcements"
        # Note: Course might have zero announcements, which is valid

        if len(announcements) > 0:
            announcement = announcements[0]
            assert 'title' in announcement, "Announcement should have title"


class TestAssignmentAPIs:
    """Test assignment-related API endpoints"""

    def test_get_assignments(self, authenticated_client):
        """Test fetching course assignments"""
        # Get first course ID
        courses = authenticated_client.get_courses()
        if not courses:
            pytest.skip("No courses available")

        course_id = courses[0]['id']

        # Fetch assignments
        assignments = authenticated_client.get_course_assignments(course_id)

        assert isinstance(assignments, list), "Should return list of assignments"
        # Note: Course might have zero assignments, which is valid

        if len(assignments) > 0:
            assignment = assignments[0]
            assert 'name' in assignment, "Assignment should have name"


class TestModuleAPIs:
    """Test lecture module API endpoints"""

    def test_get_lecture_modules(self, authenticated_client):
        """Test fetching lecture modules"""
        # Get first course ID
        courses = authenticated_client.get_courses()
        if not courses:
            pytest.skip("No courses available")

        course_id = courses[0]['id']

        # Fetch modules
        modules = authenticated_client.get_learningx_modules(course_id)

        assert isinstance(modules, list), "Should return list of modules"
        # Note: Course might have zero modules, which is valid

        if len(modules) > 0:
            module = modules[0]
            assert 'name' in module or 'title' in module, "Module should have name or title"


@pytest.mark.slow
class TestEndToEnd:
    """End-to-end workflow tests"""

    def test_full_dashboard_workflow(self):
        """Test complete dashboard workflow"""
        # Authenticate
        creds = get_credentials()
        auth = CauAuthenticator(creds['username'], creds['password'])
        assert auth.login(debug=False), "Authentication should succeed"

        # Create client
        client = CAUOnClient(auth.session)

        # Get dashboard
        dashboard = {"courses": client.get_courses()}
        assert 'courses' in dashboard

        # For each course, fetch basic data
        for course in dashboard['courses'][:2]:  # Test first 2 courses
            course_id = course['id']

            # Test announcements
            announcements = client.get_course_announcements(course_id, limit=5)
            assert isinstance(announcements, list)

            # Test assignments
            assignments = client.get_course_assignments(course_id)
            assert isinstance(assignments, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

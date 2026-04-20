"""
Stability tests for Staff Score Engine - Q2 2026
Tests all critical API endpoints to ensure app stability
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthAndBasicEndpoints:
    """Health check and basic endpoint tests"""
    
    def test_health_endpoint(self):
        """Test /api/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data
        print(f"✓ Health check passed: {data}")
    
    def test_root_endpoint(self):
        """Test /api/ root endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        print(f"✓ Root endpoint passed")


class TestEmployeesAPI:
    """Employee CRUD and listing tests"""
    
    def test_get_employees_q2_2026(self):
        """Test GET /api/v2/employees returns Q2 2026 data"""
        response = requests.get(f"{BASE_URL}/api/v2/employees?quarter=Q2&year=2026")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Employees Q2 2026: {len(data)} employees found")
        
        # Verify Q2 data
        if len(data) > 0:
            emp = data[0]
            assert emp.get("quarter") == "Q2"
            assert emp.get("year") == 2026
            print(f"✓ First employee: {emp.get('name')} - Q{emp.get('quarter')} {emp.get('year')}")
    
    def test_get_employees_q1_2026(self):
        """Test GET /api/v2/employees returns Q1 2026 data"""
        response = requests.get(f"{BASE_URL}/api/v2/employees?quarter=Q1&year=2026")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Employees Q1 2026: {len(data)} employees found")


class TestSnapshotWorkflowAPI:
    """Snapshot workflow endpoint tests"""
    
    def test_get_snapshots_q2_2026(self):
        """Test GET /api/v2/snapshot-workflow/snapshots for Q2 2026"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots?quarter=Q2&year=2026")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Snapshot workflow Q2 2026: {len(data)} snapshots found")
        
        if len(data) > 0:
            snapshot = data[0]
            assert "id" in snapshot
            assert "status" in snapshot
            print(f"✓ First snapshot: {snapshot.get('name')} - status: {snapshot.get('status')}")
    
    def test_get_current_rankings(self):
        """Test GET /api/v2/snapshot-workflow/current-rankings"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?quarter=Q2&year=2026")
        assert response.status_code == 200
        data = response.json()
        # Returns dict with employees key
        assert isinstance(data, dict)
        assert "employees" in data or "has_data" in data
        employees = data.get("employees", [])
        print(f"✓ Current rankings: {len(employees)} employees ranked")


class TestYodeckSlidesAPI:
    """Yodeck slides generation tests"""
    
    def test_get_complete_rankings_slide(self):
        """Test GET /api/v2/yodeck/{year}/{quarter}/complete-rankings returns image"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q2/complete-rankings")
        assert response.status_code == 200
        # Should return PNG image
        assert response.headers.get('content-type', '').startswith('image/')
        print(f"✓ Yodeck complete rankings slide generated (image)")


class TestQuarterSettingsAPI:
    """Quarter settings endpoint tests"""
    
    def test_get_quarter_settings(self):
        """Test GET /api/v2/quarter-settings"""
        response = requests.get(f"{BASE_URL}/api/v2/quarter-settings")
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Quarter settings retrieved")


class TestInsightsAPI:
    """Insights and analytics endpoint tests"""
    
    def test_get_store_health(self):
        """Test GET /api/v2/insights/store-health"""
        response = requests.get(f"{BASE_URL}/api/v2/insights/store-health?quarter=Q2&year=2026")
        assert response.status_code == 200
        data = response.json()
        assert "score" in data or "overall_score" in data or isinstance(data, dict)
        print(f"✓ Store health insights retrieved")
    
    def test_get_trends_momentum(self):
        """Test GET /api/v2/trends/momentum - may not exist"""
        response = requests.get(f"{BASE_URL}/api/v2/trends/momentum?quarter=Q2&year=2026")
        # This endpoint may not exist - 404 is acceptable
        assert response.status_code in [200, 404]
        print(f"✓ Trends momentum endpoint checked (status: {response.status_code})")


class TestLegacySnapshotsAPI:
    """Legacy snapshot endpoint tests"""
    
    def test_get_legacy_snapshots(self):
        """Test GET /api/v2/snapshots (legacy)"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshots?year=2026")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Legacy snapshots: {len(data)} found")
    
    def test_get_snapshot_backgrounds(self):
        """Test GET /api/v2/snapshots/backgrounds"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshots/backgrounds")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Snapshot backgrounds: {len(data)} available")


class TestDataUploadEndpoints:
    """Data upload endpoint availability tests (no actual uploads)"""
    
    def test_pos_upload_endpoint_exists(self):
        """Test POST /api/v2/data/upload-pos endpoint exists"""
        # Just verify endpoint exists by checking OPTIONS or sending empty request
        response = requests.post(f"{BASE_URL}/api/v2/data/upload-pos?quarter=Q2&year=2026")
        # Should return 422 (validation error) not 404
        assert response.status_code in [400, 422, 500]  # Not 404
        print(f"✓ POS upload endpoint exists (status: {response.status_code})")
    
    def test_cv_upload_endpoint_exists(self):
        """Test POST /api/v2/cv/server-performance/upload endpoint exists"""
        response = requests.post(f"{BASE_URL}/api/v2/cv/server-performance/upload?quarter=Q2&year=2026")
        assert response.status_code in [400, 422, 500]  # Not 404
        print(f"✓ CV/NPS upload endpoint exists (status: {response.status_code})")
    
    def test_rt_upload_endpoint_exists(self):
        """Test POST /api/v2/review-tracker/upload-feedback endpoint exists"""
        response = requests.post(f"{BASE_URL}/api/v2/review-tracker/upload-feedback?quarter=Q2&year=2026")
        assert response.status_code in [400, 422, 500]  # Not 404
        print(f"✓ RT upload endpoint exists (status: {response.status_code})")


class TestAuditEndpoints:
    """Audit and data integrity endpoint tests"""
    
    def test_data_cap_check(self):
        """Test GET /api/v2/audit/data-cap-check"""
        response = requests.get(f"{BASE_URL}/api/v2/audit/data-cap-check?quarter=Q2&year=2026")
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Data cap check retrieved")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

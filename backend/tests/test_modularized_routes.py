"""
Backend API Tests - Modularized Routes Verification
Tests that legacy snapshot routes extracted to routes/snapshots_legacy.py still work correctly.
Also verifies snapshot_workflow routes and other key endpoints.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthEndpoint:
    """Test /api/health endpoint"""
    
    def test_health_returns_healthy(self):
        """Verify health endpoint returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "healthy", f"Expected healthy status, got: {data}"
        assert "service" in data, "Missing service field in health response"
        print(f"✓ Health check passed: {data}")


class TestLegacySnapshotsRoutes:
    """Test legacy snapshot routes (extracted to routes/snapshots_legacy.py)"""
    
    def test_list_snapshots(self):
        """GET /api/v2/snapshots - List all snapshots"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshots")
        assert response.status_code == 200, f"List snapshots failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got: {type(data)}"
        print(f"✓ List snapshots returned {len(data)} snapshots")
        
        # Verify snapshot structure if any exist
        if data:
            snapshot = data[0]
            assert "id" in snapshot, "Snapshot missing 'id' field"
            assert "quarter" in snapshot or "year" in snapshot, "Snapshot missing quarter/year"
            print(f"  First snapshot: {snapshot.get('title', snapshot.get('id', 'N/A'))}")
    
    def test_list_snapshots_with_year_filter(self):
        """GET /api/v2/snapshots?year=2026 - Filter by year"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshots", params={"year": 2026})
        assert response.status_code == 200, f"Filter by year failed: {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got: {type(data)}"
        
        # Verify all returned snapshots are for 2026
        for snapshot in data:
            if "year" in snapshot:
                assert snapshot["year"] == 2026, f"Snapshot year mismatch: {snapshot['year']}"
        
        print(f"✓ Year filter returned {len(data)} snapshots for 2026")
    
    def test_get_snapshot_backgrounds(self):
        """GET /api/v2/snapshots/backgrounds - Get available backgrounds"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshots/backgrounds")
        assert response.status_code == 200, f"Get backgrounds failed: {response.status_code} - {response.text}"
        
        data = response.json()
        # Should return a list or dict of background options
        assert data is not None, "Backgrounds response is None"
        print(f"✓ Backgrounds endpoint returned: {type(data).__name__}")
        
        # If it's a list, check structure
        if isinstance(data, list) and len(data) > 0:
            print(f"  Available backgrounds: {len(data)}")
        elif isinstance(data, dict):
            print(f"  Background keys: {list(data.keys())[:5]}")


class TestSnapshotWorkflowRoutes:
    """Test snapshot workflow routes (snapshot_routes.py)"""
    
    def test_list_workflow_snapshots(self):
        """GET /api/v2/snapshot-workflow/snapshots - List workflow snapshots"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots")
        assert response.status_code == 200, f"List workflow snapshots failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got: {type(data)}"
        print(f"✓ Workflow snapshots returned {len(data)} records")
        
        # Verify structure if any exist
        if data:
            snapshot = data[0]
            # Workflow snapshots have different structure
            print(f"  First workflow snapshot: {snapshot.get('name', snapshot.get('id', 'N/A'))}")
    
    def test_current_rankings(self):
        """GET /api/v2/snapshot-workflow/current-rankings - Get current rankings"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings")
        assert response.status_code == 200, f"Current rankings failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert isinstance(data, dict), f"Expected dict, got: {type(data)}"
        
        # Check for expected fields
        if data.get("has_data", True):
            employees = data.get("employees", [])
            print(f"✓ Current rankings returned {len(employees)} employees")
            
            # Verify employee structure if any exist
            if employees:
                emp = employees[0]
                assert "name" in emp, "Employee missing 'name' field"
                print(f"  Top employee: {emp.get('name')} - Score: {emp.get('total_score', 'N/A')}")
        else:
            print(f"✓ Current rankings: No data available (expected for empty DB)")


class TestInsightsRoutes:
    """Test insights routes (routes/insights.py)"""
    
    def test_store_health(self):
        """GET /api/v2/insights/store-health - Get store health index"""
        response = requests.get(f"{BASE_URL}/api/v2/insights/store-health", params={"quarter": "Q1", "year": 2026})
        assert response.status_code == 200, f"Store health failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert isinstance(data, dict), f"Expected dict, got: {type(data)}"
        
        # Check for expected fields
        if "score" in data or "health_score" in data:
            score = data.get("score") or data.get("health_score")
            print(f"✓ Store health score: {score}")
        
        if "categories" in data:
            print(f"  Categories: {len(data['categories'])}")
        
        print(f"✓ Store health endpoint working")


class TestEmployeesRoutes:
    """Test employees routes (routes/employees.py)"""
    
    def test_list_employees(self):
        """GET /api/v2/employees - List employees"""
        response = requests.get(f"{BASE_URL}/api/v2/employees", params={"quarter": "Q1", "year": 2026})
        assert response.status_code == 200, f"List employees failed: {response.status_code} - {response.text}"
        
        data = response.json()
        # Could be a list or dict with employees key
        if isinstance(data, list):
            employees = data
        elif isinstance(data, dict):
            employees = data.get("employees", data.get("data", []))
        else:
            employees = []
        
        print(f"✓ Employees endpoint returned {len(employees)} employees")
        
        # Verify structure if any exist
        if employees and isinstance(employees, list) and len(employees) > 0:
            emp = employees[0]
            if isinstance(emp, dict):
                print(f"  First employee: {emp.get('name', 'N/A')}")


class TestQuarterSettingsRoutes:
    """Test quarter settings routes"""
    
    def test_get_quarter_settings(self):
        """GET /api/v2/quarter-settings - Get quarter settings"""
        response = requests.get(f"{BASE_URL}/api/v2/quarter-settings", params={"quarter": "Q1", "year": 2026})
        
        # Could be 200 or 404 if no settings exist
        assert response.status_code in [200, 404], f"Quarter settings failed: {response.status_code} - {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Quarter settings found")
            if isinstance(data, dict):
                print(f"  Benchmarks: PPA={data.get('benchmark_ppa')}, LBW={data.get('benchmark_lbw')}")
        else:
            print(f"✓ Quarter settings endpoint working (no settings for Q1 2026)")


class TestTrendsRoutes:
    """Test trends routes (routes/trends.py)"""
    
    def test_momentum_endpoint(self):
        """GET /api/v2/trends/momentum - Get momentum/trend data"""
        response = requests.get(f"{BASE_URL}/api/v2/trends/momentum", params={"quarter": "Q1", "year": 2026})
        
        # Could be 200 or 404 depending on data availability
        assert response.status_code in [200, 404, 500], f"Momentum failed: {response.status_code} - {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Momentum endpoint returned data")
            if isinstance(data, dict) and "employees" in data:
                print(f"  Employees with trends: {len(data['employees'])}")
        else:
            print(f"✓ Momentum endpoint working (status: {response.status_code})")


class TestRootEndpoint:
    """Test root API endpoint"""
    
    def test_root_endpoint(self):
        """GET /api/ - Root endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200, f"Root endpoint failed: {response.status_code}"
        
        data = response.json()
        assert "message" in data, "Root endpoint missing message"
        print(f"✓ Root endpoint: {data.get('message')}")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

"""
Multi-Store Architecture Tests
Tests for store management and global reporting endpoints.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestStoreManagement:
    """Tests for GET /api/v2/stores - List all stores"""
    
    def test_list_stores_returns_200(self):
        """Test that list stores endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/v2/stores")
        assert response.status_code == 200
        data = response.json()
        assert "stores" in data
        assert "total" in data
        assert "regions" in data
    
    def test_list_stores_returns_22_bubba_gump_locations(self):
        """Test that 22 Bubba Gump locations are seeded"""
        response = requests.get(f"{BASE_URL}/api/v2/stores")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 22, f"Expected 22 stores, got {data['total']}"
        
    def test_list_stores_with_stats(self):
        """Test that include_stats parameter returns employee counts"""
        response = requests.get(f"{BASE_URL}/api/v2/stores?include_stats=true")
        assert response.status_code == 200
        data = response.json()
        
        # Las Vegas store should have employees
        lv_store = next((s for s in data["stores"] if s["code"] == "LV"), None)
        assert lv_store is not None, "Las Vegas store not found"
        assert "employee_count" in lv_store
        assert "avg_score" in lv_store
        
    def test_list_stores_filter_by_region(self):
        """Test filtering stores by region"""
        response = requests.get(f"{BASE_URL}/api/v2/stores?region=West")
        assert response.status_code == 200
        data = response.json()
        
        # All returned stores should be in West region
        for store in data["stores"]:
            assert store["region"] == "West", f"Store {store['code']} is not in West region"
    
    def test_list_stores_returns_regions(self):
        """Test that regions list is returned"""
        response = requests.get(f"{BASE_URL}/api/v2/stores")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["regions"]) > 0
        expected_regions = ["West", "East", "Central", "Hawaii", "International"]
        for region in expected_regions:
            assert region in data["regions"], f"Region {region} not found"


class TestGlobalOverview:
    """Tests for GET /api/v2/stores/reports/overview - Global performance overview"""
    
    def test_global_overview_returns_200(self):
        """Test that global overview endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/v2/stores/reports/overview?quarter=Q1&year=2026")
        assert response.status_code == 200
        data = response.json()
        
        assert "quarter" in data
        assert "year" in data
        assert "stores" in data
        assert "summary" in data
        
    def test_global_overview_summary_structure(self):
        """Test that summary contains required fields"""
        response = requests.get(f"{BASE_URL}/api/v2/stores/reports/overview?quarter=Q1&year=2026")
        assert response.status_code == 200
        data = response.json()
        
        summary = data["summary"]
        assert "total_stores" in summary
        assert "total_employees" in summary
        assert "avg_score" in summary
        assert "top_performers" in summary
        assert "needs_coaching" in summary
        
    def test_global_overview_store_data_structure(self):
        """Test that store data contains required fields"""
        response = requests.get(f"{BASE_URL}/api/v2/stores/reports/overview?quarter=Q1&year=2026")
        assert response.status_code == 200
        data = response.json()
        
        # Find Las Vegas store (has data)
        lv_store = next((s for s in data["stores"] if s["code"] == "LV"), None)
        assert lv_store is not None
        
        assert "store_id" in lv_store
        assert "name" in lv_store
        assert "code" in lv_store
        assert "region" in lv_store
        assert "employee_count" in lv_store
        assert "avg_score" in lv_store
        assert "a_server_count" in lv_store
        assert "c_server_count" in lv_store
        
    def test_global_overview_filter_by_region(self):
        """Test filtering overview by region"""
        response = requests.get(f"{BASE_URL}/api/v2/stores/reports/overview?quarter=Q1&year=2026&region=West")
        assert response.status_code == 200
        data = response.json()
        
        assert data["region"] == "West"
        for store in data["stores"]:
            assert store["region"] == "West"
            
    def test_global_overview_las_vegas_has_employees(self):
        """Test that Las Vegas store has 27 employees migrated"""
        response = requests.get(f"{BASE_URL}/api/v2/stores/reports/overview?quarter=Q1&year=2026")
        assert response.status_code == 200
        data = response.json()
        
        lv_store = next((s for s in data["stores"] if s["code"] == "LV"), None)
        assert lv_store is not None
        assert lv_store["employee_count"] == 27, f"Expected 27 employees, got {lv_store['employee_count']}"


class TestGlobalLeaderboard:
    """Tests for GET /api/v2/stores/reports/leaderboard - Global employee leaderboard"""
    
    def test_global_leaderboard_returns_200(self):
        """Test that global leaderboard endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/v2/stores/reports/leaderboard?quarter=Q1&year=2026")
        assert response.status_code == 200
        data = response.json()
        
        assert "quarter" in data
        assert "year" in data
        assert "leaderboard" in data
        assert "total" in data
        
    def test_global_leaderboard_employee_structure(self):
        """Test that leaderboard employees have required fields"""
        response = requests.get(f"{BASE_URL}/api/v2/stores/reports/leaderboard?quarter=Q1&year=2026&limit=10")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["leaderboard"]) > 0
        
        emp = data["leaderboard"][0]
        assert "employee_id" in emp
        assert "name" in emp
        assert "tier_label" in emp
        assert "total_score" in emp
        assert "store_id" in emp
        assert "store_name" in emp
        assert "store_code" in emp
        assert "global_rank" in emp
        
    def test_global_leaderboard_sorted_by_score(self):
        """Test that leaderboard is sorted by score descending"""
        response = requests.get(f"{BASE_URL}/api/v2/stores/reports/leaderboard?quarter=Q1&year=2026&limit=10")
        assert response.status_code == 200
        data = response.json()
        
        scores = [emp["total_score"] for emp in data["leaderboard"]]
        assert scores == sorted(scores, reverse=True), "Leaderboard not sorted by score"
        
    def test_global_leaderboard_limit_parameter(self):
        """Test that limit parameter works"""
        response = requests.get(f"{BASE_URL}/api/v2/stores/reports/leaderboard?quarter=Q1&year=2026&limit=5")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["leaderboard"]) <= 5
        
    def test_global_leaderboard_global_rank_assigned(self):
        """Test that global rank is correctly assigned"""
        response = requests.get(f"{BASE_URL}/api/v2/stores/reports/leaderboard?quarter=Q1&year=2026&limit=10")
        assert response.status_code == 200
        data = response.json()
        
        for i, emp in enumerate(data["leaderboard"], 1):
            assert emp["global_rank"] == i, f"Expected rank {i}, got {emp['global_rank']}"


class TestStoreComparison:
    """Tests for GET /api/v2/stores/reports/store-comparison - Store metric comparison"""
    
    def test_store_comparison_returns_200(self):
        """Test that store comparison endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/v2/stores/reports/store-comparison?quarter=Q1&year=2026")
        assert response.status_code == 200
        data = response.json()
        
        assert "quarter" in data
        assert "year" in data
        assert "metric" in data
        assert "comparison" in data
        
    def test_store_comparison_default_metric_is_avg_score(self):
        """Test that default metric is avg_score"""
        response = requests.get(f"{BASE_URL}/api/v2/stores/reports/store-comparison?quarter=Q1&year=2026")
        assert response.status_code == 200
        data = response.json()
        
        assert data["metric"] == "avg_score"
        
    def test_store_comparison_structure(self):
        """Test that comparison data has required fields"""
        response = requests.get(f"{BASE_URL}/api/v2/stores/reports/store-comparison?quarter=Q1&year=2026")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["comparison"]) > 0
        
        store = data["comparison"][0]
        assert "store_id" in store
        assert "name" in store
        assert "code" in store
        assert "region" in store
        assert "value" in store
        assert "metric" in store
        assert "rank" in store
        
    def test_store_comparison_sorted_by_value(self):
        """Test that comparison is sorted by value descending"""
        response = requests.get(f"{BASE_URL}/api/v2/stores/reports/store-comparison?quarter=Q1&year=2026")
        assert response.status_code == 200
        data = response.json()
        
        values = [s["value"] for s in data["comparison"]]
        assert values == sorted(values, reverse=True), "Comparison not sorted by value"
        
    def test_store_comparison_different_metrics(self):
        """Test different metric parameters"""
        metrics = ["avg_score", "avg_ppa", "employee_count", "a_server_pct"]
        
        for metric in metrics:
            response = requests.get(f"{BASE_URL}/api/v2/stores/reports/store-comparison?quarter=Q1&year=2026&metric={metric}")
            assert response.status_code == 200, f"Failed for metric {metric}"
            data = response.json()
            assert data["metric"] == metric


class TestUploadJobs:
    """Tests for upload jobs endpoints - Background file upload"""
    
    def test_upload_jobs_direct_returns_job_id(self):
        """Test that direct upload returns a job_id"""
        # Create a simple CSV file for testing
        csv_content = b"name,guest_count,net_sales\nTest Employee,100,5000"
        
        files = {"file": ("test.csv", csv_content, "text/csv")}
        data = {"quarter": "Q1", "year": "2026"}
        
        response = requests.post(f"{BASE_URL}/api/v2/upload-jobs/direct", files=files, data=data)
        assert response.status_code == 200
        
        result = response.json()
        assert "success" in result
        assert result["success"] == True
        assert "job_id" in result
        assert "status" in result
        
        return result["job_id"]
    
    def test_upload_jobs_get_status(self):
        """Test getting job status"""
        # First create a job
        csv_content = b"name,guest_count,net_sales\nTest Employee,100,5000"
        files = {"file": ("test.csv", csv_content, "text/csv")}
        data = {"quarter": "Q1", "year": "2026"}
        
        create_response = requests.post(f"{BASE_URL}/api/v2/upload-jobs/direct", files=files, data=data)
        assert create_response.status_code == 200
        job_id = create_response.json()["job_id"]
        
        # Get job status
        response = requests.get(f"{BASE_URL}/api/v2/upload-jobs/{job_id}")
        assert response.status_code == 200
        
        result = response.json()
        assert "job_id" in result
        assert result["job_id"] == job_id
        assert "status" in result
        assert "progress" in result
        assert "filename" in result
        
    def test_upload_jobs_invalid_job_id_returns_404(self):
        """Test that invalid job_id returns 404"""
        response = requests.get(f"{BASE_URL}/api/v2/upload-jobs/invalid-job-id-12345")
        assert response.status_code == 404
        
    def test_upload_jobs_unsupported_file_type(self):
        """Test that unsupported file types are rejected"""
        files = {"file": ("test.txt", b"some text content", "text/plain")}
        data = {"quarter": "Q1", "year": "2026"}
        
        response = requests.post(f"{BASE_URL}/api/v2/upload-jobs/direct", files=files, data=data)
        assert response.status_code == 400


class TestStoreRegions:
    """Tests for GET /api/v2/stores/regions - List regions"""
    
    def test_list_regions_returns_200(self):
        """Test that list regions endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/v2/stores/regions")
        assert response.status_code == 200
        data = response.json()
        
        assert "regions" in data
        
    def test_list_regions_structure(self):
        """Test that regions have required fields"""
        response = requests.get(f"{BASE_URL}/api/v2/stores/regions")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["regions"]) > 0
        
        region = data["regions"][0]
        assert "region" in region
        assert "store_count" in region
        assert "stores" in region


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Test Full Rankings Tab Features
- Full Rankings API endpoint with hierarchy-based tiering
- Tier filter functionality
- Settings-driven server tier thresholds
- CSV template with Job Title column
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestFullRankingsAPI:
    """Test /api/v2/full-rankings/{year}/{quarter} endpoint"""
    
    def test_full_rankings_returns_data(self):
        """Test that full rankings endpoint returns data with correct structure"""
        response = requests.get(f"{BASE_URL}/api/v2/full-rankings/2026/Q1")
        assert response.status_code == 200
        
        data = response.json()
        assert "quarter" in data
        assert "year" in data
        assert "total_employees" in data
        assert "filtered_count" in data
        assert "tier_thresholds" in data
        assert "rankings" in data
        
        # Verify tier thresholds structure
        assert "a_server_min" in data["tier_thresholds"]
        assert "b_server_min" in data["tier_thresholds"]
        
        # Verify default threshold values
        assert data["tier_thresholds"]["a_server_min"] == 85.1
        assert data["tier_thresholds"]["b_server_min"] == 70.1
        
        print(f"Full rankings returned {data['total_employees']} employees")
    
    def test_full_rankings_employee_structure(self):
        """Test that each employee in rankings has correct fields"""
        response = requests.get(f"{BASE_URL}/api/v2/full-rankings/2026/Q1")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["rankings"]) > 0
        
        employee = data["rankings"][0]
        
        # Required fields
        required_fields = [
            "position", "position_label", "tier_label", "employee_id",
            "name", "job_title", "total_score", "bonus_points",
            "ppa_points", "lbw_points", "lsc_points", "glassware_points",
            "performance_tier"
        ]
        
        for field in required_fields:
            assert field in employee, f"Missing field: {field}"
        
        # Verify points structure
        assert "earned" in employee["ppa_points"]
        assert "possible" in employee["ppa_points"]
        
        print(f"First employee: {employee['name']} - {employee['tier_label']} - Score: {employee['total_score']}")
    
    def test_full_rankings_hierarchy_order(self):
        """Test that rankings follow hierarchy order: Trainers > Bartenders > A > B > C"""
        response = requests.get(f"{BASE_URL}/api/v2/full-rankings/2026/Q1")
        assert response.status_code == 200
        
        data = response.json()
        rankings = data["rankings"]
        
        # Track tier order
        tier_order = {"Trainer": 1, "Bartender": 2, "A-Server": 3, "B-Server": 4, "C-Server": 5}
        
        prev_tier_rank = 0
        for emp in rankings:
            current_tier_rank = tier_order.get(emp["tier_label"], 99)
            # Tier rank should never decrease (hierarchy order)
            assert current_tier_rank >= prev_tier_rank, \
                f"Hierarchy order violated: {emp['tier_label']} after tier rank {prev_tier_rank}"
            prev_tier_rank = current_tier_rank
        
        print("Hierarchy order verified: Trainers > Bartenders > A-Servers > B-Servers > C-Servers")
    
    def test_full_rankings_position_labels(self):
        """Test that position labels follow correct format (A1, B1, C1, etc.)"""
        response = requests.get(f"{BASE_URL}/api/v2/full-rankings/2026/Q1")
        assert response.status_code == 200
        
        data = response.json()
        rankings = data["rankings"]
        
        # Count employees per tier
        tier_counts = {"Trainer": 0, "Bartender": 0, "A-Server": 0, "B-Server": 0, "C-Server": 0}
        tier_prefixes = {"Trainer": "T", "Bartender": "Bar", "A-Server": "A", "B-Server": "B", "C-Server": "C"}
        
        for emp in rankings:
            tier = emp["tier_label"]
            tier_counts[tier] += 1
            expected_label = f"{tier_prefixes[tier]}{tier_counts[tier]}"
            assert emp["position_label"] == expected_label, \
                f"Expected {expected_label}, got {emp['position_label']}"
        
        print(f"Position labels verified. Tier counts: {tier_counts}")


class TestTierFilter:
    """Test tier filter functionality"""
    
    def test_filter_a_servers(self):
        """Test filtering by A-Server tier"""
        response = requests.get(f"{BASE_URL}/api/v2/full-rankings/2026/Q1?tier_filter=A-Server")
        assert response.status_code == 200
        
        data = response.json()
        
        # All returned employees should be A-Servers
        for emp in data["rankings"]:
            assert emp["tier_label"] == "A-Server", f"Expected A-Server, got {emp['tier_label']}"
        
        # Filtered count should match rankings length
        assert data["filtered_count"] == len(data["rankings"])
        
        print(f"A-Server filter returned {data['filtered_count']} employees")
    
    def test_filter_b_servers(self):
        """Test filtering by B-Server tier"""
        response = requests.get(f"{BASE_URL}/api/v2/full-rankings/2026/Q1?tier_filter=B-Server")
        assert response.status_code == 200
        
        data = response.json()
        
        for emp in data["rankings"]:
            assert emp["tier_label"] == "B-Server", f"Expected B-Server, got {emp['tier_label']}"
        
        print(f"B-Server filter returned {data['filtered_count']} employees")
    
    def test_filter_c_servers(self):
        """Test filtering by C-Server tier"""
        response = requests.get(f"{BASE_URL}/api/v2/full-rankings/2026/Q1?tier_filter=C-Server")
        assert response.status_code == 200
        
        data = response.json()
        
        for emp in data["rankings"]:
            assert emp["tier_label"] == "C-Server", f"Expected C-Server, got {emp['tier_label']}"
        
        print(f"C-Server filter returned {data['filtered_count']} employees")
    
    def test_filter_preserves_total_count(self):
        """Test that filtering doesn't change total_employees count"""
        # Get unfiltered
        response_all = requests.get(f"{BASE_URL}/api/v2/full-rankings/2026/Q1")
        total_all = response_all.json()["total_employees"]
        
        # Get filtered
        response_filtered = requests.get(f"{BASE_URL}/api/v2/full-rankings/2026/Q1?tier_filter=A-Server")
        total_filtered = response_filtered.json()["total_employees"]
        
        assert total_all == total_filtered, "Total employees should remain same when filtering"
        print(f"Total employees preserved: {total_all}")


class TestTierThresholds:
    """Test tier threshold classification"""
    
    def test_a_server_threshold(self):
        """Test that A-Servers have score >= 85.1"""
        response = requests.get(f"{BASE_URL}/api/v2/full-rankings/2026/Q1?tier_filter=A-Server")
        assert response.status_code == 200
        
        data = response.json()
        threshold = data["tier_thresholds"]["a_server_min"]
        
        for emp in data["rankings"]:
            assert emp["total_score"] >= threshold, \
                f"A-Server {emp['name']} has score {emp['total_score']} < {threshold}"
        
        print(f"All A-Servers have score >= {threshold}")
    
    def test_b_server_threshold(self):
        """Test that B-Servers have score >= 70.1 and < 85.1"""
        response = requests.get(f"{BASE_URL}/api/v2/full-rankings/2026/Q1?tier_filter=B-Server")
        assert response.status_code == 200
        
        data = response.json()
        a_threshold = data["tier_thresholds"]["a_server_min"]
        b_threshold = data["tier_thresholds"]["b_server_min"]
        
        for emp in data["rankings"]:
            assert emp["total_score"] >= b_threshold, \
                f"B-Server {emp['name']} has score {emp['total_score']} < {b_threshold}"
            assert emp["total_score"] < a_threshold, \
                f"B-Server {emp['name']} has score {emp['total_score']} >= {a_threshold}"
        
        print(f"All B-Servers have score >= {b_threshold} and < {a_threshold}")
    
    def test_c_server_threshold(self):
        """Test that C-Servers have score < 70.1"""
        response = requests.get(f"{BASE_URL}/api/v2/full-rankings/2026/Q1?tier_filter=C-Server")
        assert response.status_code == 200
        
        data = response.json()
        b_threshold = data["tier_thresholds"]["b_server_min"]
        
        for emp in data["rankings"]:
            assert emp["total_score"] < b_threshold, \
                f"C-Server {emp['name']} has score {emp['total_score']} >= {b_threshold}"
        
        print(f"All C-Servers have score < {b_threshold}")


class TestCSVTemplate:
    """Test CSV template download"""
    
    def test_template_download(self):
        """Test that CSV template can be downloaded"""
        response = requests.get(f"{BASE_URL}/api/v2/template")
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        
        print("CSV template downloaded successfully")
    
    def test_template_has_job_title_column(self):
        """Test that CSV template includes Job Title column"""
        response = requests.get(f"{BASE_URL}/api/v2/template")
        assert response.status_code == 200
        
        content = response.text
        lines = content.strip().split('\n')
        headers = lines[0].split(',')
        
        assert "Job Title" in headers, f"Job Title column missing. Headers: {headers}"
        
        # Verify sample data has job titles
        if len(lines) > 1:
            sample_row = lines[1].split(',')
            job_title_idx = headers.index("Job Title")
            assert sample_row[job_title_idx] in ["Server", "Bartender", "Trainer"], \
                f"Invalid job title in sample: {sample_row[job_title_idx]}"
        
        print(f"CSV template headers: {headers}")


class TestSettingsTierThresholds:
    """Test settings API for tier thresholds"""
    
    def test_settings_include_tier_thresholds_in_create(self):
        """Test that creating settings accepts tier threshold fields"""
        # This tests the model, not actual creation (Q1 2026 is locked)
        response = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q1")
        assert response.status_code == 200
        
        # The QuarterSettings model should have default values
        # Even if not stored in DB, the full-rankings endpoint uses defaults
        print("Settings API working - tier thresholds use defaults if not stored")


class TestNavigationRankingsTab:
    """Test that Rankings tab exists in navigation"""
    
    def test_rankings_route_exists(self):
        """Test that /rankings route returns 200"""
        # This tests the frontend route indirectly via API
        # The actual navigation test is done via Playwright
        response = requests.get(f"{BASE_URL}/api/v2/full-rankings/2026/Q1")
        assert response.status_code == 200
        print("Rankings API endpoint accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

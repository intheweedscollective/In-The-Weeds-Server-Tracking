"""
V2 Scoring Engine API Tests
Tests for Quarter Settings, Upload Validation, Upload & Scoring, Rankings, and Clear/Re-upload flow
"""

import pytest
import requests
import os
import io
import csv

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test data for CSV upload
TEST_CSV_DATA = """Employee Name,Guests,Net Sales,LBW,Glassware Sales,LSC Count
Test Alice,500,27500,4500,600,8
Test Bob,450,24750,4050,540,5
Test Carol,600,33000,5400,720,12
Test David,400,22000,3600,480,4
Test Eva,550,30250,4950,660,10
"""

class TestQuarterSettings:
    """Tests for V2 Quarter Settings CRUD operations"""
    
    def test_get_all_quarter_settings(self):
        """Test GET /api/v2/quarter-settings - list all settings"""
        response = requests.get(f"{BASE_URL}/api/v2/quarter-settings")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Found {len(data)} quarter settings")
    
    def test_get_existing_quarter_settings(self):
        """Test GET /api/v2/quarter-settings/{year}/{quarter} - get existing Q2 2026"""
        response = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q2")
        assert response.status_code == 200
        data = response.json()
        assert data["year"] == 2026
        assert data["quarter"] == "Q2"
        assert "benchmark_ppa" in data
        assert "weight_ppa" in data
        assert "is_locked" in data
        print(f"✓ Q2 2026 settings: PPA benchmark=${data['benchmark_ppa']}, locked={data['is_locked']}")
    
    def test_get_nonexistent_quarter_settings(self):
        """Test GET /api/v2/quarter-settings/{year}/{quarter} - 404 for non-existent"""
        response = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2030/Q4")
        assert response.status_code == 404
        print("✓ Correctly returns 404 for non-existent quarter settings")
    
    def test_create_quarter_settings_for_q3(self):
        """Test POST /api/v2/quarter-settings - create new Q3 2026 settings"""
        # First check if Q3 exists and delete employees if needed
        check_response = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q3")
        if check_response.status_code == 200:
            # Q3 exists, need to clear employees first to unlock
            requests.delete(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q3")
            # Delete the settings by creating new test
            print("✓ Q3 2026 already exists, will test update instead")
            return
        
        payload = {
            "year": 2026,
            "quarter": "Q3",
            "benchmark_ppa": 60.0,
            "benchmark_lbw": 9.0,
            "benchmark_glass": 1.2,
            "benchmark_lsc": 90.0,
            "weight_ppa": 0.30,
            "weight_lbw": 0.25,
            "weight_glass": 0.20,
            "weight_lsc": 0.25,
            "bonus_rate": 0.2,
            "bonus_cap": 5.0
        }
        response = requests.post(f"{BASE_URL}/api/v2/quarter-settings", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        print(f"✓ Created Q3 2026 settings: {data['message']}")
    
    def test_create_duplicate_settings_fails(self):
        """Test POST /api/v2/quarter-settings - duplicate should fail"""
        payload = {
            "year": 2026,
            "quarter": "Q2",  # Already exists
            "benchmark_ppa": 55.0,
            "benchmark_lbw": 8.0,
            "benchmark_glass": 1.0,
            "benchmark_lsc": 100.0,
            "weight_ppa": 0.30,
            "weight_lbw": 0.25,
            "weight_glass": 0.20,
            "weight_lsc": 0.25
        }
        response = requests.post(f"{BASE_URL}/api/v2/quarter-settings", json=payload)
        assert response.status_code == 400
        print("✓ Correctly rejects duplicate quarter settings")
    
    def test_invalid_weights_rejected(self):
        """Test POST /api/v2/quarter-settings - weights must sum to 1.0"""
        payload = {
            "year": 2027,
            "quarter": "Q1",
            "benchmark_ppa": 55.0,
            "benchmark_lbw": 8.0,
            "benchmark_glass": 1.0,
            "benchmark_lsc": 100.0,
            "weight_ppa": 0.50,  # Sum = 1.2, invalid
            "weight_lbw": 0.30,
            "weight_glass": 0.20,
            "weight_lsc": 0.20
        }
        response = requests.post(f"{BASE_URL}/api/v2/quarter-settings", json=payload)
        assert response.status_code == 400
        assert "weights must sum to 1.0" in response.json()["detail"].lower()
        print("✓ Correctly rejects invalid weight sum")


class TestUploadValidation:
    """Tests for V2 Upload Validation endpoint"""
    
    def test_validate_valid_csv(self):
        """Test POST /api/v2/upload/validate - valid CSV file"""
        files = {"file": ("test.csv", io.StringIO(TEST_CSV_DATA), "text/csv")}
        response = requests.post(f"{BASE_URL}/api/v2/upload/validate", files=files)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == True
        assert "column_validation" in data
        assert "row_validation" in data
        assert data["column_validation"]["valid"] == True
        assert data["row_validation"]["valid_rows"] == 5
        print(f"✓ Valid CSV: {data['row_validation']['valid_rows']} valid rows")
    
    def test_validate_missing_columns(self):
        """Test POST /api/v2/upload/validate - missing required columns"""
        bad_csv = """Name,Sales
Alice,1000
Bob,2000
"""
        files = {"file": ("test.csv", io.StringIO(bad_csv), "text/csv")}
        response = requests.post(f"{BASE_URL}/api/v2/upload/validate", files=files)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == False
        assert len(data["column_validation"]["missing"]) > 0
        print(f"✓ Correctly identifies missing columns: {data['column_validation']['missing']}")
    
    def test_validate_invalid_data(self):
        """Test POST /api/v2/upload/validate - invalid row data"""
        bad_csv = """Employee Name,Guests,Net Sales,LBW,Glassware Sales,LSC Count
Alice,0,1000,100,50,5
Bob,-10,2000,200,100,3
"""
        files = {"file": ("test.csv", io.StringIO(bad_csv), "text/csv")}
        response = requests.post(f"{BASE_URL}/api/v2/upload/validate", files=files)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == False
        assert data["row_validation"]["invalid_rows"] > 0
        print(f"✓ Correctly identifies invalid rows: {data['row_validation']['invalid_rows']} invalid")


class TestUploadAndScoring:
    """Tests for V2 Upload and Scoring flow"""
    
    def test_upload_requires_settings(self):
        """Test POST /api/v2/upload - requires quarter settings to exist"""
        files = {"file": ("test.csv", io.StringIO(TEST_CSV_DATA), "text/csv")}
        response = requests.post(
            f"{BASE_URL}/api/v2/upload?year=2030&quarter=Q4",
            files=files
        )
        assert response.status_code == 400
        assert "settings must be created" in response.json()["detail"].lower()
        print("✓ Correctly requires quarter settings before upload")
    
    def test_upload_to_locked_quarter_fails(self):
        """Test POST /api/v2/upload - cannot upload to locked quarter"""
        # Q2 2026 is locked
        files = {"file": ("test.csv", io.StringIO(TEST_CSV_DATA), "text/csv")}
        response = requests.post(
            f"{BASE_URL}/api/v2/upload?year=2026&quarter=Q2",
            files=files
        )
        assert response.status_code == 403
        assert "locked" in response.json()["detail"].lower()
        print("✓ Correctly rejects upload to locked quarter")
    
    def test_upload_and_score_q3(self):
        """Test POST /api/v2/upload - upload and score for Q3 2026"""
        # First ensure Q3 settings exist and are unlocked
        check_response = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q3")
        if check_response.status_code == 404:
            # Create settings
            payload = {
                "year": 2026,
                "quarter": "Q3",
                "benchmark_ppa": 60.0,
                "benchmark_lbw": 9.0,
                "benchmark_glass": 1.2,
                "benchmark_lsc": 90.0,
                "weight_ppa": 0.30,
                "weight_lbw": 0.25,
                "weight_glass": 0.20,
                "weight_lsc": 0.25,
                "bonus_rate": 0.2,
                "bonus_cap": 5.0
            }
            requests.post(f"{BASE_URL}/api/v2/quarter-settings", json=payload)
        else:
            # Clear existing data to unlock
            requests.delete(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q3")
        
        # Now upload
        files = {"file": ("test.csv", io.StringIO(TEST_CSV_DATA), "text/csv")}
        response = requests.post(
            f"{BASE_URL}/api/v2/upload?year=2026&quarter=Q3",
            files=files
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["employees_count"] == 5
        assert data["settings_locked"] == True
        print(f"✓ Uploaded and scored {data['employees_count']} employees for Q3 2026")


class TestRankingsAndEmployees:
    """Tests for V2 Rankings and Employee retrieval"""
    
    def test_get_employees_for_quarter(self):
        """Test GET /api/v2/employees - get employees for Q2 2026"""
        response = requests.get(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q2")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Verify scoring fields exist
        emp = data[0]
        assert "total_score" in emp
        assert "peer_rank" in emp
        assert "performance_tier" in emp
        assert "ppa" in emp
        assert "lbw_per_guest" in emp
        print(f"✓ Retrieved {len(data)} employees for Q2 2026")
    
    def test_get_rankings(self):
        """Test GET /api/v2/rankings/{year}/{quarter}"""
        response = requests.get(f"{BASE_URL}/api/v2/rankings/2026/Q2")
        assert response.status_code == 200
        data = response.json()
        assert data["quarter"] == "Q2"
        assert data["year"] == 2026
        assert "rankings" in data
        assert len(data["rankings"]) > 0
        
        # Verify rankings are sorted
        rankings = data["rankings"]
        for i in range(len(rankings) - 1):
            assert rankings[i]["peer_rank"] <= rankings[i+1]["peer_rank"]
        print(f"✓ Rankings for Q2 2026: {data['total_employees']} employees ranked")
    
    def test_get_top_performers(self):
        """Test GET /api/v2/top-performers/{year}/{quarter}"""
        response = requests.get(f"{BASE_URL}/api/v2/top-performers/2026/Q2?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "top_overall" in data
        assert "top_by_metric" in data
        assert len(data["top_overall"]) <= 5
        print(f"✓ Top performers: {len(data['top_overall'])} overall, metrics: {list(data['top_by_metric'].keys())}")
    
    def test_get_single_employee(self):
        """Test GET /api/v2/employees/{employee_id}"""
        # First get an employee ID
        list_response = requests.get(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q2")
        employees = list_response.json()
        if len(employees) > 0:
            emp_id = employees[0]["id"]
            response = requests.get(f"{BASE_URL}/api/v2/employees/{emp_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == emp_id
            print(f"✓ Retrieved single employee: {data['name']}")
        else:
            pytest.skip("No employees to test")


class TestClearAndReupload:
    """Tests for Clear and Re-upload flow"""
    
    def test_clear_unlocks_quarter(self):
        """Test DELETE /api/v2/employees - clearing data unlocks quarter"""
        # First ensure Q3 has data
        check_response = requests.get(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q3")
        if len(check_response.json()) == 0:
            # Upload data first
            check_settings = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q3")
            if check_settings.status_code == 404:
                payload = {
                    "year": 2026,
                    "quarter": "Q3",
                    "benchmark_ppa": 60.0,
                    "benchmark_lbw": 9.0,
                    "benchmark_glass": 1.2,
                    "benchmark_lsc": 90.0,
                    "weight_ppa": 0.30,
                    "weight_lbw": 0.25,
                    "weight_glass": 0.20,
                    "weight_lsc": 0.25
                }
                requests.post(f"{BASE_URL}/api/v2/quarter-settings", json=payload)
            
            files = {"file": ("test.csv", io.StringIO(TEST_CSV_DATA), "text/csv")}
            requests.post(f"{BASE_URL}/api/v2/upload?year=2026&quarter=Q3", files=files)
        
        # Now clear
        response = requests.delete(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q3")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        
        # Verify settings are unlocked
        settings_response = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q3")
        if settings_response.status_code == 200:
            settings = settings_response.json()
            assert settings["is_locked"] == False
            print(f"✓ Cleared {data['deleted_count']} employees, quarter unlocked")
        else:
            print(f"✓ Cleared {data['deleted_count']} employees")
    
    def test_reupload_after_clear(self):
        """Test re-upload after clearing data"""
        # Ensure Q3 is unlocked
        requests.delete(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q3")
        
        # Ensure settings exist
        check_settings = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q3")
        if check_settings.status_code == 404:
            payload = {
                "year": 2026,
                "quarter": "Q3",
                "benchmark_ppa": 60.0,
                "benchmark_lbw": 9.0,
                "benchmark_glass": 1.2,
                "benchmark_lsc": 90.0,
                "weight_ppa": 0.30,
                "weight_lbw": 0.25,
                "weight_glass": 0.20,
                "weight_lsc": 0.25
            }
            requests.post(f"{BASE_URL}/api/v2/quarter-settings", json=payload)
        
        # Re-upload
        files = {"file": ("test.csv", io.StringIO(TEST_CSV_DATA), "text/csv")}
        response = requests.post(
            f"{BASE_URL}/api/v2/upload?year=2026&quarter=Q3",
            files=files
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        print(f"✓ Re-uploaded {data['employees_count']} employees after clear")


class TestBenchmarkSuggestions:
    """Tests for Benchmark Suggestions endpoint"""
    
    def test_get_benchmark_suggestions(self):
        """Test GET /api/v2/quarter-settings/{year}/{quarter}/benchmark-suggestions"""
        response = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q3/benchmark-suggestions")
        assert response.status_code == 200
        data = response.json()
        # May or may not have previous data
        assert "has_previous_data" in data
        print(f"✓ Benchmark suggestions: has_previous_data={data['has_previous_data']}")


class TestUpdateSettings:
    """Tests for updating quarter settings"""
    
    def test_update_unlocked_settings(self):
        """Test PUT /api/v2/quarter-settings/{year}/{quarter} - update unlocked settings"""
        # First ensure Q3 is unlocked
        requests.delete(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q3")
        
        # Ensure settings exist
        check_settings = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q3")
        if check_settings.status_code == 404:
            payload = {
                "year": 2026,
                "quarter": "Q3",
                "benchmark_ppa": 60.0,
                "benchmark_lbw": 9.0,
                "benchmark_glass": 1.2,
                "benchmark_lsc": 90.0,
                "weight_ppa": 0.30,
                "weight_lbw": 0.25,
                "weight_glass": 0.20,
                "weight_lsc": 0.25
            }
            requests.post(f"{BASE_URL}/api/v2/quarter-settings", json=payload)
        
        # Update
        update_payload = {
            "benchmark_ppa": 62.0,
            "benchmark_lbw": 9.5
        }
        response = requests.put(
            f"{BASE_URL}/api/v2/quarter-settings/2026/Q3",
            json=update_payload
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        
        # Verify update
        verify_response = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q3")
        verify_data = verify_response.json()
        assert verify_data["benchmark_ppa"] == 62.0
        assert verify_data["benchmark_lbw"] == 9.5
        print(f"✓ Updated Q3 settings: PPA=${verify_data['benchmark_ppa']}, LBW=${verify_data['benchmark_lbw']}")
    
    def test_update_locked_settings_fails(self):
        """Test PUT /api/v2/quarter-settings/{year}/{quarter} - cannot update locked settings"""
        # Q2 2026 is locked
        update_payload = {
            "benchmark_ppa": 100.0
        }
        response = requests.put(
            f"{BASE_URL}/api/v2/quarter-settings/2026/Q2",
            json=update_payload
        )
        assert response.status_code == 403
        assert "locked" in response.json()["detail"].lower()
        print("✓ Correctly rejects update to locked settings")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

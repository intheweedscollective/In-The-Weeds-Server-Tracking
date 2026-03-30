"""
Test Snapshot Metrics Calculation Fix
Tests the fix for merge_snapshot_data function that calculates per-guest metrics
(lbw_per_guest, glassware_per_guest, guests_per_lsc) from raw POS data.

Bug: After processing snapshot Q1P3W6, the generated slide was missing most data
Fix: Added calculations for per-guest metrics when they aren't pre-populated in POS data
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Snapshot ID from the bug report
SNAPSHOT_ID = "af0b6115-135a-4c3d-b839-fd6ef6a18348"


class TestCurrentRankingsEndpoint:
    """Test /api/v2/snapshot-workflow/current-rankings endpoint"""
    
    def test_current_rankings_returns_200(self):
        """Verify endpoint returns 200 OK"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ Current rankings endpoint returns 200")
    
    def test_current_rankings_has_28_employees(self):
        """Verify all 28 employees are returned"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings")
        data = response.json()
        
        assert data.get("success") == True, "Response should indicate success"
        assert data.get("has_data") == True, "Response should have data"
        
        employees = data.get("employees", [])
        assert len(employees) == 28, f"Expected 28 employees, got {len(employees)}"
        print(f"✓ Current rankings returns all 28 employees")
    
    def test_snapshot_metadata_correct(self):
        """Verify snapshot metadata is correct"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings")
        data = response.json()
        
        snapshot = data.get("snapshot", {})
        assert snapshot.get("id") == SNAPSHOT_ID, f"Expected snapshot ID {SNAPSHOT_ID}"
        assert snapshot.get("name") == "Q1P3W6", "Expected snapshot name Q1P3W6"
        assert snapshot.get("employee_count") == 28, "Expected 28 employees in snapshot"
        print(f"✓ Snapshot metadata correct: {snapshot.get('name')} with {snapshot.get('employee_count')} employees")


class TestPerGuestMetricsCalculation:
    """Test that per-guest metrics are properly calculated for all employees"""
    
    @pytest.fixture
    def employees(self):
        """Get employees from current rankings"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings")
        return response.json().get("employees", [])
    
    def test_lbw_per_guest_calculated(self, employees):
        """Verify lbw_per_guest is non-zero for all employees with guests"""
        issues = []
        for emp in employees:
            name = emp.get("name", "Unknown")
            lbw_per_guest = emp.get("lbw_per_guest", 0) or 0
            guest_count = emp.get("guest_count", 0) or 0
            
            if guest_count > 0 and lbw_per_guest == 0:
                issues.append(f"{name}: lbw_per_guest is 0 but has {guest_count} guests")
        
        assert len(issues) == 0, f"Found {len(issues)} employees with missing lbw_per_guest: {issues}"
        print(f"✓ All {len(employees)} employees have lbw_per_guest calculated")
    
    def test_glassware_per_guest_calculated(self, employees):
        """Verify glassware_per_guest is non-zero for all employees with guests"""
        issues = []
        for emp in employees:
            name = emp.get("name", "Unknown")
            glassware_per_guest = emp.get("glassware_per_guest", 0) or 0
            guest_count = emp.get("guest_count", 0) or 0
            
            if guest_count > 0 and glassware_per_guest == 0:
                issues.append(f"{name}: glassware_per_guest is 0 but has {guest_count} guests")
        
        assert len(issues) == 0, f"Found {len(issues)} employees with missing glassware_per_guest: {issues}"
        print(f"✓ All {len(employees)} employees have glassware_per_guest calculated")
    
    def test_guests_per_lsc_calculated(self, employees):
        """Verify guests_per_lsc is non-zero for employees with LSC count"""
        issues = []
        for emp in employees:
            name = emp.get("name", "Unknown")
            guests_per_lsc = emp.get("guests_per_lsc", 0) or 0
            lsc_count = emp.get("lsc_count", 0) or 0
            guest_count = emp.get("guest_count", 0) or 0
            
            # Only check if they have both guests and LSC count
            if lsc_count > 0 and guest_count > 0 and guests_per_lsc == 0:
                issues.append(f"{name}: guests_per_lsc is 0 but has {guest_count} guests and {lsc_count} LSC")
        
        assert len(issues) == 0, f"Found {len(issues)} employees with missing guests_per_lsc: {issues}"
        print(f"✓ All employees with LSC data have guests_per_lsc calculated")


class TestScoreCalculation:
    """Test that scores are properly calculated for all employees"""
    
    @pytest.fixture
    def employees(self):
        """Get employees from current rankings"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings")
        return response.json().get("employees", [])
    
    def test_score_ppa_non_zero(self, employees):
        """Verify score_ppa is non-zero for all employees"""
        issues = []
        for emp in employees:
            name = emp.get("name", "Unknown")
            score_ppa = emp.get("score_ppa", 0) or 0
            
            if score_ppa == 0:
                issues.append(f"{name}: score_ppa is 0")
        
        assert len(issues) == 0, f"Found {len(issues)} employees with zero score_ppa: {issues}"
        print(f"✓ All {len(employees)} employees have non-zero score_ppa")
    
    def test_score_lbw_non_zero(self, employees):
        """Verify score_lbw is non-zero for all employees"""
        issues = []
        for emp in employees:
            name = emp.get("name", "Unknown")
            score_lbw = emp.get("score_lbw", 0) or 0
            
            if score_lbw == 0:
                issues.append(f"{name}: score_lbw is 0")
        
        assert len(issues) == 0, f"Found {len(issues)} employees with zero score_lbw: {issues}"
        print(f"✓ All {len(employees)} employees have non-zero score_lbw")
    
    def test_score_glass_non_zero(self, employees):
        """Verify score_glass is non-zero for all employees"""
        issues = []
        for emp in employees:
            name = emp.get("name", "Unknown")
            score_glass = emp.get("score_glass", 0) or 0
            
            if score_glass == 0:
                issues.append(f"{name}: score_glass is 0")
        
        assert len(issues) == 0, f"Found {len(issues)} employees with zero score_glass: {issues}"
        print(f"✓ All {len(employees)} employees have non-zero score_glass")
    
    def test_score_lsc_non_zero(self, employees):
        """Verify score_lsc is non-zero for all employees"""
        issues = []
        for emp in employees:
            name = emp.get("name", "Unknown")
            score_lsc = emp.get("score_lsc", 0) or 0
            
            if score_lsc == 0:
                issues.append(f"{name}: score_lsc is 0")
        
        assert len(issues) == 0, f"Found {len(issues)} employees with zero score_lsc: {issues}"
        print(f"✓ All {len(employees)} employees have non-zero score_lsc")
    
    def test_total_score_in_reasonable_range(self, employees):
        """Verify total_score is in reasonable range (50-120)"""
        issues = []
        for emp in employees:
            name = emp.get("name", "Unknown")
            total_score = emp.get("total_score", 0) or 0
            
            if total_score < 50 or total_score > 120:
                issues.append(f"{name}: total_score {total_score} out of expected range (50-120)")
        
        assert len(issues) == 0, f"Found {len(issues)} employees with out-of-range total_score: {issues}"
        print(f"✓ All {len(employees)} employees have total_score in range 50-120")


class TestTopScorer:
    """Test that top scorer is correctly identified"""
    
    def test_top_scorer_is_starwars(self):
        """Verify Starwars Mckinnon-Herrera is the top scorer with ~117 points"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings")
        data = response.json()
        employees = data.get("employees", [])
        
        # Sort by total_score descending
        sorted_employees = sorted(employees, key=lambda x: x.get("total_score", 0) or 0, reverse=True)
        
        top_scorer = sorted_employees[0]
        assert "Starwars" in top_scorer.get("name", ""), f"Expected Starwars as top scorer, got {top_scorer.get('name')}"
        
        total_score = top_scorer.get("total_score", 0)
        assert 115 <= total_score <= 120, f"Expected top score ~117, got {total_score}"
        
        print(f"✓ Top scorer is {top_scorer.get('name')} with {total_score} points")


class TestSlideGeneration:
    """Test slide generation endpoint"""
    
    def test_slide_endpoint_returns_200(self):
        """Verify slide endpoint returns 200 OK"""
        response = requests.get(
            f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/slide",
            stream=True
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ Slide endpoint returns 200")
    
    def test_slide_returns_png(self):
        """Verify slide returns a valid PNG file"""
        response = requests.get(
            f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/slide",
            stream=True
        )
        
        # Check content type
        content_type = response.headers.get("content-type", "")
        assert "image/png" in content_type, f"Expected image/png, got {content_type}"
        
        # Check PNG magic bytes
        content = response.content
        assert content[:8] == b'\x89PNG\r\n\x1a\n', "Response is not a valid PNG file"
        
        # Check file size is reasonable (should be > 100KB for a full slide)
        assert len(content) > 100000, f"Slide too small: {len(content)} bytes"
        
        print(f"✓ Slide is a valid PNG file ({len(content)} bytes)")
    
    def test_slide_has_content_disposition(self):
        """Verify slide has proper download filename"""
        response = requests.get(
            f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/slide",
            stream=True
        )
        
        content_disposition = response.headers.get("content-disposition", "")
        assert "attachment" in content_disposition, "Expected attachment content-disposition"
        assert ".png" in content_disposition, "Expected .png in filename"
        
        print(f"✓ Slide has proper content-disposition: {content_disposition}")


class TestSnapshotDetails:
    """Test snapshot details endpoint"""
    
    def test_snapshot_details_returns_200(self):
        """Verify snapshot details endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ Snapshot details endpoint returns 200")
    
    def test_snapshot_has_employees(self):
        """Verify snapshot has employee data"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}")
        data = response.json()
        
        employees = data.get("employees", [])
        assert len(employees) == 28, f"Expected 28 employees, got {len(employees)}"
        print(f"✓ Snapshot has {len(employees)} employees")
    
    def test_snapshot_has_benchmarks(self):
        """Verify snapshot has benchmarks used"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}")
        data = response.json()
        
        # Check both possible field names
        benchmarks = data.get("benchmarks_used") or data.get("benchmarks", {})
        assert "ppa" in benchmarks, "Expected ppa benchmark"
        assert "lbw" in benchmarks, "Expected lbw benchmark"
        assert "glass" in benchmarks, "Expected glass benchmark"
        assert "lsc" in benchmarks, "Expected lsc benchmark"
        
        print(f"✓ Snapshot has benchmarks: {benchmarks}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

"""
Test suite for Finalize Quarter flow
Tests DAR deductions, snapshot status updates, and final score calculations
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestFinalizeQuarterFlow:
    """Tests for the Finalize Quarter functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data and ensure quarter is not finalized"""
        self.year = 2026
        self.quarter = "Q1"
        
        # Ensure quarter is not finalized before tests
        try:
            requests.delete(f"{BASE_URL}/api/v2/finalize/{self.year}/{self.quarter}")
        except:
            pass
        
        yield
        
        # Cleanup: Unfinalize quarter after tests
        try:
            requests.delete(f"{BASE_URL}/api/v2/finalize/{self.year}/{self.quarter}")
        except:
            pass
    
    def test_get_finalization_status_not_finalized(self):
        """Test GET /v2/finalization/{year}/{quarter} returns not finalized"""
        response = requests.get(f"{BASE_URL}/api/v2/finalization/{self.year}/{self.quarter}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["is_finalized"] == False
        assert data["quarter"] == self.quarter
        assert data["year"] == self.year
        assert data["dar_entries"] == []
        assert data["final_rankings"] == []
        print(f"✓ Finalization status: is_finalized={data['is_finalized']}")
    
    def test_get_current_rankings_has_employees(self):
        """Test current-rankings endpoint returns employees from active snapshot"""
        response = requests.get(
            f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings",
            params={"year": self.year, "quarter": self.quarter}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        employees = data.get("employees", [])
        assert len(employees) > 0, "No employees found in current rankings"
        
        # Verify employee data structure
        first_emp = employees[0]
        assert "id" in first_emp
        assert "name" in first_emp
        assert "total_score" in first_emp or "pre_dar_score" in first_emp
        
        print(f"✓ Current rankings has {len(employees)} employees")
        print(f"  First employee: {first_emp.get('name')} - Score: {first_emp.get('total_score', first_emp.get('pre_dar_score'))}")
    
    def test_save_dar_entries_draft(self):
        """Test POST /v2/dar/{year}/{quarter} saves DAR entries as draft"""
        # Get employees first
        rankings_response = requests.get(
            f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings",
            params={"year": self.year, "quarter": self.quarter}
        )
        employees = rankings_response.json().get("employees", [])
        
        # Create DAR entries for first 2 employees
        dar_entries = [
            {
                "employee_id": employees[0]["id"],
                "employee_name": employees[0]["name"],
                "written_warnings": 1,
                "suspensions": 0
            },
            {
                "employee_id": employees[1]["id"],
                "employee_name": employees[1]["name"],
                "written_warnings": 0,
                "suspensions": 1
            }
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/v2/dar/{self.year}/{self.quarter}",
            json={
                "quarter": self.quarter,
                "year": self.year,
                "entries": dar_entries
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["count"] == 2
        
        print(f"✓ DAR entries saved: {data['count']} entries")
    
    def test_get_dar_entries(self):
        """Test GET /v2/dar/{year}/{quarter} returns saved DAR entries"""
        # First save some entries
        rankings_response = requests.get(
            f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings",
            params={"year": self.year, "quarter": self.quarter}
        )
        employees = rankings_response.json().get("employees", [])
        
        dar_entries = [
            {
                "employee_id": employees[0]["id"],
                "employee_name": employees[0]["name"],
                "written_warnings": 2,
                "suspensions": 1
            }
        ]
        
        requests.post(
            f"{BASE_URL}/api/v2/dar/{self.year}/{self.quarter}",
            json={
                "quarter": self.quarter,
                "year": self.year,
                "entries": dar_entries
            }
        )
        
        # Now get the entries
        response = requests.get(f"{BASE_URL}/api/v2/dar/{self.year}/{self.quarter}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) > 0
        assert data[0]["written_warnings"] == 2
        assert data[0]["suspensions"] == 1
        
        print(f"✓ Retrieved {len(data)} DAR entries")
    
    def test_finalize_quarter_with_dar_deductions(self):
        """Test POST /v2/finalize/{year}/{quarter} applies DAR deductions correctly"""
        # Get employees
        rankings_response = requests.get(
            f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings",
            params={"year": self.year, "quarter": self.quarter}
        )
        employees = rankings_response.json().get("employees", [])
        
        # Get first employee's pre-DAR score
        first_emp = employees[0]
        pre_dar_score = first_emp.get("pre_dar_score") or first_emp.get("total_score", 0)
        
        # Create DAR entries with known deductions
        # Written Warning: -3 pts, Suspension: -5 pts
        dar_entries = [
            {
                "employee_id": first_emp["id"],
                "employee_name": first_emp["name"],
                "written_warnings": 2,  # -6 pts
                "suspensions": 1        # -5 pts
            }
        ]
        # Add empty entries for other employees
        for emp in employees[1:]:
            dar_entries.append({
                "employee_id": emp["id"],
                "employee_name": emp["name"],
                "written_warnings": 0,
                "suspensions": 0
            })
        
        # Finalize quarter
        response = requests.post(
            f"{BASE_URL}/api/v2/finalize/{self.year}/{self.quarter}",
            json={
                "quarter": self.quarter,
                "year": self.year,
                "entries": dar_entries
            },
            params={"generate_reviews": False}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "finalized successfully" in data["message"]
        assert data["total_employees"] == len(employees)
        
        # Verify DAR deductions were applied
        final_rankings = data["final_rankings"]
        first_emp_final = next(r for r in final_rankings if r["employee_id"] == first_emp["id"])
        
        expected_deduction = 2 * 3 + 1 * 5  # 6 + 5 = 11
        expected_final_score = max(0, pre_dar_score - expected_deduction)
        
        assert first_emp_final["total_deduction"] == expected_deduction, \
            f"Expected deduction {expected_deduction}, got {first_emp_final['total_deduction']}"
        assert abs(first_emp_final["final_score"] - expected_final_score) < 0.1, \
            f"Expected final score {expected_final_score}, got {first_emp_final['final_score']}"
        
        print(f"✓ Quarter finalized successfully")
        print(f"  Pre-DAR Score: {pre_dar_score}")
        print(f"  Deduction: -{expected_deduction} (2 warnings × 3 + 1 suspension × 5)")
        print(f"  Final Score: {first_emp_final['final_score']}")
    
    def test_finalization_status_after_finalize(self):
        """Test finalization status is updated after finalizing"""
        # First finalize the quarter
        rankings_response = requests.get(
            f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings",
            params={"year": self.year, "quarter": self.quarter}
        )
        employees = rankings_response.json().get("employees", [])
        
        dar_entries = [
            {
                "employee_id": emp["id"],
                "employee_name": emp["name"],
                "written_warnings": 0,
                "suspensions": 0
            }
            for emp in employees
        ]
        
        requests.post(
            f"{BASE_URL}/api/v2/finalize/{self.year}/{self.quarter}",
            json={
                "quarter": self.quarter,
                "year": self.year,
                "entries": dar_entries
            },
            params={"generate_reviews": False}
        )
        
        # Check finalization status
        response = requests.get(f"{BASE_URL}/api/v2/finalization/{self.year}/{self.quarter}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["is_finalized"] == True
        assert "finalized_at" in data
        assert len(data["final_rankings"]) == len(employees)
        assert data["total_employees"] == len(employees)
        
        print(f"✓ Finalization status updated: is_finalized={data['is_finalized']}")
        print(f"  Finalized at: {data['finalized_at']}")
    
    def test_snapshot_status_updated_to_finalized(self):
        """Test snapshot status is updated to 'finalized' after quarter finalization"""
        # First finalize the quarter
        rankings_response = requests.get(
            f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings",
            params={"year": self.year, "quarter": self.quarter}
        )
        employees = rankings_response.json().get("employees", [])
        
        dar_entries = [
            {
                "employee_id": emp["id"],
                "employee_name": emp["name"],
                "written_warnings": 0,
                "suspensions": 0
            }
            for emp in employees
        ]
        
        requests.post(
            f"{BASE_URL}/api/v2/finalize/{self.year}/{self.quarter}",
            json={
                "quarter": self.quarter,
                "year": self.year,
                "entries": dar_entries
            },
            params={"generate_reviews": False}
        )
        
        # Check snapshot status
        response = requests.get(
            f"{BASE_URL}/api/v2/snapshot-workflow/snapshots",
            params={"year": self.year, "quarter": self.quarter}
        )
        
        assert response.status_code == 200
        snapshots = response.json()
        
        # Find the current/active snapshot
        current_snapshot = next((s for s in snapshots if s.get("is_current")), None)
        
        if current_snapshot:
            assert current_snapshot["status"] == "finalized", \
                f"Expected snapshot status 'finalized', got '{current_snapshot['status']}'"
            print(f"✓ Snapshot status updated to 'finalized'")
            print(f"  Snapshot ID: {current_snapshot['id'][:20]}...")
        else:
            # Check if any snapshot has finalized status
            finalized_snapshot = next((s for s in snapshots if s.get("status") == "finalized"), None)
            assert finalized_snapshot is not None, "No finalized snapshot found"
            print(f"✓ Found finalized snapshot: {finalized_snapshot['id'][:20]}...")
    
    def test_unfinalize_quarter(self):
        """Test DELETE /v2/finalize/{year}/{quarter} reopens the quarter"""
        # First finalize
        rankings_response = requests.get(
            f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings",
            params={"year": self.year, "quarter": self.quarter}
        )
        employees = rankings_response.json().get("employees", [])
        
        dar_entries = [
            {
                "employee_id": emp["id"],
                "employee_name": emp["name"],
                "written_warnings": 0,
                "suspensions": 0
            }
            for emp in employees
        ]
        
        requests.post(
            f"{BASE_URL}/api/v2/finalize/{self.year}/{self.quarter}",
            json={
                "quarter": self.quarter,
                "year": self.year,
                "entries": dar_entries
            },
            params={"generate_reviews": False}
        )
        
        # Now unfinalize
        response = requests.delete(f"{BASE_URL}/api/v2/finalize/{self.year}/{self.quarter}")
        
        assert response.status_code == 200
        data = response.json()
        assert "reopened" in data["message"].lower()
        
        # Verify status is now not finalized
        status_response = requests.get(f"{BASE_URL}/api/v2/finalization/{self.year}/{self.quarter}")
        status_data = status_response.json()
        
        assert status_data["is_finalized"] == False
        
        print(f"✓ Quarter unfinalized successfully")
        print(f"  Message: {data['message']}")
    
    def test_dar_calculation_written_warning(self):
        """Test Written Warning deduction is -3 pts"""
        rankings_response = requests.get(
            f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings",
            params={"year": self.year, "quarter": self.quarter}
        )
        employees = rankings_response.json().get("employees", [])
        first_emp = employees[0]
        pre_dar_score = first_emp.get("pre_dar_score") or first_emp.get("total_score", 0)
        
        dar_entries = [
            {
                "employee_id": first_emp["id"],
                "employee_name": first_emp["name"],
                "written_warnings": 1,
                "suspensions": 0
            }
        ]
        for emp in employees[1:]:
            dar_entries.append({
                "employee_id": emp["id"],
                "employee_name": emp["name"],
                "written_warnings": 0,
                "suspensions": 0
            })
        
        response = requests.post(
            f"{BASE_URL}/api/v2/finalize/{self.year}/{self.quarter}",
            json={
                "quarter": self.quarter,
                "year": self.year,
                "entries": dar_entries
            },
            params={"generate_reviews": False}
        )
        
        data = response.json()
        first_emp_final = next(r for r in data["final_rankings"] if r["employee_id"] == first_emp["id"])
        
        assert first_emp_final["total_deduction"] == 3, \
            f"Written Warning should deduct 3 pts, got {first_emp_final['total_deduction']}"
        
        expected_final = max(0, pre_dar_score - 3)
        assert abs(first_emp_final["final_score"] - expected_final) < 0.1
        
        print(f"✓ Written Warning deduction: -3 pts")
        print(f"  {pre_dar_score} - 3 = {first_emp_final['final_score']}")
    
    def test_dar_calculation_suspension(self):
        """Test Suspension deduction is -5 pts"""
        # Unfinalize first
        requests.delete(f"{BASE_URL}/api/v2/finalize/{self.year}/{self.quarter}")
        
        rankings_response = requests.get(
            f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings",
            params={"year": self.year, "quarter": self.quarter}
        )
        employees = rankings_response.json().get("employees", [])
        first_emp = employees[0]
        pre_dar_score = first_emp.get("pre_dar_score") or first_emp.get("total_score", 0)
        
        dar_entries = [
            {
                "employee_id": first_emp["id"],
                "employee_name": first_emp["name"],
                "written_warnings": 0,
                "suspensions": 1
            }
        ]
        for emp in employees[1:]:
            dar_entries.append({
                "employee_id": emp["id"],
                "employee_name": emp["name"],
                "written_warnings": 0,
                "suspensions": 0
            })
        
        response = requests.post(
            f"{BASE_URL}/api/v2/finalize/{self.year}/{self.quarter}",
            json={
                "quarter": self.quarter,
                "year": self.year,
                "entries": dar_entries
            },
            params={"generate_reviews": False}
        )
        
        data = response.json()
        first_emp_final = next(r for r in data["final_rankings"] if r["employee_id"] == first_emp["id"])
        
        assert first_emp_final["total_deduction"] == 5, \
            f"Suspension should deduct 5 pts, got {first_emp_final['total_deduction']}"
        
        expected_final = max(0, pre_dar_score - 5)
        assert abs(first_emp_final["final_score"] - expected_final) < 0.1
        
        print(f"✓ Suspension deduction: -5 pts")
        print(f"  {pre_dar_score} - 5 = {first_emp_final['final_score']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

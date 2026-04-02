"""
Test Finalize Quarter Workflow
Tests the complete finalization workflow including:
- GET /api/v2/snapshot-workflow/snapshots/{snapshot_id}/workflow-status
- POST /api/v2/snapshot-workflow/snapshots/{snapshot_id}/finalize
- POST /api/v2/snapshot-workflow/snapshots/{snapshot_id}/reopen
- GET /api/v2/quarter-settings/{year}/{quarter}
- GET /api/v2/finalization/{year}/{quarter}
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Known snapshot ID for Q1 2026 (from agent context)
SNAPSHOT_ID = "7cd70c38-10ce-4b42-8db3-4a02f878e21f"
YEAR = 2026
QUARTER = "Q1"


class TestWorkflowStatus:
    """Test workflow status endpoint"""
    
    def test_get_workflow_status(self):
        """GET /api/v2/snapshot-workflow/snapshots/{snapshot_id}/workflow-status returns correct status"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/workflow-status")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "status" in data, "Response should contain 'status'"
        assert "is_finalized" in data, "Response should contain 'is_finalized'"
        assert "actions" in data, "Response should contain 'actions'"
        assert "employee_count" in data, "Response should contain 'employee_count'"
        
        # Verify actions structure
        actions = data.get("actions", {})
        assert "can_finalize" in actions, "Actions should contain 'can_finalize'"
        assert "can_reopen" in actions, "Actions should contain 'can_reopen'"
        
        print(f"Workflow status: {data['status']}, is_finalized: {data['is_finalized']}")
        print(f"Employee count: {data['employee_count']}")
        print(f"Actions: {actions}")
    
    def test_workflow_status_not_found(self):
        """GET /api/v2/snapshot-workflow/snapshots/{invalid_id}/workflow-status returns 404"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/invalid-snapshot-id/workflow-status")
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestQuarterSettings:
    """Test quarter settings endpoint"""
    
    def test_get_quarter_settings(self):
        """GET /api/v2/quarter-settings/{year}/{quarter} returns benchmarks"""
        response = requests.get(f"{BASE_URL}/api/v2/quarter-settings/{YEAR}/{QUARTER}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "benchmark_ppa" in data, "Response should contain 'benchmark_ppa'"
        assert "benchmark_lbw" in data, "Response should contain 'benchmark_lbw'"
        assert "a_server_min_score" in data, "Response should contain 'a_server_min_score'"
        assert "b_server_min_score" in data, "Response should contain 'b_server_min_score'"
        
        print(f"Quarter settings for {QUARTER} {YEAR}:")
        print(f"  PPA Benchmark: {data.get('benchmark_ppa')}")
        print(f"  LBW Benchmark: {data.get('benchmark_lbw')}")
        print(f"  A-Server Min: {data.get('a_server_min_score')}")
        print(f"  B-Server Min: {data.get('b_server_min_score')}")


class TestFinalization:
    """Test finalization endpoint"""
    
    def test_get_finalization_status(self):
        """GET /api/v2/finalization/{year}/{quarter} returns finalization status"""
        response = requests.get(f"{BASE_URL}/api/v2/finalization/{YEAR}/{QUARTER}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "quarter" in data, "Response should contain 'quarter'"
        assert "year" in data, "Response should contain 'year'"
        assert "is_finalized" in data, "Response should contain 'is_finalized'"
        
        print(f"Finalization status for {QUARTER} {YEAR}: is_finalized={data.get('is_finalized')}")


class TestFinalizeAndReopen:
    """Test finalize and reopen workflow"""
    
    def test_finalize_snapshot(self):
        """POST /api/v2/snapshot-workflow/snapshots/{snapshot_id}/finalize should finalize with DAR entries"""
        # First check current status
        status_response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/workflow-status")
        assert status_response.status_code == 200
        
        current_status = status_response.json()
        print(f"Current status before finalize: {current_status['status']}")
        
        # If already finalized, reopen first
        if current_status.get("is_finalized"):
            print("Snapshot is already finalized, reopening first...")
            reopen_response = requests.post(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/reopen")
            assert reopen_response.status_code == 200, f"Failed to reopen: {reopen_response.text}"
            print("Reopened successfully")
        
        # Get employees to build DAR entries
        rankings_response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?year={YEAR}&quarter={QUARTER}")
        assert rankings_response.status_code == 200
        
        employees = rankings_response.json().get("employees", [])
        assert len(employees) > 0, "Should have employees to finalize"
        
        # Build DAR entries (add some test DAR values)
        dar_entries = []
        for i, emp in enumerate(employees[:3]):  # Add DAR to first 3 employees for testing
            dar_entries.append({
                "employee_id": emp.get("id"),
                "written_warnings": 1 if i == 0 else 0,  # First employee gets 1 written warning
                "suspensions": 1 if i == 1 else 0  # Second employee gets 1 suspension
            })
        
        # Add remaining employees with no DAR
        for emp in employees[3:]:
            dar_entries.append({
                "employee_id": emp.get("id"),
                "written_warnings": 0,
                "suspensions": 0
            })
        
        # Finalize
        finalize_response = requests.post(
            f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/finalize",
            json={"dar_entries": dar_entries}
        )
        
        assert finalize_response.status_code == 200, f"Expected 200, got {finalize_response.status_code}: {finalize_response.text}"
        
        data = finalize_response.json()
        assert data.get("success") == True, "Finalize should return success=True"
        assert data.get("status") == "finalized", "Status should be 'finalized'"
        
        # Verify summary
        summary = data.get("summary", {})
        assert "total_employees" in summary, "Summary should contain 'total_employees'"
        assert "employees_with_dar" in summary, "Summary should contain 'employees_with_dar'"
        assert "total_dar_deductions" in summary, "Summary should contain 'total_dar_deductions'"
        
        print(f"Finalization successful:")
        print(f"  Total employees: {summary.get('total_employees')}")
        print(f"  Employees with DAR: {summary.get('employees_with_dar')}")
        print(f"  Total DAR deductions: {summary.get('total_dar_deductions')}")
        
        # Verify status changed to finalized
        status_response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/workflow-status")
        assert status_response.status_code == 200
        
        new_status = status_response.json()
        assert new_status.get("status") == "finalized", f"Status should be 'finalized', got {new_status.get('status')}"
        assert new_status.get("is_finalized") == True, "is_finalized should be True"
        
        print(f"Verified: Snapshot status is now 'finalized'")
    
    def test_reopen_snapshot(self):
        """POST /api/v2/snapshot-workflow/snapshots/{snapshot_id}/reopen should reopen finalized snapshot"""
        # First ensure it's finalized
        status_response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/workflow-status")
        assert status_response.status_code == 200
        
        current_status = status_response.json()
        
        if not current_status.get("is_finalized"):
            print("Snapshot is not finalized, finalizing first...")
            # Quick finalize with empty DAR
            rankings_response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?year={YEAR}&quarter={QUARTER}")
            employees = rankings_response.json().get("employees", [])
            dar_entries = [{"employee_id": emp.get("id"), "written_warnings": 0, "suspensions": 0} for emp in employees]
            
            finalize_response = requests.post(
                f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/finalize",
                json={"dar_entries": dar_entries}
            )
            assert finalize_response.status_code == 200
        
        # Now reopen
        reopen_response = requests.post(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/reopen")
        
        assert reopen_response.status_code == 200, f"Expected 200, got {reopen_response.status_code}: {reopen_response.text}"
        
        data = reopen_response.json()
        assert data.get("success") == True, "Reopen should return success=True"
        assert data.get("status") == "reviewed", "Status should be 'reviewed'"
        
        print(f"Reopen successful: status={data.get('status')}")
        
        # Verify status changed back to reviewed
        status_response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/workflow-status")
        assert status_response.status_code == 200
        
        new_status = status_response.json()
        assert new_status.get("status") == "reviewed", f"Status should be 'reviewed', got {new_status.get('status')}"
        assert new_status.get("is_finalized") == False, "is_finalized should be False"
        
        print(f"Verified: Snapshot status is now 'reviewed'")
    
    def test_reopen_non_finalized_fails(self):
        """POST /api/v2/snapshot-workflow/snapshots/{snapshot_id}/reopen should fail if not finalized"""
        # First ensure it's not finalized
        status_response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/workflow-status")
        current_status = status_response.json()
        
        if current_status.get("is_finalized"):
            # Reopen first
            requests.post(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/reopen")
        
        # Try to reopen again (should fail)
        reopen_response = requests.post(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/reopen")
        
        assert reopen_response.status_code == 400, f"Expected 400, got {reopen_response.status_code}"
        print("Correctly rejected reopen of non-finalized snapshot")


class TestDARDeductions:
    """Test DAR deduction calculations"""
    
    def test_dar_deduction_calculation(self):
        """Verify DAR deductions are calculated correctly: Written Warning = -3, Suspension = -5"""
        # Get current rankings
        rankings_response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?year={YEAR}&quarter={QUARTER}")
        assert rankings_response.status_code == 200
        
        employees = rankings_response.json().get("employees", [])
        assert len(employees) > 0
        
        # Get first employee's pre-DAR score
        test_employee = employees[0]
        pre_dar_score = test_employee.get("total_score", 0)
        
        print(f"Test employee: {test_employee.get('name')}, pre-DAR score: {pre_dar_score}")
        
        # Ensure snapshot is not finalized
        status_response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/workflow-status")
        if status_response.json().get("is_finalized"):
            requests.post(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/reopen")
        
        # Finalize with specific DAR values
        dar_entries = []
        for emp in employees:
            if emp.get("id") == test_employee.get("id"):
                # Give test employee 2 written warnings and 1 suspension
                dar_entries.append({
                    "employee_id": emp.get("id"),
                    "written_warnings": 2,  # -6 points
                    "suspensions": 1  # -5 points
                })
            else:
                dar_entries.append({
                    "employee_id": emp.get("id"),
                    "written_warnings": 0,
                    "suspensions": 0
                })
        
        finalize_response = requests.post(
            f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/finalize",
            json={"dar_entries": dar_entries}
        )
        assert finalize_response.status_code == 200
        
        # Get updated rankings
        rankings_response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?year={YEAR}&quarter={QUARTER}")
        updated_employees = rankings_response.json().get("employees", [])
        
        # Find test employee
        updated_test_emp = next((e for e in updated_employees if e.get("id") == test_employee.get("id")), None)
        assert updated_test_emp is not None
        
        # Verify deductions
        expected_deduction = (2 * 3) + (1 * 5)  # 6 + 5 = 11
        expected_final_score = max(0, pre_dar_score - expected_deduction)
        
        actual_final_score = updated_test_emp.get("final_score") or updated_test_emp.get("total_score")
        
        print(f"Pre-DAR score: {pre_dar_score}")
        print(f"Expected deduction: {expected_deduction} (2 written warnings * 3 + 1 suspension * 5)")
        print(f"Expected final score: {expected_final_score}")
        print(f"Actual final score: {actual_final_score}")
        
        # Allow small floating point differences
        assert abs(actual_final_score - expected_final_score) < 0.1, \
            f"Final score mismatch: expected {expected_final_score}, got {actual_final_score}"
        
        print("DAR deduction calculation verified correctly!")
        
        # Cleanup: reopen the snapshot
        requests.post(f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{SNAPSHOT_ID}/reopen")


class TestCurrentRankings:
    """Test current rankings endpoint"""
    
    def test_get_current_rankings(self):
        """GET /api/v2/snapshot-workflow/current-rankings returns employees from active snapshot"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?year={YEAR}&quarter={QUARTER}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "employees" in data, "Response should contain 'employees'"
        assert "snapshot" in data, "Response should contain 'snapshot'"
        
        employees = data.get("employees", [])
        assert len(employees) > 0, "Should have employees"
        
        # Verify employee structure
        first_emp = employees[0]
        assert "id" in first_emp, "Employee should have 'id'"
        assert "name" in first_emp, "Employee should have 'name'"
        assert "total_score" in first_emp, "Employee should have 'total_score'"
        
        print(f"Current rankings: {len(employees)} employees")
        print(f"Top 3 employees:")
        for emp in employees[:3]:
            print(f"  {emp.get('name')}: {emp.get('total_score')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

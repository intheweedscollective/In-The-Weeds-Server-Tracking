"""
Test Employee Metric Edit and Score Recalculation
Tests the bug fixes for:
1. Employee metric edit updates score correctly (via PUT /v2/snapshot-workflow/employees/{id})
2. POS Review modal confirm-pos-review updates scores correctly
3. current-rankings endpoint returns data from the active snapshot (is_current=True)
4. Verify scores recalculate when PPA is changed
"""

import pytest
import requests
import os
import json

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestCurrentRankingsEndpoint:
    """Test that current-rankings returns data from is_current=True snapshot"""
    
    def test_current_rankings_returns_data(self):
        """Verify current-rankings endpoint returns employee data"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q1")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("has_data") == True, "Expected has_data to be True"
        assert "employees" in data, "Expected employees in response"
        assert len(data["employees"]) > 0, "Expected at least one employee"
        
        print(f"✓ current-rankings returns {len(data['employees'])} employees")
    
    def test_current_rankings_returns_active_snapshot(self):
        """Verify current-rankings returns data from is_current=True snapshot"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q1")
        assert response.status_code == 200
        
        data = response.json()
        snapshot = data.get("snapshot", {})
        
        # Verify snapshot ID matches the expected active snapshot
        expected_snapshot_id = "af0b6115-135a-4c3d-b839-fd6ef6a18348"
        assert snapshot.get("id") == expected_snapshot_id, f"Expected snapshot {expected_snapshot_id}, got {snapshot.get('id')}"
        
        print(f"✓ current-rankings returns active snapshot: {snapshot.get('id')}")
    
    def test_current_rankings_employees_have_scores(self):
        """Verify all employees have calculated scores"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q1")
        assert response.status_code == 200
        
        data = response.json()
        employees = data.get("employees", [])
        
        for emp in employees:
            name = emp.get("name", "Unknown")
            total_score = emp.get("total_score")
            
            # Verify score exists and is reasonable
            assert total_score is not None, f"Employee {name} has no total_score"
            assert isinstance(total_score, (int, float)), f"Employee {name} total_score is not a number"
            assert total_score >= 0, f"Employee {name} has negative score: {total_score}"
        
        print(f"✓ All {len(employees)} employees have valid scores")


class TestEmployeeMetricEdit:
    """Test PUT /v2/snapshot-workflow/employees/{id} updates scores correctly"""
    
    def test_get_employee_for_edit(self):
        """Get an employee to test editing"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q1")
        assert response.status_code == 200
        
        data = response.json()
        employees = data.get("employees", [])
        assert len(employees) > 0, "No employees found"
        
        # Get first employee
        emp = employees[0]
        print(f"✓ Found employee for testing: {emp.get('name')} (PPA: {emp.get('ppa')}, Score: {emp.get('total_score')})")
        return emp
    
    def test_update_employee_ppa_recalculates_score(self):
        """Test that updating PPA recalculates the total_score"""
        # First get current employee data
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q1")
        assert response.status_code == 200
        
        data = response.json()
        employees = data.get("employees", [])
        assert len(employees) > 0, "No employees found"
        
        # Find an employee with PPA below benchmark (55.0) where changes will affect score
        # When PPA is already above benchmark, score is maxed out and won't change
        test_emp = None
        for emp in employees:
            ppa = emp.get("ppa", 0) or 0
            if 0 < ppa < 55:  # Below benchmark - changes will affect score
                test_emp = emp
                break
        
        if test_emp is None:
            # Fallback: find any employee with PPA
            for emp in employees:
                if emp.get("ppa") and emp.get("ppa") > 0:
                    test_emp = emp
                    break
        
        assert test_emp is not None, "No employee with PPA found"
        
        emp_id = test_emp.get("id") or test_emp.get("name")
        original_ppa = test_emp.get("ppa")
        original_score = test_emp.get("total_score")
        original_score_ppa = test_emp.get("score_ppa")
        
        print(f"Testing with employee: {test_emp.get('name')}")
        print(f"  Original PPA: {original_ppa}")
        print(f"  Original score_ppa: {original_score_ppa}")
        print(f"  Original total_score: {original_score}")
        
        # Update PPA to benchmark value (55.0) - this should change score if original was below
        new_ppa = 55.0
        
        update_response = requests.put(
            f"{BASE_URL}/api/v2/snapshot-workflow/employees/{emp_id}",
            json={"ppa": new_ppa}
        )
        
        assert update_response.status_code == 200, f"Update failed: {update_response.status_code} - {update_response.text}"
        
        update_data = update_response.json()
        assert update_data.get("success") == True, f"Update not successful: {update_data}"
        
        # Verify the returned employee has updated score
        updated_emp = update_data.get("employee", {})
        new_score = updated_emp.get("total_score")
        new_score_ppa = updated_emp.get("score_ppa")
        
        print(f"  New PPA: {updated_emp.get('ppa')}")
        print(f"  New score_ppa: {new_score_ppa}")
        print(f"  New total_score: {new_score}")
        
        # PPA should be updated
        assert updated_emp.get("ppa") == new_ppa, f"PPA not updated: expected {new_ppa}, got {updated_emp.get('ppa')}"
        
        # score_ppa should be 100 (since PPA = benchmark)
        assert new_score_ppa == 100.0, f"score_ppa should be 100 when PPA equals benchmark, got {new_score_ppa}"
        
        # If original PPA was below benchmark, score should have increased
        if original_ppa < 55:
            assert new_score > original_score, f"Score should have increased: {original_score} -> {new_score}"
            print(f"✓ Score increased from {original_score} to {new_score}")
        
        # Verify by fetching current-rankings again
        verify_response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q1")
        assert verify_response.status_code == 200
        
        verify_data = verify_response.json()
        verify_employees = verify_data.get("employees", [])
        
        # Find the updated employee
        verified_emp = None
        for emp in verify_employees:
            if emp.get("id") == emp_id or emp.get("name") == test_emp.get("name"):
                verified_emp = emp
                break
        
        assert verified_emp is not None, "Could not find updated employee in current-rankings"
        assert verified_emp.get("ppa") == new_ppa, f"PPA not persisted: expected {new_ppa}, got {verified_emp.get('ppa')}"
        
        print(f"✓ PPA update persisted and score recalculated")
        
        # Restore original PPA
        restore_response = requests.put(
            f"{BASE_URL}/api/v2/snapshot-workflow/employees/{emp_id}",
            json={"ppa": original_ppa}
        )
        assert restore_response.status_code == 200, "Failed to restore original PPA"
        print(f"✓ Restored original PPA: {original_ppa}")
    
    def test_update_employee_lbw_recalculates_derived_values(self):
        """Test that updating LBW components recalculates lbw_per_guest"""
        # Get current employee data
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q1")
        assert response.status_code == 200
        
        data = response.json()
        employees = data.get("employees", [])
        
        # Find an employee with guest_count
        test_emp = None
        for emp in employees:
            if emp.get("guest_count") and emp.get("guest_count") > 0:
                test_emp = emp
                break
        
        if test_emp is None:
            pytest.skip("No employee with guest_count found")
        
        emp_id = test_emp.get("id") or test_emp.get("name")
        original_liquor = test_emp.get("liquor_sales", 0)
        original_lbw_per_guest = test_emp.get("lbw_per_guest", 0)
        
        print(f"Testing LBW update with: {test_emp.get('name')}")
        print(f"  Original liquor_sales: {original_liquor}")
        print(f"  Original lbw_per_guest: {original_lbw_per_guest}")
        
        # Update liquor_sales
        new_liquor = original_liquor + 100.0
        
        update_response = requests.put(
            f"{BASE_URL}/api/v2/snapshot-workflow/employees/{emp_id}",
            json={"liquor_sales": new_liquor}
        )
        
        assert update_response.status_code == 200, f"Update failed: {update_response.status_code}"
        
        update_data = update_response.json()
        updated_emp = update_data.get("employee", {})
        
        new_lbw_per_guest = updated_emp.get("lbw_per_guest")
        
        print(f"  New liquor_sales: {updated_emp.get('liquor_sales')}")
        print(f"  New lbw_per_guest: {new_lbw_per_guest}")
        
        # lbw_per_guest should have increased
        assert new_lbw_per_guest > original_lbw_per_guest, f"lbw_per_guest did not increase after liquor_sales update"
        
        print(f"✓ LBW update recalculated lbw_per_guest correctly")
        
        # Restore original value
        restore_response = requests.put(
            f"{BASE_URL}/api/v2/snapshot-workflow/employees/{emp_id}",
            json={"liquor_sales": original_liquor}
        )
        assert restore_response.status_code == 200
        print(f"✓ Restored original liquor_sales")


class TestConfirmPosReview:
    """Test POST /v2/snapshot-workflow/snapshots/{id}/confirm-pos-review updates scores"""
    
    def test_confirm_pos_review_updates_scores(self):
        """Test that confirm-pos-review recalculates scores after PPA edit"""
        # Get current snapshot ID
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q1")
        assert response.status_code == 200
        
        data = response.json()
        snapshot_id = data.get("snapshot", {}).get("id")
        employees = data.get("employees", [])
        
        assert snapshot_id, "No snapshot ID found"
        assert len(employees) > 0, "No employees found"
        
        # Find an employee with PPA below benchmark (55.0) where changes will affect score
        test_emp = None
        for emp in employees:
            ppa = emp.get("ppa", 0) or 0
            if 0 < ppa < 55:  # Below benchmark - changes will affect score
                test_emp = emp
                break
        
        if test_emp is None:
            test_emp = employees[0]  # Fallback
        
        original_ppa = test_emp.get("ppa", 50)
        original_score = test_emp.get("total_score")
        
        print(f"Testing confirm-pos-review with snapshot: {snapshot_id}")
        print(f"  Employee: {test_emp.get('name')}")
        print(f"  Original PPA: {original_ppa}")
        print(f"  Original Score: {original_score}")
        
        # Create modified employee data with new PPA (set to benchmark)
        modified_ppa = 55.0  # Set to benchmark for predictable score change
        modified_employees = [{
            "name": test_emp.get("name"),
            "ppa": modified_ppa,
            "guest_count": test_emp.get("guest_count"),
            "net_sales": test_emp.get("net_sales"),
            "liquor_sales": test_emp.get("liquor_sales"),
            "beer_sales": test_emp.get("beer_sales"),
            "wine_sales": test_emp.get("wine_sales"),
            "lbw_total": test_emp.get("lbw"),
            "glassware_sales": test_emp.get("bar_glassware_sales") or test_emp.get("glassware_sales"),
            "loyalty_sales": test_emp.get("loyalty_sales"),
            "lsc_count": test_emp.get("lsc_count"),
        }]
        
        # Call confirm-pos-review
        confirm_response = requests.post(
            f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{snapshot_id}/confirm-pos-review",
            json={"employees": modified_employees}
        )
        
        assert confirm_response.status_code == 200, f"confirm-pos-review failed: {confirm_response.status_code} - {confirm_response.text}"
        
        confirm_data = confirm_response.json()
        assert confirm_data.get("success") == True, f"confirm-pos-review not successful: {confirm_data}"
        
        print(f"  confirm-pos-review response: {confirm_data.get('message')}")
        
        # Verify the score was recalculated by fetching current-rankings
        verify_response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q1")
        assert verify_response.status_code == 200
        
        verify_data = verify_response.json()
        verify_employees = verify_data.get("employees", [])
        
        # Find the updated employee
        verified_emp = None
        for emp in verify_employees:
            if emp.get("name") == test_emp.get("name"):
                verified_emp = emp
                break
        
        assert verified_emp is not None, "Could not find employee after confirm-pos-review"
        
        new_ppa = verified_emp.get("ppa")
        new_score = verified_emp.get("total_score")
        new_score_ppa = verified_emp.get("score_ppa")
        
        print(f"  After confirm-pos-review:")
        print(f"    New PPA: {new_ppa}")
        print(f"    New score_ppa: {new_score_ppa}")
        print(f"    New Score: {new_score}")
        
        # Verify PPA was updated
        assert new_ppa == modified_ppa, f"PPA not updated: expected {modified_ppa}, got {new_ppa}"
        
        # Verify score_ppa is 100 (since PPA = benchmark)
        assert new_score_ppa == 100.0, f"score_ppa should be 100 when PPA equals benchmark, got {new_score_ppa}"
        
        # If original PPA was below benchmark, score should have increased
        if original_ppa < 55:
            assert new_score > original_score, f"Score should have increased: {original_score} -> {new_score}"
            print(f"✓ Score increased from {original_score} to {new_score}")
        
        print(f"✓ confirm-pos-review correctly updated PPA and recalculated score")
        
        # Restore original PPA
        restore_employees = [{
            "name": test_emp.get("name"),
            "ppa": original_ppa,
            "guest_count": test_emp.get("guest_count"),
            "net_sales": test_emp.get("net_sales"),
            "liquor_sales": test_emp.get("liquor_sales"),
            "beer_sales": test_emp.get("beer_sales"),
            "wine_sales": test_emp.get("wine_sales"),
            "lbw_total": test_emp.get("lbw"),
            "glassware_sales": test_emp.get("bar_glassware_sales") or test_emp.get("glassware_sales"),
            "loyalty_sales": test_emp.get("loyalty_sales"),
            "lsc_count": test_emp.get("lsc_count"),
        }]
        
        restore_response = requests.post(
            f"{BASE_URL}/api/v2/snapshot-workflow/snapshots/{snapshot_id}/confirm-pos-review",
            json={"employees": restore_employees}
        )
        assert restore_response.status_code == 200
        print(f"✓ Restored original PPA via confirm-pos-review")


class TestScoreRecalculationFormula:
    """Test that score recalculation follows the correct formula"""
    
    def test_score_formula_verification(self):
        """Verify the scoring formula is applied correctly"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?year=2026&quarter=Q1")
        assert response.status_code == 200
        
        data = response.json()
        employees = data.get("employees", [])
        benchmarks = data.get("benchmarks", {})
        
        # Default benchmarks if not provided
        benchmark_ppa = benchmarks.get("ppa", 55.0)
        benchmark_lbw = benchmarks.get("lbw", 8.0)
        benchmark_glass = benchmarks.get("glass", 1.25)
        benchmark_lsc = benchmarks.get("lsc", 100.0)
        
        print(f"Benchmarks: PPA={benchmark_ppa}, LBW={benchmark_lbw}, Glass={benchmark_glass}, LSC={benchmark_lsc}")
        
        # Verify formula for first few employees
        for emp in employees[:3]:
            name = emp.get("name")
            ppa = emp.get("ppa", 0) or 0
            lbw_per_guest = emp.get("lbw_per_guest", 0) or 0
            glassware_per_guest = emp.get("glassware_per_guest", 0) or 0
            guests_per_lsc = emp.get("guests_per_lsc", 0) or 0
            
            # Calculate expected scores
            expected_score_ppa = (ppa / benchmark_ppa) * 100 if benchmark_ppa > 0 else 0
            expected_score_lbw = (lbw_per_guest / benchmark_lbw) * 100 if benchmark_lbw > 0 else 0
            expected_score_glass = (glassware_per_guest / benchmark_glass) * 100 if benchmark_glass > 0 else 0
            expected_score_lsc = (benchmark_lsc / guests_per_lsc) * 100 if guests_per_lsc > 0 else 0
            
            actual_score_ppa = emp.get("score_ppa", 0)
            actual_score_lbw = emp.get("score_lbw", 0)
            actual_score_glass = emp.get("score_glass", 0)
            actual_score_lsc = emp.get("score_lsc", 0)
            
            print(f"\n{name}:")
            print(f"  PPA: {ppa} -> score_ppa: {actual_score_ppa} (expected: {expected_score_ppa:.2f})")
            print(f"  LBW/G: {lbw_per_guest} -> score_lbw: {actual_score_lbw} (expected: {expected_score_lbw:.2f})")
            print(f"  Glass/G: {glassware_per_guest} -> score_glass: {actual_score_glass} (expected: {expected_score_glass:.2f})")
            print(f"  G/LSC: {guests_per_lsc} -> score_lsc: {actual_score_lsc} (expected: {expected_score_lsc:.2f})")
            
            # Allow small floating point differences
            assert abs(actual_score_ppa - expected_score_ppa) < 0.1, f"score_ppa mismatch for {name}"
            assert abs(actual_score_lbw - expected_score_lbw) < 0.1, f"score_lbw mismatch for {name}"
            assert abs(actual_score_glass - expected_score_glass) < 0.1, f"score_glass mismatch for {name}"
            if guests_per_lsc > 0:
                assert abs(actual_score_lsc - expected_score_lsc) < 0.1, f"score_lsc mismatch for {name}"
        
        print(f"\n✓ Score formula verified for {min(3, len(employees))} employees")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

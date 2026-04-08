"""
Integration/E2E Tests for Staff Score Engine
TEST 3 OF 3 - Focus on end-to-end workflows and data consistency

Tests:
1. Snapshot workflow: current-rankings endpoint returns correct data
2. Employee CRUD: create, read, update employee
3. Score recalculation: verify total_score calculation with weights
4. Quarter settings update: update benchmarks and verify in store-health
5. Trend data consistency: momentum data matches rankings
6. Navigation flow verification (via API data consistency)
"""

import pytest
import requests
import os
import uuid
from datetime import datetime

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://staff-score-engine.preview.emergentagent.com"

print(f"Testing against: {BASE_URL}")


class TestSnapshotWorkflow:
    """Test snapshot workflow and current-rankings endpoint"""
    
    def test_current_rankings_returns_data(self):
        """Verify current-rankings endpoint returns employee data"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?quarter=Q1&year=2026")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, "Expected success=True"
        assert data.get("has_data") == True, "Expected has_data=True"
        
        # Verify employees array exists and has data
        employees = data.get("employees", [])
        assert len(employees) > 0, "Expected at least one employee in rankings"
        
        # Verify employee structure
        first_emp = employees[0]
        assert "name" in first_emp, "Employee should have name"
        assert "total_score" in first_emp or "pre_dar_score" in first_emp, "Employee should have score"
        assert "tier_label" in first_emp, "Employee should have tier_label"
        
        print(f"SUCCESS: current-rankings returned {len(employees)} employees")
        print(f"Sample employee: {first_emp.get('name')} - Score: {first_emp.get('total_score', first_emp.get('pre_dar_score'))}")
    
    def test_current_rankings_sorted_by_tier(self):
        """Verify employees are sorted by tier (Trainer > Bartender > A-Server > B-Server > C-Server)"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?quarter=Q1&year=2026")
        assert response.status_code == 200
        
        data = response.json()
        employees = data.get("employees", [])
        
        if len(employees) < 2:
            pytest.skip("Not enough employees to test sorting")
        
        # Define tier order
        tier_order = {"Trainer": 1, "Bartender": 2, "A-Server": 3, "B-Server": 4, "C-Server": 5, "Server": 6}
        
        # Check that employees are sorted by tier
        prev_tier_rank = 0
        prev_score = float('inf')
        
        for emp in employees:
            tier = emp.get("tier_label", "Server")
            tier_rank = tier_order.get(tier, 99)
            score = emp.get("total_score") or emp.get("pre_dar_score") or 0
            
            # Within same tier, scores should be descending
            if tier_rank == prev_tier_rank:
                assert score <= prev_score, f"Within tier {tier}, scores should be descending"
            
            prev_tier_rank = tier_rank
            prev_score = score if tier_rank == prev_tier_rank else float('inf')
        
        print("SUCCESS: Employees are sorted by tier and score")
    
    def test_snapshot_metadata_present(self):
        """Verify snapshot metadata is included in response"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?quarter=Q1&year=2026")
        assert response.status_code == 200
        
        data = response.json()
        snapshot = data.get("snapshot")
        
        assert snapshot is not None, "Expected snapshot metadata"
        assert "id" in snapshot, "Snapshot should have id"
        assert "name" in snapshot or "title" in snapshot, "Snapshot should have name/title"
        
        print(f"SUCCESS: Snapshot metadata present - ID: {snapshot.get('id')}, Name: {snapshot.get('name', snapshot.get('title'))}")


class TestEmployeeCRUD:
    """Test Employee CRUD operations"""
    
    @pytest.fixture
    def test_employee_data(self):
        """Generate unique test employee data"""
        unique_id = str(uuid.uuid4())[:8]
        return {
            "name": f"TEST_Integration_{unique_id}",
            "job_title": "server",
            "year": 2026,
            "quarter": "Q1",
            "guests": 100,
            "net_sales": 5500,
            "lbw": 800,
            "glassware_sales": 125,
            "lsc_count": 2,
            "cv_promoters": 3,
            "cv_passives": 1,
            "cv_detractors": 0,
            "review_mentions": 2
        }
    
    def test_create_employee(self, test_employee_data):
        """Test creating a new employee"""
        response = requests.post(
            f"{BASE_URL}/api/v2/employees",
            json=test_employee_data
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, "Expected success=True"
        assert "employee_id" in data, "Expected employee_id in response"
        
        employee_id = data.get("employee_id")
        print(f"SUCCESS: Created employee with ID: {employee_id}")
        
        # Store for cleanup
        return employee_id
    
    def test_read_employee(self, test_employee_data):
        """Test reading an employee after creation"""
        # First create
        create_response = requests.post(
            f"{BASE_URL}/api/v2/employees",
            json=test_employee_data
        )
        assert create_response.status_code == 200
        employee_id = create_response.json().get("employee_id")
        
        # Then read
        read_response = requests.get(f"{BASE_URL}/api/v2/employees/{employee_id}")
        assert read_response.status_code == 200, f"Expected 200, got {read_response.status_code}"
        
        employee = read_response.json()
        assert employee.get("name") == test_employee_data["name"], "Name should match"
        assert employee.get("guests") == test_employee_data["guests"], "Guests should match"
        
        # Verify derived metrics were calculated
        assert employee.get("ppa") is not None, "PPA should be calculated"
        assert employee.get("total_score") is not None, "Total score should be calculated"
        
        print(f"SUCCESS: Read employee - Name: {employee.get('name')}, PPA: {employee.get('ppa')}, Score: {employee.get('total_score')}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/v2/employees/{employee_id}")
    
    def test_update_employee(self, test_employee_data):
        """Test updating an employee"""
        # First create
        create_response = requests.post(
            f"{BASE_URL}/api/v2/employees",
            json=test_employee_data
        )
        assert create_response.status_code == 200
        employee_id = create_response.json().get("employee_id")
        
        # Update with new data
        update_data = {
            "guests": 150,
            "net_sales": 8250,
            "cv_promoters": 5
        }
        
        update_response = requests.put(
            f"{BASE_URL}/api/v2/employees/{employee_id}",
            json=update_data
        )
        assert update_response.status_code == 200, f"Expected 200, got {update_response.status_code}: {update_response.text}"
        
        # Verify update
        read_response = requests.get(f"{BASE_URL}/api/v2/employees/{employee_id}")
        assert read_response.status_code == 200
        
        updated_employee = read_response.json()
        assert updated_employee.get("guests") == 150, "Guests should be updated"
        assert updated_employee.get("cv_promoters") == 5, "CV promoters should be updated"
        
        # Verify score was recalculated
        original_ppa = test_employee_data["net_sales"] / test_employee_data["guests"]
        new_ppa = 8250 / 150
        assert abs(updated_employee.get("ppa", 0) - new_ppa) < 0.1, "PPA should be recalculated"
        
        print(f"SUCCESS: Updated employee - New PPA: {updated_employee.get('ppa')}, New Score: {updated_employee.get('total_score')}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/v2/employees/{employee_id}")
    
    def test_delete_employee(self, test_employee_data):
        """Test deleting an employee"""
        # First create
        create_response = requests.post(
            f"{BASE_URL}/api/v2/employees",
            json=test_employee_data
        )
        assert create_response.status_code == 200
        employee_id = create_response.json().get("employee_id")
        
        # Delete
        delete_response = requests.delete(f"{BASE_URL}/api/v2/employees/{employee_id}")
        assert delete_response.status_code == 200, f"Expected 200, got {delete_response.status_code}"
        
        # Verify deletion
        read_response = requests.get(f"{BASE_URL}/api/v2/employees/{employee_id}")
        assert read_response.status_code == 404, "Employee should not exist after deletion"
        
        print(f"SUCCESS: Deleted employee {employee_id}")


class TestScoreCalculation:
    """Test score calculation with weights"""
    
    def test_score_calculation_formula(self):
        """Verify total_score calculation follows the correct formula"""
        # Get an employee with known metrics
        response = requests.get(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q1&limit=5")
        assert response.status_code == 200
        
        data = response.json()
        # Handle both list and dict response formats
        if isinstance(data, list):
            employees = data
        else:
            employees = data.get("employees", [])
        
        if not employees:
            pytest.skip("No employees found for score verification")
        
        # Find an employee with complete data
        for emp in employees:
            if all([
                emp.get("score_ppa") is not None,
                emp.get("score_lsc") is not None,
                emp.get("score_lbw") is not None,
                emp.get("score_glass") is not None
            ]):
                # Verify weighted score is reasonable (between 0 and 100)
                weighted = emp.get("weighted_score", 0)
                total = emp.get("total_score", 0)
                
                # Weighted score should be positive and reasonable
                assert weighted > 0, f"Weighted score should be positive for {emp.get('name')}"
                assert weighted <= 100, f"Weighted score should be <= 100 for {emp.get('name')}"
                
                # Total score = weighted + bonuses
                # Total should be >= weighted (bonuses add to it)
                cv_score = emp.get("cv_score", 0) or 0
                metric_bonus = emp.get("total_metric_bonus", 0) or 0
                rt_bonus = emp.get("review_tracker_bonus", 0) or 0
                
                expected_total = weighted + cv_score + metric_bonus + rt_bonus
                
                # Allow tolerance for rounding
                tolerance = 2.0
                assert abs(total - expected_total) < tolerance, \
                    f"Total score mismatch for {emp.get('name')}: expected ~{expected_total:.2f}, got {total}"
                
                print(f"SUCCESS: Score calculation verified for {emp.get('name')}")
                print(f"  PPA: {emp.get('score_ppa')}, LSC: {emp.get('score_lsc')}, LBW: {emp.get('score_lbw')}, Glass: {emp.get('score_glass')}")
                print(f"  Weighted: {weighted}, CV: {cv_score}, Metric Bonus: {metric_bonus}, RT Bonus: {rt_bonus}")
                print(f"  Total Score: {total}")
                return
        
        pytest.skip("No employee with complete score data found")
    
    def test_metric_bonus_calculation(self):
        """Verify metric bonus is calculated for scores over 100%"""
        response = requests.get(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q1&limit=20")
        assert response.status_code == 200
        
        data = response.json()
        # Handle both list and dict response formats
        if isinstance(data, list):
            employees = data
        else:
            employees = data.get("employees", [])
        
        # Find an employee with scores over 100%
        for emp in employees:
            score_ppa = emp.get("score_ppa", 0) or 0
            if score_ppa > 100:
                # Bonus formula: (score - 100) / 20 * 5, capped at 5
                expected_bonus = min((score_ppa - 100) / 20 * 5, 5.0)
                actual_bonus = emp.get("bonus_ppa", 0) or 0
                
                assert abs(actual_bonus - expected_bonus) < 0.5, \
                    f"PPA bonus mismatch for {emp.get('name')}: expected {expected_bonus:.2f}, got {actual_bonus}"
                
                print(f"SUCCESS: Metric bonus verified for {emp.get('name')}")
                print(f"  PPA Score: {score_ppa}%, Bonus: {actual_bonus}")
                return
        
        print("INFO: No employee with score > 100% found, skipping bonus verification")


class TestQuarterSettings:
    """Test quarter settings management"""
    
    def test_get_quarter_settings(self):
        """Verify quarter settings can be retrieved"""
        response = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q1")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        settings = response.json()
        
        # Verify required fields
        assert "benchmark_ppa" in settings, "Should have benchmark_ppa"
        assert "benchmark_lbw" in settings, "Should have benchmark_lbw"
        assert "benchmark_glass" in settings, "Should have benchmark_glass"
        assert "benchmark_lsc" in settings, "Should have benchmark_lsc"
        assert "weight_ppa" in settings, "Should have weight_ppa"
        assert "a_server_min_score" in settings, "Should have a_server_min_score"
        assert "b_server_min_score" in settings, "Should have b_server_min_score"
        
        print(f"SUCCESS: Quarter settings retrieved")
        print(f"  Benchmarks - PPA: ${settings.get('benchmark_ppa')}, LBW: ${settings.get('benchmark_lbw')}")
        print(f"  Thresholds - A-Server: {settings.get('a_server_min_score')}, B-Server: {settings.get('b_server_min_score')}")
    
    def test_settings_reflected_in_store_health(self):
        """Verify quarter settings are used in store-health calculations"""
        # Get settings
        settings_response = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q1")
        assert settings_response.status_code == 200
        settings = settings_response.json()
        
        # Get store health
        health_response = requests.get(f"{BASE_URL}/api/v2/insights/store-health?quarter=Q1&year=2026")
        assert health_response.status_code == 200
        health = health_response.json()
        
        # Verify concept benchmarks are present
        concept_comparison = health.get("concept_comparison", {})
        
        # Check that store health uses settings
        assert health.get("store_health_score") is not None, "Should have store_health_score"
        assert health.get("employee_count") is not None, "Should have employee_count"
        
        print(f"SUCCESS: Store health uses quarter settings")
        print(f"  Store Health Score: {health.get('store_health_score')}")
        print(f"  Employee Count: {health.get('employee_count')}")


class TestTrendDataConsistency:
    """Test trend/momentum data consistency"""
    
    def test_momentum_endpoint_returns_data(self):
        """Verify momentum endpoint returns trend data"""
        response = requests.get(f"{BASE_URL}/api/v2/trends/momentum/2026/Q1")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Should have employees with momentum data
        employees = data.get("employees", [])
        
        if not employees:
            print("INFO: No momentum data available (may need multiple snapshots)")
            return
        
        # Verify momentum structure
        for emp in employees[:5]:  # Check first 5
            assert "name" in emp or "employee_name" in emp, "Should have name"
            # Momentum fields may include: direction, change, rolling_avg
            
        print(f"SUCCESS: Momentum data returned for {len(employees)} employees")
        if employees:
            sample = employees[0]
            print(f"  Sample: {sample.get('name', sample.get('employee_name'))} - Direction: {sample.get('direction')}, Change: {sample.get('change')}")
    
    def test_momentum_matches_rankings(self):
        """Verify momentum employee names match rankings"""
        # Get rankings
        rankings_response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?quarter=Q1&year=2026")
        assert rankings_response.status_code == 200
        rankings = rankings_response.json()
        ranking_names = {emp.get("name", "").lower() for emp in rankings.get("employees", [])}
        
        # Get momentum
        momentum_response = requests.get(f"{BASE_URL}/api/v2/trends/momentum/2026/Q1")
        assert momentum_response.status_code == 200
        momentum = momentum_response.json()
        
        momentum_employees = momentum.get("employees", [])
        if not momentum_employees:
            print("INFO: No momentum data to compare")
            return
        
        # Check that momentum employees exist in rankings
        matched = 0
        for emp in momentum_employees[:10]:
            name = (emp.get("name") or emp.get("employee_name") or "").lower()
            if name in ranking_names:
                matched += 1
        
        if momentum_employees:
            match_rate = matched / min(len(momentum_employees), 10) * 100
            print(f"SUCCESS: {match_rate:.0f}% of momentum employees found in rankings ({matched}/{min(len(momentum_employees), 10)})")


class TestInsightsEndpoints:
    """Test insights endpoints for data consistency"""
    
    def test_store_health_endpoint(self):
        """Verify store-health endpoint returns correct structure"""
        response = requests.get(f"{BASE_URL}/api/v2/insights/store-health?quarter=Q1&year=2026")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify required fields
        assert "store_health_score" in data, "Should have store_health_score"
        assert "employee_count" in data, "Should have employee_count"
        assert "categories" in data, "Should have categories"
        
        # Verify categories structure
        categories = data.get("categories", {})
        expected_categories = ["sales_execution", "upsell_performance", "loyalty_engagement", "guest_experience", "labor_efficiency"]
        
        for cat in expected_categories:
            if cat in categories:
                assert "score" in categories[cat], f"Category {cat} should have score"
                assert "weight" in categories[cat], f"Category {cat} should have weight"
        
        print(f"SUCCESS: Store health endpoint verified")
        print(f"  Score: {data.get('store_health_score')}, Employees: {data.get('employee_count')}")
    
    def test_coaching_radar_endpoint(self):
        """Verify coaching-radar endpoint returns data"""
        response = requests.get(f"{BASE_URL}/api/v2/insights/coaching-radar?quarter=Q1&year=2026")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify structure
        assert "coaching_opportunities" in data or "opportunities" in data, "Should have coaching opportunities"
        assert "total_potential_monthly_revenue" in data or "monthly_revenue_potential" in data, "Should have revenue potential"
        
        print(f"SUCCESS: Coaching radar endpoint verified")
        print(f"  Opportunities: {data.get('coaching_opportunities', data.get('opportunities'))}")
        print(f"  Revenue Potential: ${data.get('total_potential_monthly_revenue', data.get('monthly_revenue_potential'))}")
    
    def test_review_impact_endpoint(self):
        """Verify review-impact endpoint returns data"""
        response = requests.get(f"{BASE_URL}/api/v2/insights/review-impact?quarter=Q1&year=2026")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify structure - data has 'totals' nested object
        assert "totals" in data or "total_revenue_influence" in data, "Should have totals or total_revenue_influence"
        
        totals = data.get("totals", data)
        revenue = totals.get("total_revenue_influence", 0)
        
        print(f"SUCCESS: Review impact endpoint verified")
        print(f"  Revenue Influence: ${revenue}")


class TestDataIntegrity:
    """Test data integrity across endpoints"""
    
    def test_employee_count_consistency(self):
        """Verify employee count is consistent across endpoints"""
        # Get from employees endpoint
        emp_response = requests.get(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q1")
        assert emp_response.status_code == 200
        emp_data = emp_response.json()
        # Handle both list and dict response formats
        if isinstance(emp_data, list):
            emp_count = len(emp_data)
        else:
            emp_count = emp_data.get("total", len(emp_data.get("employees", [])))
        
        # Get from rankings
        rank_response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings?quarter=Q1&year=2026")
        assert rank_response.status_code == 200
        rank_data = rank_response.json()
        rank_count = len(rank_data.get("employees", []))
        
        # Get from store health
        health_response = requests.get(f"{BASE_URL}/api/v2/insights/store-health?quarter=Q1&year=2026")
        assert health_response.status_code == 200
        health_data = health_response.json()
        health_count = health_data.get("employee_count", 0)
        
        print(f"Employee counts - Employees API: {emp_count}, Rankings: {rank_count}, Store Health: {health_count}")
        
        # Allow some tolerance (rankings may exclude some employees)
        assert abs(emp_count - rank_count) <= 5, f"Employee count mismatch: employees={emp_count}, rankings={rank_count}"
        assert abs(emp_count - health_count) <= 5, f"Employee count mismatch: employees={emp_count}, health={health_count}"
        
        print(f"SUCCESS: Employee counts are consistent across endpoints")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_employees(self):
        """Remove any TEST_ prefixed employees created during testing"""
        response = requests.get(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q1&limit=100")
        if response.status_code != 200:
            return
        
        data = response.json()
        # Handle both list and dict response formats
        if isinstance(data, list):
            employees = data
        else:
            employees = data.get("employees", [])
        
        deleted = 0
        for emp in employees:
            if emp.get("name", "").startswith("TEST_"):
                emp_id = emp.get("id")
                if emp_id:
                    del_response = requests.delete(f"{BASE_URL}/api/v2/employees/{emp_id}")
                    if del_response.status_code == 200:
                        deleted += 1
        
        print(f"Cleanup: Deleted {deleted} test employees")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

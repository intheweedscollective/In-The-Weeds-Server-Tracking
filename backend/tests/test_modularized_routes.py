"""
Backend API Tests for Modularized Routes
Tests the following endpoints after route extraction to insights.py and pos_upload.py:
- GET /api/v2/insights/store-health - Store Performance Index with concept benchmarks
- GET /api/v2/insights/coaching-radar - Coaching opportunities
- GET /api/v2/insights/review-impact - Review revenue impact
- GET /api/v2/trends/momentum/{year}/{quarter} - Momentum indicators
- GET /api/v2/employees - Employee listing
- GET /api/v2/quarter-settings/{year}/{quarter} - Quarter settings with concept benchmarks
- GET /api/v2/snapshot-workflow/current-rankings - Current rankings
"""

import pytest
import requests
import os

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable not set")


class TestHealthCheck:
    """Basic health check to verify API is running"""
    
    def test_health_endpoint(self):
        """Test /api/health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        data = response.json()
        assert data.get("status") == "healthy"
        print(f"✓ Health check passed: {data}")


class TestInsightsEndpoints:
    """Tests for modularized insights.py endpoints"""
    
    def test_store_health_score(self):
        """Test GET /api/v2/insights/store-health - Store Performance Index"""
        response = requests.get(f"{BASE_URL}/api/v2/insights/store-health", params={
            "quarter": "Q1",
            "year": 2026
        })
        assert response.status_code == 200, f"Store health failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "store_health_score" in data, "Missing store_health_score"
        assert "categories" in data, "Missing categories"
        assert "employee_count" in data, "Missing employee_count"
        assert "quarter" in data, "Missing quarter"
        assert "year" in data, "Missing year"
        
        # Verify categories structure
        categories = data.get("categories", {})
        expected_categories = ["sales_execution", "upsell_performance", "loyalty_engagement", 
                              "labor_efficiency", "guest_experience"]
        for cat in expected_categories:
            assert cat in categories, f"Missing category: {cat}"
            assert "score" in categories[cat], f"Missing score in {cat}"
            assert "weight" in categories[cat], f"Missing weight in {cat}"
            assert "label" in categories[cat], f"Missing label in {cat}"
        
        # Verify concept comparison data
        assert "concept_comparison" in data, "Missing concept_comparison"
        assert "benchmarks" in data, "Missing benchmarks"
        assert "awards" in data, "Missing awards"
        
        print(f"✓ Store health score: {data.get('store_health_score')}")
        print(f"  - Employee count: {data.get('employee_count')}")
        print(f"  - Categories: {list(categories.keys())}")
        print(f"  - Concept comparison: {data.get('concept_comparison', {}).keys()}")
    
    def test_coaching_radar(self):
        """Test GET /api/v2/insights/coaching-radar - Coaching opportunities"""
        response = requests.get(f"{BASE_URL}/api/v2/insights/coaching-radar", params={
            "quarter": "Q1",
            "year": 2026
        })
        assert response.status_code == 200, f"Coaching radar failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "coaching_opportunities" in data, "Missing coaching_opportunities"
        assert "total_potential_monthly_revenue" in data, "Missing total_potential_monthly_revenue"
        assert "employees_needing_coaching" in data, "Missing employees_needing_coaching"
        assert "total_employees" in data, "Missing total_employees"
        assert "benchmarks" in data, "Missing benchmarks"
        assert "quarter" in data, "Missing quarter"
        assert "year" in data, "Missing year"
        
        # Verify coaching opportunities structure if any exist
        opportunities = data.get("coaching_opportunities", [])
        if opportunities:
            first_opp = opportunities[0]
            assert "employee_id" in first_opp or "employee_name" in first_opp, "Missing employee identifier"
            assert "opportunities" in first_opp, "Missing opportunities list"
            assert "total_potential_monthly" in first_opp, "Missing total_potential_monthly"
        
        print(f"✓ Coaching radar: {len(opportunities)} opportunities found")
        print(f"  - Total potential monthly revenue: ${data.get('total_potential_monthly_revenue', 0):,.0f}")
        print(f"  - Employees needing coaching: {data.get('employees_needing_coaching')}/{data.get('total_employees')}")
    
    def test_review_impact(self):
        """Test GET /api/v2/insights/review-impact - Review revenue impact"""
        response = requests.get(f"{BASE_URL}/api/v2/insights/review-impact", params={
            "quarter": "Q1",
            "year": 2026
        })
        assert response.status_code == 200, f"Review impact failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "review_impact" in data, "Missing review_impact"
        assert "totals" in data, "Missing totals"
        assert "methodology" in data, "Missing methodology"
        assert "quarter" in data, "Missing quarter"
        assert "year" in data, "Missing year"
        
        # Verify totals structure
        totals = data.get("totals", {})
        assert "total_mentions" in totals, "Missing total_mentions in totals"
        assert "total_promoters" in totals, "Missing total_promoters in totals"
        assert "total_revenue_influence" in totals, "Missing total_revenue_influence in totals"
        
        # Verify methodology
        methodology = data.get("methodology", {})
        assert "revenue_per_mention" in methodology, "Missing revenue_per_mention"
        assert "revenue_per_promoter" in methodology, "Missing revenue_per_promoter"
        
        print(f"✓ Review impact: {len(data.get('review_impact', []))} employees with impact")
        print(f"  - Total revenue influence: ${totals.get('total_revenue_influence', 0):,.0f}")
        print(f"  - Total mentions: {totals.get('total_mentions', 0)}")


class TestTrendsEndpoints:
    """Tests for modularized trends.py endpoints"""
    
    def test_momentum_indicators(self):
        """Test GET /api/v2/trends/momentum/{year}/{quarter} - Momentum indicators"""
        response = requests.get(f"{BASE_URL}/api/v2/trends/momentum/2026/Q1")
        assert response.status_code == 200, f"Momentum failed: {response.text}"
        data = response.json()
        
        # Response should be a dictionary of employee_id -> momentum data
        assert isinstance(data, dict), "Response should be a dictionary"
        
        # If there's data, verify structure
        if data:
            first_key = list(data.keys())[0]
            first_emp = data[first_key]
            
            # Verify momentum data structure
            assert "current_score" in first_emp, "Missing current_score"
            assert "rolling_avg" in first_emp, "Missing rolling_avg"
            assert "change" in first_emp, "Missing change"
            assert "direction" in first_emp, "Missing direction"
            assert "percent_change" in first_emp, "Missing percent_change"
            assert "snapshots_used" in first_emp, "Missing snapshots_used"
            
            # Verify direction is valid
            assert first_emp["direction"] in ["up", "down", "stable"], f"Invalid direction: {first_emp['direction']}"
            
            print(f"✓ Momentum indicators: {len(data)} employees")
            # Show sample data
            sample_count = min(3, len(data))
            for i, (emp_id, emp_data) in enumerate(list(data.items())[:sample_count]):
                print(f"  - {emp_data.get('employee_name', emp_id)}: {emp_data['direction']} ({emp_data['change']:+.2f})")
        else:
            print("✓ Momentum indicators: No data (expected if no snapshots)")


class TestEmployeesEndpoint:
    """Tests for employee listing endpoint"""
    
    def test_get_employees(self):
        """Test GET /api/v2/employees - Employee listing"""
        response = requests.get(f"{BASE_URL}/api/v2/employees", params={
            "quarter": "Q1",
            "year": 2026
        })
        assert response.status_code == 200, f"Employees failed: {response.text}"
        data = response.json()
        
        # Response should be a list
        assert isinstance(data, list), "Response should be a list"
        
        # If there are employees, verify structure
        if data:
            first_emp = data[0]
            
            # Verify essential fields
            assert "id" in first_emp or "employee_id" in first_emp, "Missing employee id"
            assert "name" in first_emp, "Missing name"
            
            # Check for scoring fields
            scoring_fields = ["total_score", "pre_dar_score", "weighted_score"]
            has_scoring = any(field in first_emp for field in scoring_fields)
            
            print(f"✓ Employees: {len(data)} employees found")
            print(f"  - Sample employee: {first_emp.get('name')}")
            print(f"  - Has scoring data: {has_scoring}")
            if has_scoring:
                print(f"  - Total score: {first_emp.get('total_score', 'N/A')}")
        else:
            print("✓ Employees: No employees found for Q1 2026")


class TestQuarterSettingsEndpoint:
    """Tests for quarter settings endpoint"""
    
    def test_get_quarter_settings(self):
        """Test GET /api/v2/quarter-settings/{year}/{quarter} - Quarter settings"""
        response = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q1")
        assert response.status_code == 200, f"Quarter settings failed: {response.text}"
        data = response.json()
        
        # Verify essential benchmark fields
        assert "benchmark_ppa" in data, "Missing benchmark_ppa"
        assert "benchmark_lbw" in data, "Missing benchmark_lbw"
        assert "benchmark_glass" in data, "Missing benchmark_glass"
        assert "benchmark_lsc" in data, "Missing benchmark_lsc"
        
        # Verify weight fields
        assert "weight_ppa" in data, "Missing weight_ppa"
        assert "weight_lbw" in data, "Missing weight_lbw"
        assert "weight_glass" in data, "Missing weight_glass"
        assert "weight_lsc" in data, "Missing weight_lsc"
        
        # Verify tier thresholds
        assert "a_server_min_score" in data, "Missing a_server_min_score"
        assert "b_server_min_score" in data, "Missing b_server_min_score"
        
        # Verify concept benchmarks (new fields from Flash Report)
        concept_fields = ["concept_avg_ppa", "concept_lsc_ratio", "concept_labor_pct", 
                         "target_labor_pct", "store_labor_pct"]
        for field in concept_fields:
            if field in data:
                print(f"  - {field}: {data[field]}")
        
        print(f"✓ Quarter settings for Q1 2026:")
        print(f"  - PPA benchmark: ${data.get('benchmark_ppa')}")
        print(f"  - LBW benchmark: ${data.get('benchmark_lbw')}")
        print(f"  - Glass benchmark: ${data.get('benchmark_glass')}")
        print(f"  - LSC benchmark: {data.get('benchmark_lsc')}")
        print(f"  - A-Server min: {data.get('a_server_min_score')}")
        print(f"  - B-Server min: {data.get('b_server_min_score')}")
    
    def test_get_all_quarter_settings(self):
        """Test GET /api/v2/quarter-settings - All quarter settings"""
        response = requests.get(f"{BASE_URL}/api/v2/quarter-settings")
        assert response.status_code == 200, f"All quarter settings failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ All quarter settings: {len(data)} quarters configured")
        for setting in data[:3]:  # Show first 3
            print(f"  - {setting.get('quarter')} {setting.get('year')}")


class TestSnapshotWorkflowEndpoint:
    """Tests for snapshot workflow current-rankings endpoint"""
    
    def test_current_rankings(self):
        """Test GET /api/v2/snapshot-workflow/current-rankings - Current rankings"""
        response = requests.get(f"{BASE_URL}/api/v2/snapshot-workflow/current-rankings", params={
            "quarter": "Q1",
            "year": 2026
        })
        assert response.status_code == 200, f"Current rankings failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "success" in data, "Missing success field"
        assert "has_data" in data, "Missing has_data field"
        
        if data.get("has_data"):
            assert "employees" in data, "Missing employees"
            assert "snapshot" in data, "Missing snapshot"
            
            employees = data.get("employees", [])
            snapshot = data.get("snapshot", {})
            
            # Verify snapshot info
            if snapshot:
                assert "id" in snapshot, "Missing snapshot id"
                assert "name" in snapshot, "Missing snapshot name"
            
            # Verify employee structure if any
            if employees:
                first_emp = employees[0]
                assert "name" in first_emp, "Missing employee name"
                
                # Check for tier_label (used for sorting)
                if "tier_label" in first_emp:
                    print(f"  - First employee tier: {first_emp.get('tier_label')}")
            
            print(f"✓ Current rankings: {len(employees)} employees")
            print(f"  - Snapshot: {snapshot.get('name', 'N/A')}")
            print(f"  - Effective date: {snapshot.get('effective_date', 'N/A')}")
        else:
            print(f"✓ Current rankings: No data (message: {data.get('message', 'N/A')})")


class TestInsightsWithNoData:
    """Test insights endpoints handle missing data gracefully"""
    
    def test_store_health_no_data(self):
        """Test store health with non-existent quarter"""
        response = requests.get(f"{BASE_URL}/api/v2/insights/store-health", params={
            "quarter": "Q4",
            "year": 2099  # Future year with no data
        })
        assert response.status_code == 200, f"Store health should handle no data: {response.text}"
        data = response.json()
        
        # Should return gracefully with message
        if data.get("employee_count", 0) == 0:
            assert "message" in data or data.get("store_health_score") == 0
            print("✓ Store health handles no data gracefully")
    
    def test_coaching_radar_no_data(self):
        """Test coaching radar with non-existent quarter"""
        response = requests.get(f"{BASE_URL}/api/v2/insights/coaching-radar", params={
            "quarter": "Q4",
            "year": 2099
        })
        assert response.status_code == 200, f"Coaching radar should handle no data: {response.text}"
        data = response.json()
        
        if data.get("total_employees", 0) == 0:
            assert "message" in data or len(data.get("coaching_opportunities", [])) == 0
            print("✓ Coaching radar handles no data gracefully")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

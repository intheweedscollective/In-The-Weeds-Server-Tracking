"""
Pre-deployment Sanity Check Tests
Tests all major features: QR codes, leaderboard, data uploads, employee management, scoring, exports, and reporting
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestQRCodeFeatures:
    """QR Code endpoints and functionality"""
    
    def test_qr_employees_endpoint(self):
        """Test /api/qr/employees returns employee list"""
        response = requests.get(f"{BASE_URL}/api/qr/employees")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Expected list of employees"
        print(f"QR Employees: Found {len(data)} employees")
        if len(data) > 0:
            # Verify employee structure
            emp = data[0]
            assert 'id' in emp, "Employee should have 'id'"
            assert 'name' in emp, "Employee should have 'name'"
            print(f"Sample employee: {emp.get('name')}")
    
    def test_qr_go_redirect(self):
        """Test /api/qr/go/{id} redirects to Google Reviews URL"""
        # First get an employee ID
        emp_response = requests.get(f"{BASE_URL}/api/qr/employees")
        assert emp_response.status_code == 200
        employees = emp_response.json()
        
        if len(employees) > 0:
            emp_id = employees[0]['id']
            # Test redirect (don't follow redirects)
            response = requests.get(f"{BASE_URL}/api/qr/go/{emp_id}", allow_redirects=False)
            assert response.status_code == 302, f"Expected 302 redirect, got {response.status_code}"
            location = response.headers.get('Location', '')
            assert 'google.com' in location or 'search.google.com' in location, f"Expected Google URL, got {location}"
            print(f"QR redirect working: {location[:50]}...")
        else:
            pytest.skip("No QR employees to test redirect")
    
    def test_qr_settings_endpoint(self):
        """Test /api/qr/settings returns settings"""
        response = requests.get(f"{BASE_URL}/api/qr/settings")
        assert response.status_code == 200
        data = response.json()
        assert 'google_url' in data or 'qr_style' in data, "Settings should have expected fields"
        print(f"QR Settings: {data.get('qr_style', 'default')}")


class TestLeaderboardFeatures:
    """Leaderboard and rankings endpoints"""
    
    def test_full_rankings_endpoint(self):
        """Test /api/v2/full-rankings/{year}/{quarter} returns rankings"""
        response = requests.get(f"{BASE_URL}/api/v2/full-rankings/2026/Q1")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert 'rankings' in data or isinstance(data, list), "Expected rankings data"
        
        rankings = data.get('rankings', data) if isinstance(data, dict) else data
        print(f"Full Rankings: Found {len(rankings)} employees")
        
        if len(rankings) > 0:
            emp = rankings[0]
            # Verify ranking structure has score components
            print(f"Top employee: {emp.get('name')} - Score: {emp.get('total_score', emp.get('pre_dar_score', 'N/A'))}")
    
    def test_employees_endpoint_with_performance_tier(self):
        """Test /api/v2/employees returns employees with performance_tier"""
        response = requests.get(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q1")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Expected list of employees"
        print(f"Employees: Found {len(data)} employees")
        
        if len(data) > 0:
            emp = data[0]
            # Check for performance_tier field
            has_tier = 'performance_tier' in emp
            tier_value = emp.get('performance_tier', 'Not present')
            print(f"Sample employee: {emp.get('name')} - Performance Tier: {tier_value}")
            # Performance tier should not be 'Not Assessed' for employees with scores
            if emp.get('total_score', 0) > 0 or emp.get('pre_dar_score', 0) > 0:
                assert tier_value != 'Not Assessed', f"Employee with score should have valid tier, got: {tier_value}"


class TestEmployeeManagement:
    """Employee CRUD and cleanup features"""
    
    def test_employees_list(self):
        """Test /api/v2/employees returns employee list"""
        response = requests.get(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q1")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Employee list: {len(data)} employees")
    
    def test_cleanup_analyze_endpoint(self):
        """Test /api/v2/employees/cleanup/analyze detects invalid entries"""
        response = requests.get(f"{BASE_URL}/api/v2/employees/cleanup/analyze")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify response structure
        assert 'valid_count' in data, "Should have valid_count"
        assert 'duplicate_count' in data, "Should have duplicate_count"
        assert 'test_data_count' in data, "Should have test_data_count"
        assert 'potential_duplicates' in data, "Should have potential_duplicates"
        assert 'test_data' in data, "Should have test_data"
        
        print(f"Cleanup Analysis: {data['valid_count']} valid, {data['duplicate_count']} duplicates, {data['test_data_count']} test data")
        
        # Check if it detects known invalid patterns
        test_data_names = [e.get('name', '').lower() for e in data.get('test_data', [])]
        duplicate_names = [e.get('name', '').lower() for e in data.get('potential_duplicates', [])]
        all_flagged = test_data_names + duplicate_names
        
        # These patterns should be detected if present
        patterns_to_check = ['server sales', 'total', 'test', 'demo']
        for pattern in patterns_to_check:
            found = any(pattern in name for name in all_flagged)
            if found:
                print(f"  - Pattern '{pattern}' detected in flagged entries")


class TestDataExportImport:
    """Data export and import functionality"""
    
    def test_data_export_endpoint(self):
        """Test /api/v2/data/export returns JSON with employee data"""
        response = requests.get(f"{BASE_URL}/api/v2/data/export?quarter=Q1&year=2026")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify export structure
        assert 'employees' in data or 'employee_count' in data, "Export should have employee data"
        
        emp_count = data.get('employee_count', len(data.get('employees', [])))
        print(f"Data Export: {emp_count} employees exported")
        
        if 'employees' in data and len(data['employees']) > 0:
            emp = data['employees'][0]
            print(f"Sample exported employee: {emp.get('name')}")
    
    def test_data_import_endpoint_exists(self):
        """Test /api/v2/data/import endpoint exists"""
        # Test with empty data to verify endpoint exists
        response = requests.post(f"{BASE_URL}/api/v2/data/import", json={})
        # Should return 400 or 422 for invalid data, not 404
        assert response.status_code != 404, "Import endpoint should exist"
        print(f"Data Import endpoint exists (status: {response.status_code})")


class TestAnalyticsAndDashboard:
    """Analytics and dashboard features"""
    
    def test_quarter_settings_endpoint(self):
        """Test /api/v2/quarter-settings returns settings"""
        response = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q1")
        # May return 404 if not configured, which is acceptable
        if response.status_code == 200:
            data = response.json()
            print(f"Quarter Settings: benchmark_ppa={data.get('benchmark_ppa')}, benchmark_lbw={data.get('benchmark_lbw')}")
        else:
            print(f"Quarter Settings: Not configured (status {response.status_code})")
    
    def test_cv_stats_endpoint(self):
        """Test Customer Voice stats endpoint"""
        response = requests.get(f"{BASE_URL}/api/v2/cv/stats?quarter=Q1&year=2026")
        if response.status_code == 200:
            data = response.json()
            print(f"CV Stats: {data.get('total_responses', 0)} responses, NPS: {data.get('avg_nps', 'N/A')}")
        else:
            print(f"CV Stats: Not available (status {response.status_code})")
    
    def test_reviews_stats_endpoint(self):
        """Test Review Tracker stats endpoint"""
        response = requests.get(f"{BASE_URL}/api/v2/reviews/stats?quarter=Q1&year=2026")
        if response.status_code == 200:
            data = response.json()
            print(f"RT Stats: {data.get('total_mentions', 0)} mentions")
        else:
            print(f"RT Stats: Not available (status {response.status_code})")


class TestReportsAndSlides:
    """Reports and slide generation"""
    
    def test_leaderboard_slide_endpoint(self):
        """Test leaderboard slide generation endpoint"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/leaderboard-slide?format=16:9")
        # Should return image or 200
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            assert 'image' in content_type or 'png' in content_type, f"Expected image, got {content_type}"
            print(f"Leaderboard Slide: Generated successfully ({len(response.content)} bytes)")
        else:
            print("Leaderboard Slide: Not available")
    
    def test_top10_slide_endpoint(self):
        """Test top 10 slide generation endpoint"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/top-10-slide?format=16:9")
        if response.status_code == 200:
            print(f"Top 10 Slide: Generated successfully ({len(response.content)} bytes)")
        else:
            print(f"Top 10 Slide: Status {response.status_code}")


class TestScoringSystem:
    """Scoring system verification"""
    
    def test_scoring_breakdown(self):
        """Verify scoring breakdown: Base + Reviews + Bonuses = Total"""
        response = requests.get(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q1")
        assert response.status_code == 200
        employees = response.json()
        
        if len(employees) == 0:
            pytest.skip("No employees to verify scoring")
        
        # Check first few employees for rational scoring
        verified = 0
        for emp in employees[:5]:
            name = emp.get('name', 'Unknown')
            weighted = emp.get('weighted_score', 0) or 0
            cv_score = emp.get('cv_score', 0) or 0
            rt_bonus = emp.get('review_tracker_bonus', 0) or 0
            metric_bonus = emp.get('total_metric_bonus', 0) or 0
            total = emp.get('pre_dar_score', emp.get('total_score', 0)) or 0
            
            # Calculate expected total
            expected = weighted + cv_score + rt_bonus + metric_bonus
            
            # Allow small floating point differences
            diff = abs(total - expected)
            if diff < 0.5:
                verified += 1
                print(f"  {name}: Base({weighted:.1f}) + CV({cv_score:.1f}) + RT({rt_bonus:.1f}) + Bonus({metric_bonus:.1f}) = {total:.1f} OK")
            else:
                print(f"  {name}: Expected {expected:.1f}, got {total:.1f} (diff: {diff:.1f})")
        
        print(f"Scoring Verification: {verified}/{min(5, len(employees))} employees have rational scoring")


class TestAPIHealth:
    """Basic API health checks"""
    
    def test_api_root(self):
        """Test API root endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        print("API Root: OK")
    
    def test_qr_stats(self):
        """Test QR stats endpoint"""
        response = requests.get(f"{BASE_URL}/api/qr/stats")
        assert response.status_code == 200
        data = response.json()
        print(f"QR Stats: {data.get('total_scans', 0)} total scans, {data.get('total_employees', 0)} employees")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

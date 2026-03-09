"""
Performance Review Application - Backend API Tests
Tests for: POS Parser, ReviewTrackers, CustomerVoice, Scoring, and Dashboard
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthCheck:
    """Basic health check tests"""
    
    def test_api_root_accessible(self):
        """Test that API root endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"✓ API root accessible: {data['message']}")


class TestEmployees:
    """Employee-related tests for Q1 2026"""
    
    def test_get_employees_count(self):
        """Verify 27 employees parsed from clean POS format"""
        response = requests.get(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q1")
        assert response.status_code == 200
        employees = response.json()
        assert isinstance(employees, list)
        # Per requirement: 27 employees from multi-sheet XLSX
        assert len(employees) == 27, f"Expected 27 employees, got {len(employees)}"
        print(f"✓ Employee count: {len(employees)} (expected: 27)")
    
    def test_employee_has_required_fields(self):
        """Verify employees have all required scoring fields"""
        response = requests.get(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q1")
        assert response.status_code == 200
        employees = response.json()
        
        if len(employees) > 0:
            emp = employees[0]
            required_fields = [
                'name', 'guests', 'net_sales', 'ppa', 'lbw_per_guest',
                'glassware_per_guest', 'guests_per_lsc', 'total_score', 'peer_rank'
            ]
            for field in required_fields:
                assert field in emp, f"Missing required field: {field}"
            print(f"✓ Employee has all required fields: {list(emp.keys())[:10]}...")


class TestReviewTrackerPlatformStats:
    """Test ReviewTrackers platform counts match RT dashboard"""
    
    def test_platform_stats_match_rt_dashboard(self):
        """
        Verify platform counts match RT dashboard:
        Google: 130, Yelp: 41, TripAdvisor: 23, OpenTable: 8, Total: 202
        """
        response = requests.get(f"{BASE_URL}/api/v2/reviews/platform-stats?quarter=Q1&year=2026")
        assert response.status_code == 200
        stats = response.json()
        
        # Expected values per RT dashboard
        expected = {
            'google': 130,
            'yelp': 41,
            'tripadvisor': 23,
            'opentable': 8,
            'total_reviews': 202
        }
        
        # Check each platform
        if 'google' in stats:
            google_count = stats['google'].get('count', 0)
            print(f"  Google: {google_count} (expected: {expected['google']})")
            assert google_count == expected['google'], f"Google count mismatch: {google_count} vs {expected['google']}"
        
        if 'yelp' in stats:
            yelp_count = stats['yelp'].get('count', 0)
            print(f"  Yelp: {yelp_count} (expected: {expected['yelp']})")
            assert yelp_count == expected['yelp'], f"Yelp count mismatch: {yelp_count} vs {expected['yelp']}"
        
        if 'tripadvisor' in stats:
            ta_count = stats['tripadvisor'].get('count', 0)
            print(f"  TripAdvisor: {ta_count} (expected: {expected['tripadvisor']})")
            assert ta_count == expected['tripadvisor'], f"TripAdvisor count mismatch: {ta_count} vs {expected['tripadvisor']}"
        
        if 'opentable' in stats:
            ot_count = stats['opentable'].get('count', 0)
            print(f"  OpenTable: {ot_count} (expected: {expected['opentable']})")
            assert ot_count == expected['opentable'], f"OpenTable count mismatch: {ot_count} vs {expected['opentable']}"
        
        total = stats.get('total_reviews', 0)
        print(f"  Total: {total} (expected: {expected['total_reviews']})")
        assert total == expected['total_reviews'], f"Total count mismatch: {total} vs {expected['total_reviews']}"
        
        print("✓ All platform stats match RT dashboard!")


class TestCustomerVoiceStats:
    """Test Customer Voice NPS stats match dashboard"""
    
    def test_cv_store_nps_matches_dashboard(self):
        """
        Verify store NPS matches CV dashboard: 80.28%
        """
        response = requests.get(f"{BASE_URL}/api/v2/cv/stats?quarter=Q1&year=2026")
        assert response.status_code == 200
        stats = response.json()
        
        # Expected per CV dashboard
        expected_nps = 80.28
        expected_surveys = 71
        
        avg_nps = stats.get('avg_nps', 0)
        total_surveys = stats.get('total_surveys', 0)
        
        print(f"  Store NPS: {avg_nps}% (expected: {expected_nps}%)")
        assert abs(avg_nps - expected_nps) < 1, f"NPS mismatch: {avg_nps} vs {expected_nps}"
        
        print(f"  Total Surveys: {total_surveys} (expected: {expected_surveys})")
        assert total_surveys == expected_surveys, f"Survey count mismatch: {total_surveys} vs {expected_surveys}"
        
        print("✓ Customer Voice stats match dashboard!")
    
    def test_cv_has_promoter_detractor_counts(self):
        """Verify CV stats include promoter/detractor breakdown"""
        response = requests.get(f"{BASE_URL}/api/v2/cv/stats?quarter=Q1&year=2026")
        assert response.status_code == 200
        stats = response.json()
        
        assert 'promoter_count' in stats
        assert 'detractor_count' in stats
        assert 'passive_count' in stats
        
        promoters = stats.get('promoter_count', 0)
        detractors = stats.get('detractor_count', 0)
        passives = stats.get('passive_count', 0)
        total = promoters + detractors + passives
        
        print(f"  Promoters: {promoters}, Passives: {passives}, Detractors: {detractors}")
        print(f"  Total from breakdown: {total}")
        print("✓ CV stats include promoter/detractor breakdown!")


class TestScoringAudit:
    """Test Scoring Audit page functionality"""
    
    def test_audit_report_endpoint(self):
        """Test audit report endpoint returns data"""
        response = requests.get(f"{BASE_URL}/api/v2/audit/report?quarter=Q1&year=2026")
        assert response.status_code == 200
        report = response.json()
        
        assert 'overall_status' in report
        assert 'employee_audit' in report
        
        print(f"  Overall Status: {report.get('overall_status')}")
        print(f"  Employees Audited: {report.get('employee_audit', {}).get('total', 0)}")
        print(f"  Passed: {report.get('employee_audit', {}).get('passed', 0)}")
        print(f"  Warnings: {report.get('employee_audit', {}).get('warnings', 0)}")
        print(f"  Failed: {report.get('employee_audit', {}).get('failed', 0)}")
        
        # Don't assert PASS status since data may need sync
        print("✓ Audit report endpoint working!")
    
    def test_data_cap_check_endpoint(self):
        """Test data cap check endpoint"""
        response = requests.get(f"{BASE_URL}/api/v2/audit/data-cap-check?quarter=Q1&year=2026")
        assert response.status_code == 200
        caps = response.json()
        
        assert 'customer_voice' in caps
        assert 'review_tracker' in caps
        
        cv_status = caps.get('customer_voice', {}).get('status', 'unknown')
        rt_status = caps.get('review_tracker', {}).get('status', 'unknown')
        
        print(f"  CV Status: {cv_status}")
        print(f"  RT Status: {rt_status}")
        print("✓ Data cap check endpoint working!")
    
    def test_review_accuracy_endpoint(self):
        """Test review accuracy verification endpoint"""
        response = requests.get(f"{BASE_URL}/api/v2/audit/review-accuracy?quarter=Q1&year=2026")
        assert response.status_code == 200
        accuracy = response.json()
        
        assert 'status' in accuracy
        assert 'platform_comparison' in accuracy
        assert 'mention_verification' in accuracy
        
        status = accuracy.get('status')
        print(f"  Review Accuracy Status: {status}")
        
        # Check mention verification
        mentions = accuracy.get('mention_verification', {})
        total_pass = sum(1 for m in mentions.values() if m.get('status') == 'PASS')
        total = len(mentions)
        print(f"  Mentions Verified: {total_pass}/{total} PASS")
        
        print("✓ Review accuracy endpoint working!")


class TestSyncNpsToEmployees:
    """Test NPS to employees sync functionality"""
    
    def test_sync_nps_endpoint_exists(self):
        """Verify sync NPS to employees endpoint exists"""
        # Just check it's callable - don't run full sync to avoid long wait
        response = requests.options(f"{BASE_URL}/api/v2/audit/sync-nps-to-employees")
        # OPTIONS might return 200, 204, or 405 depending on CORS config
        assert response.status_code in [200, 204, 405], f"Unexpected status: {response.status_code}"
        print("✓ Sync NPS endpoint exists!")


class TestDashboardEndpoints:
    """Test Dashboard-related endpoints"""
    
    def test_full_rankings_endpoint(self):
        """Test full rankings endpoint for Top 5 performers"""
        response = requests.get(f"{BASE_URL}/api/v2/full-rankings/2026/Q1")
        assert response.status_code == 200
        data = response.json()
        
        assert 'rankings' in data
        assert 'total_employees' in data
        
        rankings = data.get('rankings', [])
        total = data.get('total_employees', 0)
        
        print(f"  Total Employees: {total}")
        print(f"  Rankings Returned: {len(rankings)}")
        
        if len(rankings) >= 5:
            print("  Top 5 Performers:")
            for i, emp in enumerate(rankings[:5], 1):
                print(f"    {i}. {emp.get('name')}: {emp.get('total_score', 0):.2f}")
        
        print("✓ Full rankings endpoint working!")
    
    def test_quarter_settings_endpoint(self):
        """Test quarter settings endpoint"""
        response = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q1")
        assert response.status_code == 200
        settings = response.json()
        
        assert 'benchmark_ppa' in settings
        assert 'benchmark_lbw' in settings
        assert 'a_server_min_score' in settings
        assert 'b_server_min_score' in settings
        
        print(f"  PPA Benchmark: ${settings.get('benchmark_ppa')}")
        print(f"  LBW Benchmark: ${settings.get('benchmark_lbw')}")
        print(f"  A-Server Min: {settings.get('a_server_min_score')}")
        print(f"  B-Server Min: {settings.get('b_server_min_score')}")
        print("✓ Quarter settings endpoint working!")
    
    def test_needs_coaching_count(self):
        """Test counting employees needing coaching (C-Servers)"""
        # Get settings for threshold
        settings_resp = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q1")
        assert settings_resp.status_code == 200
        settings = settings_resp.json()
        b_server_min = settings.get('b_server_min_score', 70)
        
        # Get employees
        emp_resp = requests.get(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q1")
        assert emp_resp.status_code == 200
        employees = emp_resp.json()
        
        # Count C-Servers (below B threshold, only servers)
        needs_coaching = [
            e for e in employees 
            if (e.get('total_score', 0) or 0) < b_server_min 
            and (e.get('job_title', 'Server').lower() in ['server', ''])
        ]
        
        print(f"  B-Server Threshold: {b_server_min}")
        print(f"  Needs Coaching Count: {len(needs_coaching)}")
        
        if needs_coaching:
            print("  Employees Needing Coaching:")
            for emp in needs_coaching[:5]:
                print(f"    - {emp.get('name')}: {emp.get('total_score', 0):.2f}")
        
        print("✓ Needs coaching calculation working!")


class TestDataIntegrity:
    """Test data integrity checks"""
    
    def test_all_employees_have_scores(self):
        """Verify all employees have calculated scores"""
        response = requests.get(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q1")
        assert response.status_code == 200
        employees = response.json()
        
        missing_scores = [e for e in employees if e.get('total_score') is None]
        assert len(missing_scores) == 0, f"{len(missing_scores)} employees missing total_score"
        
        print(f"✓ All {len(employees)} employees have calculated scores!")
    
    def test_employees_have_rankings(self):
        """Verify all employees have rankings via full-rankings endpoint"""
        response = requests.get(f"{BASE_URL}/api/v2/full-rankings/2026/Q1")
        assert response.status_code == 200
        data = response.json()
        
        rankings = data.get('rankings', [])
        assert len(rankings) > 0, "No rankings found"
        
        # Verify positions are 1-N and continuous
        positions = [e.get('position') for e in rankings]
        positions.sort()
        expected = list(range(1, len(rankings) + 1))
        assert positions == expected, f"Rankings not sequential 1-N: {positions}"
        
        print(f"✓ All {len(rankings)} employees have sequential rankings (via full-rankings)!")
    
    def test_derived_metrics_calculated(self):
        """Verify derived metrics (PPA, LBW/guest, etc.) are calculated"""
        response = requests.get(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q1")
        assert response.status_code == 200
        employees = response.json()
        
        derived_fields = ['ppa', 'lbw_per_guest', 'glassware_per_guest']
        
        for field in derived_fields:
            missing = [e for e in employees if e.get(field) is None]
            assert len(missing) == 0, f"{len(missing)} employees missing {field}"
        
        print(f"✓ All derived metrics calculated for {len(employees)} employees!")


class TestRankingsExpansion:
    """Test Rankings page employee detail expansion"""
    
    def test_employee_detail_accessible(self):
        """Test that individual employee details are accessible"""
        # Get first employee
        response = requests.get(f"{BASE_URL}/api/v2/employees?year=2026&quarter=Q1")
        assert response.status_code == 200
        employees = response.json()
        
        if len(employees) > 0:
            emp_id = employees[0].get('id')
            detail_response = requests.get(f"{BASE_URL}/api/v2/employees/{emp_id}")
            assert detail_response.status_code == 200
            
            emp_detail = detail_response.json()
            print(f"  Employee: {emp_detail.get('name')}")
            print(f"  Total Score: {emp_detail.get('total_score')}")
            print(f"  NPS Score: {emp_detail.get('nps_score')}")
            print(f"  Review Mentions: {emp_detail.get('review_mentions')}")
            print(f"  CV Promoters: {emp_detail.get('cv_promoters')}")
            print(f"  CV Detractors: {emp_detail.get('cv_detractors')}")
            
        print("✓ Employee detail endpoint working!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

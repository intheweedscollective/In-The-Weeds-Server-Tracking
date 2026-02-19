"""
Yodeck Slides API Tests - All 6 slide endpoints
Tests for the slide generators in yodeck_slides.py
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://loyalty-voice-sync.preview.emergentagent.com').rstrip('/')


class TestYodeckSlidesAPI:
    """Test all 6 Yodeck slide endpoints"""
    
    def test_top10_slide_returns_png(self):
        """Test Top 10 By Metric slide endpoint returns PNG"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/top10")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers.get('content-type') == 'image/png', "Expected PNG content type"
        # Verify it's a valid PNG by checking magic bytes
        assert response.content[:8] == b'\x89PNG\r\n\x1a\n', "Invalid PNG magic bytes"
        print(f"✓ Top 10 slide: {len(response.content)} bytes")
    
    def test_complete_rankings_slide_returns_png(self):
        """Test Complete Rankings slide endpoint returns PNG"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/complete-rankings")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers.get('content-type') == 'image/png', "Expected PNG content type"
        assert response.content[:8] == b'\x89PNG\r\n\x1a\n', "Invalid PNG magic bytes"
        print(f"✓ Complete Rankings slide: {len(response.content)} bytes")
    
    def test_most_improved_slide_returns_png(self):
        """Test Most Improved slide endpoint returns PNG"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/most-improved")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers.get('content-type') == 'image/png', "Expected PNG content type"
        assert response.content[:8] == b'\x89PNG\r\n\x1a\n', "Invalid PNG magic bytes"
        print(f"✓ Most Improved slide: {len(response.content)} bytes")
    
    def test_promotion_watchlist_slide_returns_png(self):
        """Test Promotion Watchlist slide endpoint returns PNG"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/promotion-watchlist")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers.get('content-type') == 'image/png', "Expected PNG content type"
        assert response.content[:8] == b'\x89PNG\r\n\x1a\n', "Invalid PNG magic bytes"
        print(f"✓ Promotion Watchlist slide: {len(response.content)} bytes")
    
    def test_at_risk_slide_returns_png(self):
        """Test At-Risk slide endpoint returns PNG"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/at-risk")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers.get('content-type') == 'image/png', "Expected PNG content type"
        assert response.content[:8] == b'\x89PNG\r\n\x1a\n', "Invalid PNG magic bytes"
        print(f"✓ At-Risk slide: {len(response.content)} bytes")
    
    def test_printable_rankings_slide_returns_png(self):
        """Test Printable Rankings slide endpoint returns PNG"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/printable-rankings")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers.get('content-type') == 'image/png', "Expected PNG content type"
        assert response.content[:8] == b'\x89PNG\r\n\x1a\n', "Invalid PNG magic bytes"
        print(f"✓ Printable Rankings slide: {len(response.content)} bytes")


class TestSlideManifest:
    """Test slide manifest endpoint"""
    
    def test_all_slides_manifest(self):
        """Test /all endpoint returns valid manifest with all slide info"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/all")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert 'slides' in data, "Missing 'slides' in response"
        assert 'total_employees' in data, "Missing 'total_employees' in response"
        assert 'tier_counts' in data, "Missing 'tier_counts' in response"
        
        # Verify expected slide IDs are present
        slide_ids = [s['id'] for s in data['slides']]
        expected_ids = ['top10', 'complete-rankings', 'most-improved', 'promotion-watchlist', 'at-risk', 'printable-rankings']
        for expected_id in expected_ids:
            assert expected_id in slide_ids, f"Missing slide ID: {expected_id}"
        
        print(f"✓ Manifest contains {len(data['slides'])} slides, {data['total_employees']} employees")


class TestTop10SlideWithFormats:
    """Test Top 10 slide with different format options"""
    
    def test_top10_with_letter_format(self):
        """Test Top 10 slide with letter (print) format"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/top10?format=letter")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers.get('content-type') == 'image/png', "Expected PNG content type"
        # Letter format should be larger (2550x3300 vs 1920x1080)
        assert len(response.content) > 50000, "Letter format should produce larger image"
        print(f"✓ Top 10 letter format: {len(response.content)} bytes")
    
    def test_top10_with_16x9_format(self):
        """Test Top 10 slide with explicit 16:9 format"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/top10?format=16:9")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers.get('content-type') == 'image/png', "Expected PNG content type"
        print(f"✓ Top 10 16:9 format: {len(response.content)} bytes")


class TestCompleteRankingsWithBackgrounds:
    """Test Complete Rankings slide with background options"""
    
    def test_complete_rankings_dark_background(self):
        """Test Complete Rankings with dark background"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/complete-rankings?background=dark")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers.get('content-type') == 'image/png'
        print(f"✓ Complete Rankings (dark): {len(response.content)} bytes")
    
    def test_complete_rankings_with_letter_format(self):
        """Test Complete Rankings with letter format"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/complete-rankings?format=letter")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ Complete Rankings (letter): {len(response.content)} bytes")


class TestSlideDownloadHeaders:
    """Test that slides have proper download headers"""
    
    def test_top10_has_content_disposition(self):
        """Test Top 10 slide has Content-Disposition header for download"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/top10")
        assert response.status_code == 200
        content_disp = response.headers.get('content-disposition', '')
        assert 'attachment' in content_disp, "Missing 'attachment' in Content-Disposition"
        assert 'filename=' in content_disp, "Missing 'filename=' in Content-Disposition"
        print(f"✓ Content-Disposition: {content_disp}")
    
    def test_promotion_watchlist_has_content_disposition(self):
        """Test Promotion Watchlist slide has Content-Disposition header"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/promotion-watchlist")
        assert response.status_code == 200
        content_disp = response.headers.get('content-disposition', '')
        assert 'attachment' in content_disp, "Missing 'attachment' in Content-Disposition"
        print(f"✓ Promotion Watchlist Content-Disposition: {content_disp}")


class TestErrorHandling:
    """Test error handling for invalid requests"""
    
    def test_invalid_quarter_returns_404(self):
        """Test that invalid quarter returns 404"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2030/Q9/top10")
        # Should return 404 if no data exists for that quarter
        assert response.status_code in [404, 400], f"Expected 404 or 400, got {response.status_code}"
        print(f"✓ Invalid quarter returns {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

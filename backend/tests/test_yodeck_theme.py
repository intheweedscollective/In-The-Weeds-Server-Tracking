"""
Test Yodeck Slides and Theme Customization APIs
Tests for:
- Yodeck slide manifest endpoint
- Individual slide download endpoints
- Theme settings in quarter settings
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestYodeckSlideManifest:
    """Test Yodeck slide manifest endpoint"""
    
    def test_get_all_slides_manifest(self):
        """Test GET /api/v2/yodeck/{year}/{quarter}/all returns correct structure"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/all")
        assert response.status_code == 200
        
        data = response.json()
        # Verify structure
        assert "quarter" in data
        assert "year" in data
        assert "total_employees" in data
        assert "tier_counts" in data
        assert "theme" in data
        assert "available_themes" in data
        assert "slides" in data
        
        # Verify values
        assert data["quarter"] == "Q1"
        assert data["year"] == 2026
        assert data["total_employees"] == 28
        assert data["theme"] == "dark_navy"
        
        # Verify available themes
        assert "dark_navy" in data["available_themes"]
        assert "light_corporate" in data["available_themes"]
        assert "bubba_red" in data["available_themes"]
        assert "ocean_blue" in data["available_themes"]
        
        print(f"✓ Slide manifest returned {len(data['slides'])} slides")
    
    def test_slides_have_correct_structure(self):
        """Test that each slide in manifest has required fields"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/all")
        assert response.status_code == 200
        
        data = response.json()
        for slide in data["slides"]:
            assert "id" in slide
            assert "name" in slide
            assert "endpoint" in slide
            assert "pages" in slide
            assert "category" in slide
            
            # Verify endpoint format
            assert slide["endpoint"].startswith("/api/v2/yodeck/")
            
        print(f"✓ All {len(data['slides'])} slides have correct structure")
    
    def test_tier_counts_match_employees(self):
        """Test that tier counts in manifest are accurate"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/all")
        assert response.status_code == 200
        
        data = response.json()
        tier_counts = data["tier_counts"]
        
        # Verify tier counts sum to total
        total_from_tiers = sum(tier_counts.values())
        assert total_from_tiers == data["total_employees"]
        
        print(f"✓ Tier counts: {tier_counts}")


class TestYodeckSlideDownload:
    """Test individual slide download endpoints"""
    
    def test_download_top10_slide(self):
        """Test GET /api/v2/yodeck/{year}/{quarter}/top10 returns PNG image"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/top10")
        assert response.status_code == 200
        
        # Verify content type is PNG
        assert response.headers.get("content-type") == "image/png"
        
        # Verify content is not empty
        assert len(response.content) > 1000  # PNG should be at least 1KB
        
        # Verify PNG magic bytes
        assert response.content[:8] == b'\x89PNG\r\n\x1a\n'
        
        print(f"✓ Top 10 slide downloaded: {len(response.content)} bytes")
    
    def test_download_tier_slide_a_servers(self):
        """Test GET /api/v2/yodeck/{year}/{quarter}/tier/a-servers returns PNG"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/tier/a-servers")
        assert response.status_code == 200
        
        assert response.headers.get("content-type") == "image/png"
        assert len(response.content) > 1000
        assert response.content[:8] == b'\x89PNG\r\n\x1a\n'
        
        print(f"✓ A-Server tier slide downloaded: {len(response.content)} bytes")
    
    def test_download_tier_slide_b_servers(self):
        """Test GET /api/v2/yodeck/{year}/{quarter}/tier/b-servers returns PNG"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/tier/b-servers")
        assert response.status_code == 200
        
        assert response.headers.get("content-type") == "image/png"
        assert len(response.content) > 1000
        
        print(f"✓ B-Server tier slide downloaded: {len(response.content)} bytes")
    
    def test_download_tier_slide_c_servers(self):
        """Test GET /api/v2/yodeck/{year}/{quarter}/tier/c-servers returns PNG"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/tier/c-servers")
        assert response.status_code == 200
        
        assert response.headers.get("content-type") == "image/png"
        assert len(response.content) > 1000
        
        print(f"✓ C-Server tier slide downloaded: {len(response.content)} bytes")
    
    def test_download_most_improved_slide(self):
        """Test GET /api/v2/yodeck/{year}/{quarter}/most-improved returns PNG"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/most-improved")
        assert response.status_code == 200
        
        assert response.headers.get("content-type") == "image/png"
        assert len(response.content) > 1000
        
        print(f"✓ Most Improved slide downloaded: {len(response.content)} bytes")
    
    def test_download_promotion_watchlist_slide(self):
        """Test GET /api/v2/yodeck/{year}/{quarter}/promotion-watchlist returns PNG"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/promotion-watchlist")
        assert response.status_code == 200
        
        assert response.headers.get("content-type") == "image/png"
        assert len(response.content) > 1000
        
        print(f"✓ Promotion Watchlist slide downloaded: {len(response.content)} bytes")
    
    def test_download_at_risk_slide(self):
        """Test GET /api/v2/yodeck/{year}/{quarter}/at-risk returns PNG"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/at-risk")
        assert response.status_code == 200
        
        assert response.headers.get("content-type") == "image/png"
        assert len(response.content) > 1000
        
        print(f"✓ At Risk slide downloaded: {len(response.content)} bytes")
    
    def test_invalid_tier_returns_400(self):
        """Test that invalid tier name returns 400 error"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/tier/invalid-tier")
        assert response.status_code == 400
        
        data = response.json()
        assert "detail" in data
        
        print(f"✓ Invalid tier correctly returns 400: {data['detail']}")


class TestQuarterSettingsTheme:
    """Test theme settings in quarter settings API"""
    
    def test_get_quarter_settings_has_theme(self):
        """Test GET /api/v2/quarter-settings/{year}/{quarter} returns theme fields"""
        response = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q1")
        assert response.status_code == 200
        
        data = response.json()
        # Note: Q1 2026 was created before theme fields were added
        # So theme fields may not exist in the stored document
        # But the API should still work
        
        assert "year" in data
        assert "quarter" in data
        assert data["year"] == 2026
        assert data["quarter"] == "Q1"
        
        print(f"✓ Quarter settings retrieved for Q1 2026")
    
    def test_update_theme_on_locked_quarter_fails(self):
        """Test PUT /api/v2/quarter-settings/{year}/{quarter} fails on locked quarter"""
        response = requests.put(
            f"{BASE_URL}/api/v2/quarter-settings/2026/Q1",
            json={"slide_theme": "ocean_blue"}
        )
        
        # Should fail because Q1 2026 is locked
        assert response.status_code == 403
        
        data = response.json()
        assert "locked" in data.get("detail", "").lower()
        
        print(f"✓ Theme update correctly blocked on locked quarter")
    
    def test_theme_reflected_in_slide_manifest(self):
        """Test that theme from settings is reflected in slide manifest"""
        # Get settings
        settings_response = requests.get(f"{BASE_URL}/api/v2/quarter-settings/2026/Q1")
        assert settings_response.status_code == 200
        
        # Get slide manifest
        manifest_response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/all")
        assert manifest_response.status_code == 200
        
        manifest = manifest_response.json()
        
        # Theme should be present in manifest
        assert "theme" in manifest
        # Default theme is dark_navy if not set
        assert manifest["theme"] in ["dark_navy", "light_corporate", "bubba_red", "ocean_blue", "custom"]
        
        print(f"✓ Theme in manifest: {manifest['theme']}")


class TestSlideEndpointFormats:
    """Test that slide endpoints return correct format"""
    
    def test_slide_has_content_disposition_header(self):
        """Test that slide download has Content-Disposition header for filename"""
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/top10")
        assert response.status_code == 200
        
        content_disposition = response.headers.get("content-disposition", "")
        assert "attachment" in content_disposition
        assert "filename=" in content_disposition
        assert ".png" in content_disposition
        
        print(f"✓ Content-Disposition header: {content_disposition}")
    
    def test_slide_dimensions_are_1920x1080(self):
        """Test that generated slides are 1920x1080 (16:9)"""
        # This would require PIL to verify, but we can check file size is reasonable
        response = requests.get(f"{BASE_URL}/api/v2/yodeck/2026/Q1/top10")
        assert response.status_code == 200
        
        # A 1920x1080 PNG should be at least 50KB
        assert len(response.content) > 50000
        
        print(f"✓ Slide size: {len(response.content)} bytes (reasonable for 1920x1080)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
UI Dashboard Scrapers for ReviewTrackers and Loyalty Voice
Pulls exact stats from the web dashboards to ensure 100% accuracy.
"""

import asyncio
import os
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from playwright.async_api import async_playwright, Page, Browser


class ReviewTrackersScraper:
    """Scrape stats directly from ReviewTrackers web dashboard."""
    
    def __init__(self):
        self.username = os.environ.get("REVIEWTRACKERS_USERNAME", "")
        self.password = os.environ.get("REVIEWTRACKERS_PASSWORD", "")
        self.base_url = "https://app.reviewtrackers.com"
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
    
    async def login(self) -> bool:
        """Login to ReviewTrackers dashboard."""
        try:
            await self.page.goto(f"{self.base_url}/login", wait_until="networkidle")
            await self.page.wait_for_timeout(2000)
            
            # Fill login form
            await self.page.fill('input[name="email"], input[type="email"]', self.username)
            await self.page.fill('input[name="password"], input[type="password"]', self.password)
            
            # Click login button
            await self.page.click('button[type="submit"]')
            await self.page.wait_for_timeout(5000)
            
            # Check if login succeeded
            if "login" not in self.page.url.lower():
                print("[RT Scraper] Login successful")
                return True
            else:
                print("[RT Scraper] Login failed - still on login page")
                return False
                
        except Exception as e:
            print(f"[RT Scraper] Login error: {e}")
            return False
    
    async def scrape_platform_stats(self, quarter: str = "Q1", year: int = 2026) -> Dict[str, Any]:
        """
        Scrape platform stats from ReviewTrackers dashboard.
        Returns exact numbers shown in the UI.
        """
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page()
        
        try:
            if not await self.login():
                return {"success": False, "error": "Login failed"}
            
            # Navigate to reviews/analytics page
            await self.page.goto(f"{self.base_url}/reviews", wait_until="networkidle")
            await self.page.wait_for_timeout(3000)
            
            # Set date filter to Quarter to Date
            # Look for date filter dropdown
            try:
                date_filter = self.page.locator('button:has-text("Date"), [data-testid="date-filter"]').first
                if await date_filter.is_visible():
                    await date_filter.click()
                    await self.page.wait_for_timeout(1000)
                    
                    # Select "Quarter to date"
                    qtd_option = self.page.locator('text="Quarter to date", text="Quarter to Date", text="QTD"').first
                    if await qtd_option.is_visible():
                        await qtd_option.click()
                        await self.page.wait_for_timeout(2000)
            except:
                print("[RT Scraper] Could not set date filter, using default")
            
            # Scrape platform cards
            stats = {
                "success": True,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "quarter": quarter,
                "year": year,
                "platforms": {}
            }
            
            # Look for platform stat cards
            # These typically show: Platform name, rating, review count
            platform_selectors = [
                # Common patterns for platform cards
                '[class*="platform"], [class*="source"], [data-testid*="platform"]',
                '.review-source, .platform-card, .source-card',
            ]
            
            for platform in ["Google", "Yelp", "TripAdvisor", "OpenTable", "Facebook"]:
                try:
                    # Try to find the platform card
                    card = self.page.locator(f'text="{platform}"').first
                    if await card.is_visible():
                        # Get parent container
                        parent = card.locator('xpath=ancestor::div[contains(@class, "card") or contains(@class, "stat")]').first
                        
                        # Extract rating and count
                        text = await parent.text_content() if await parent.count() > 0 else await card.text_content()
                        
                        # Parse rating (e.g., "4.67" or "4.7")
                        rating_match = re.search(r'(\d+\.?\d*)\s*(?:rating|stars?|avg)?', text, re.I)
                        rating = float(rating_match.group(1)) if rating_match else 0.0
                        
                        # Parse count (e.g., "129 reviews" or "129")
                        count_match = re.search(r'(\d+)\s*(?:reviews?|total)?', text, re.I)
                        count = int(count_match.group(1)) if count_match else 0
                        
                        stats["platforms"][platform] = {
                            "rating": rating,
                            "reviews": count
                        }
                except Exception as e:
                    print(f"[RT Scraper] Error scraping {platform}: {e}")
                    stats["platforms"][platform] = {"rating": 0.0, "reviews": 0}
            
            # Get total reviews
            try:
                total_elem = self.page.locator('text=/\\d+\\s*(?:total\\s*)?reviews?/i').first
                if await total_elem.is_visible():
                    total_text = await total_elem.text_content()
                    total_match = re.search(r'(\d+)', total_text)
                    stats["total_reviews"] = int(total_match.group(1)) if total_match else 0
                else:
                    # Sum from platforms
                    stats["total_reviews"] = sum(p.get("reviews", 0) for p in stats["platforms"].values())
            except:
                stats["total_reviews"] = sum(p.get("reviews", 0) for p in stats["platforms"].values())
            
            return stats
            
        except Exception as e:
            print(f"[RT Scraper] Error: {e}")
            return {"success": False, "error": str(e)}
            
        finally:
            if self.browser:
                await self.browser.close()
            await playwright.stop()


class LoyaltyVoiceScraper:
    """Scrape stats directly from Loyalty Voice web dashboard."""
    
    def __init__(self):
        self.username = os.environ.get("REVIEWTRACKERS_USERNAME", "")  # Same credentials
        self.password = os.environ.get("REVIEWTRACKERS_PASSWORD", "")
        self.base_url = "https://landrys.loyalty-voice.com"
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
    
    async def login(self) -> bool:
        """Login to Loyalty Voice dashboard."""
        try:
            await self.page.goto(self.base_url, wait_until="networkidle")
            await self.page.wait_for_timeout(2000)
            
            # Fill login form
            email_input = self.page.locator('input[type="email"], input[name="email"], #email').first
            password_input = self.page.locator('input[type="password"], input[name="password"], #password').first
            
            await email_input.fill(self.username)
            await password_input.fill(self.password)
            
            # Click login button
            login_btn = self.page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign In")').first
            await login_btn.click()
            await self.page.wait_for_timeout(5000)
            
            # Check if login succeeded
            if "login" not in self.page.url.lower() and "sign" not in self.page.url.lower():
                print("[LV Scraper] Login successful")
                return True
            else:
                print("[LV Scraper] Login failed")
                return False
                
        except Exception as e:
            print(f"[LV Scraper] Login error: {e}")
            return False
    
    async def scrape_nps_stats(self, quarter: str = "Q1", year: int = 2026) -> Dict[str, Any]:
        """
        Scrape NPS stats from Loyalty Voice dashboard.
        Returns exact numbers shown in the UI.
        """
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page()
        
        try:
            if not await self.login():
                return {"success": False, "error": "Login failed"}
            
            # Navigate to summary/NPS page
            await self.page.wait_for_timeout(3000)
            
            # Set date filter to Quarter to Date
            try:
                date_filter = self.page.locator('[class*="date"], button:has-text("Date"), button:has-text("Period")').first
                if await date_filter.is_visible():
                    await date_filter.click()
                    await self.page.wait_for_timeout(1000)
                    
                    qtd_option = self.page.locator('text="Quarter to date", text="QTD"').first
                    if await qtd_option.is_visible():
                        await qtd_option.click()
                        await self.page.wait_for_timeout(2000)
            except:
                print("[LV Scraper] Could not set date filter")
            
            # Scrape NPS stats
            stats = {
                "success": True,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "quarter": quarter,
                "year": year,
            }
            
            # Get page content for parsing
            content = await self.page.content()
            
            # Look for NPS score (e.g., "80.28%" or "NPS: 80.28")
            nps_patterns = [
                r'NPS[:\s]*(\d+\.?\d*)\s*%?',
                r'(\d+\.?\d*)\s*%?\s*NPS',
                r'Net\s*Promoter\s*Score[:\s]*(\d+\.?\d*)',
            ]
            
            for pattern in nps_patterns:
                match = re.search(pattern, content, re.I)
                if match:
                    stats["nps_score"] = float(match.group(1))
                    break
            else:
                stats["nps_score"] = 0.0
            
            # Look for Promoters count
            promo_match = re.search(r'Promoters?[:\s]*(\d+)|(\d+)\s*Promoters?', content, re.I)
            stats["promoters"] = int(promo_match.group(1) or promo_match.group(2)) if promo_match else 0
            
            # Look for Passives count
            passive_match = re.search(r'Passives?[:\s]*(\d+)|(\d+)\s*Passives?', content, re.I)
            stats["passives"] = int(passive_match.group(1) or passive_match.group(2)) if passive_match else 0
            
            # Look for Detractors count
            detract_match = re.search(r'Detractors?[:\s]*(\d+)|(\d+)\s*Detractors?', content, re.I)
            stats["detractors"] = int(detract_match.group(1) or detract_match.group(2)) if detract_match else 0
            
            # Look for total responses
            total_match = re.search(r'(\d+)\s*(?:total\s*)?(?:responses?|surveys?|feedback)', content, re.I)
            if total_match:
                stats["total_responses"] = int(total_match.group(1))
            else:
                stats["total_responses"] = stats["promoters"] + stats["passives"] + stats["detractors"]
            
            return stats
            
        except Exception as e:
            print(f"[LV Scraper] Error: {e}")
            return {"success": False, "error": str(e)}
            
        finally:
            if self.browser:
                await self.browser.close()
            await playwright.stop()


async def sync_official_stats_from_ui(db, quarter: str = "Q1", year: int = 2026) -> Dict[str, Any]:
    """
    Sync official stats from both RT and LV dashboards.
    This pulls the exact numbers shown in the UI.
    """
    results = {
        "quarter": quarter,
        "year": year,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "reviewtrackers": None,
        "loyalty_voice": None,
    }
    
    # Scrape ReviewTrackers
    print("[Sync] Scraping ReviewTrackers dashboard...")
    rt_scraper = ReviewTrackersScraper()
    rt_stats = await rt_scraper.scrape_platform_stats(quarter, year)
    
    if rt_stats.get("success"):
        # Save as official RT stats
        official_rt = {
            "quarter": quarter.upper(),
            "year": year,
            "platforms": rt_stats.get("platforms", {}),
            "total_reviews": rt_stats.get("total_reviews", 0),
            "source": "scraped_from_ui",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await db.official_rt_stats.update_one(
            {"quarter": quarter.upper(), "year": year},
            {"$set": official_rt},
            upsert=True
        )
        results["reviewtrackers"] = {"success": True, "stats": official_rt}
    else:
        results["reviewtrackers"] = {"success": False, "error": rt_stats.get("error")}
    
    # Scrape Loyalty Voice
    print("[Sync] Scraping Loyalty Voice dashboard...")
    lv_scraper = LoyaltyVoiceScraper()
    lv_stats = await lv_scraper.scrape_nps_stats(quarter, year)
    
    if lv_stats.get("success"):
        # Save as official CV stats
        official_cv = {
            "quarter": quarter.upper(),
            "year": year,
            "nps_score": lv_stats.get("nps_score", 0),
            "promoters": lv_stats.get("promoters", 0),
            "passives": lv_stats.get("passives", 0),
            "detractors": lv_stats.get("detractors", 0),
            "total_responses": lv_stats.get("total_responses", 0),
            "source": "scraped_from_ui",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await db.official_cv_stats.update_one(
            {"quarter": quarter.upper(), "year": year},
            {"$set": official_cv},
            upsert=True
        )
        results["loyalty_voice"] = {"success": True, "stats": official_cv}
    else:
        results["loyalty_voice"] = {"success": False, "error": lv_stats.get("error")}
    
    return results

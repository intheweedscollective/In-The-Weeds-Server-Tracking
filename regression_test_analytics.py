#!/usr/bin/env python3
"""
Regression test for Analytics PDF export endpoint
Specific test for the review request requirements:
1) GET /api/analytics/pdf should return application/pdf and non-empty file
2) Parse with pypdf and ensure at least 1 page  
3) Extract text and confirm it includes 'Performance Analytics Report' and columns including 'Above Bench'
4) Quick check generate-review still works (Q4 2025) and returns pdf_base64
"""

import requests
import io
import base64
from pypdf import PdfReader
import sys

def test_analytics_pdf_endpoint():
    """Test the Analytics PDF endpoint according to review request requirements"""
    print("🔍 Testing Analytics PDF Export Endpoint...")
    
    base_url = "https://employee-pulse-36.preview.emergentagent.com"
    api_url = f"{base_url}/api"
    
    try:
        # 1) GET /api/analytics/pdf should return application/pdf and non-empty file
        response = requests.get(f"{api_url}/analytics/pdf", timeout=30)
        
        if response.status_code != 200:
            print(f"❌ FAILED: Status code {response.status_code}, expected 200")
            return False
        
        # Check content type
        content_type = response.headers.get('content-type', '')
        if content_type != 'application/pdf':
            print(f"❌ FAILED: Content-Type '{content_type}', expected 'application/pdf'")
            return False
        
        # Check non-empty file
        pdf_content = response.content
        if len(pdf_content) == 0:
            print(f"❌ FAILED: PDF file is empty")
            return False
        
        print(f"✅ Requirement 1: Returns application/pdf, size: {len(pdf_content)} bytes")
        
        # 2) Parse with pypdf and ensure at least 1 page
        try:
            pdf_reader = PdfReader(io.BytesIO(pdf_content))
            page_count = len(pdf_reader.pages)
            
            if page_count < 1:
                print(f"❌ FAILED: PDF has {page_count} pages, expected at least 1")
                return False
            
            print(f"✅ Requirement 2: PDF parsed successfully, {page_count} page(s)")
            
            # 3) Extract text and confirm it includes 'Performance Analytics Report' and 'Above Bench'
            full_text = ""
            for page in pdf_reader.pages:
                full_text += page.extract_text()
            
            has_performance_analytics = 'Performance Analytics Report' in full_text
            has_above_bench = 'Above Bench' in full_text
            
            if not has_performance_analytics:
                print(f"❌ FAILED: PDF text does not contain 'Performance Analytics Report'")
                return False
            
            if not has_above_bench:
                print(f"❌ FAILED: PDF text does not contain 'Above Bench' column")
                return False
            
            print(f"✅ Requirement 3: PDF contains 'Performance Analytics Report' and 'Above Bench' column")
            
        except Exception as pdf_error:
            print(f"❌ FAILED: PDF parsing error: {str(pdf_error)}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ FAILED: Request error: {str(e)}")
        return False

def test_generate_review_q4_2025():
    """Test generate-review still works for Q4 2025 and returns pdf_base64"""
    print("\n🔍 Testing Generate Review Q4 2025 Regression...")
    
    base_url = "https://employee-pulse-36.preview.emergentagent.com"
    api_url = f"{base_url}/api"
    
    try:
        # First get an employee to test with
        response = requests.get(f"{api_url}/employees", timeout=10)
        if response.status_code != 200:
            print(f"❌ FAILED: Could not get employees, status: {response.status_code}")
            return False
        
        employees = response.json()
        if not employees:
            print(f"❌ FAILED: No employees found in database")
            return False
        
        test_employee = employees[0]
        employee_id = test_employee['id']
        employee_name = test_employee['name']
        
        print(f"📋 Testing with employee: {employee_name} (ID: {employee_id})")
        
        # Test generate review for Q4 2025
        payload = {
            "quarter": "Q4",
            "year": 2025
        }
        
        response = requests.post(
            f"{api_url}/employees/{employee_id}/generate-review", 
            json=payload, 
            timeout=60
        )
        
        if response.status_code != 200:
            print(f"❌ FAILED: Status code {response.status_code}, expected 200")
            return False
        
        data = response.json()
        
        # Check success field
        if not data.get('success', False):
            print(f"❌ FAILED: Response success is False")
            return False
        
        # Check pdf_base64 field exists and is not None
        if 'pdf_base64' not in data or data['pdf_base64'] is None:
            print(f"❌ FAILED: pdf_base64 field missing or None")
            return False
        
        # Validate the PDF can be decoded and read
        try:
            pdf_bytes = base64.b64decode(data['pdf_base64'])
            pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
            page_count = len(pdf_reader.pages)
            
            if page_count < 1:
                print(f"❌ FAILED: Generated PDF has {page_count} pages, expected at least 1")
                return False
            
            print(f"✅ Requirement 4: Generate-review works for Q4 2025, returns valid pdf_base64 ({page_count} pages)")
            
        except Exception as pdf_error:
            print(f"❌ FAILED: PDF validation error: {str(pdf_error)}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ FAILED: Request error: {str(e)}")
        return False

def main():
    """Run all regression tests"""
    print("🚀 Analytics PDF Export Regression Tests")
    print("=" * 50)
    
    test1_passed = test_analytics_pdf_endpoint()
    test2_passed = test_generate_review_q4_2025()
    
    print("\n" + "=" * 50)
    print("📊 Regression Test Results:")
    print(f"Analytics PDF Export: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"Generate Review Q4 2025: {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    
    if test1_passed and test2_passed:
        print("\n🎉 All regression tests PASSED!")
        return 0
    else:
        print("\n⚠️ Some regression tests FAILED!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
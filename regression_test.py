#!/usr/bin/env python3
"""
Quick regression test for generate-review functionality after PDF styling changes.
Tests the specific steps requested in the review request.
"""

import requests
import base64
import io
from pypdf import PdfReader
import sys

def test_generate_review_regression():
    """
    Regression test for generate-review functionality.
    Steps:
    1) GET /api/employees (pick first employee id)
    2) POST /api/employees/{id}/generate-review with quarter Q4 year 2025
    3) Confirm success true and pdf_base64 present
    4) Decode pdf_base64 and confirm it is readable by pypdf and has at least 1 page
    """
    
    base_url = "https://staff-score-engine.preview.emergentagent.com"
    api_url = f"{base_url}/api"
    
    print("🔍 Starting generate-review regression test...")
    print("=" * 50)
    
    try:
        # Step 1: GET /api/employees (pick first employee id)
        print("Step 1: Getting employees list...")
        response = requests.get(f"{api_url}/employees", timeout=10)
        
        if response.status_code != 200:
            print(f"❌ Failed to get employees. Status: {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return False
        
        employees = response.json()
        if not employees:
            print("❌ No employees found in database")
            return False
        
        first_employee = employees[0]
        employee_id = first_employee['id']
        employee_name = first_employee['name']
        
        print(f"✅ Found {len(employees)} employees")
        print(f"   Using first employee: {employee_name} (ID: {employee_id})")
        
        # Step 2: POST /api/employees/{id}/generate-review with quarter Q4 year 2025
        print("\nStep 2: Generating review for Q4 2025...")
        payload = {
            "quarter": "Q4",
            "year": 2025
        }
        
        response = requests.post(
            f"{api_url}/employees/{employee_id}/generate-review",
            json=payload,
            timeout=60  # AI generation can take time
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to generate review. Status: {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return False
        
        review_data = response.json()
        print(f"✅ Review generation API call successful")
        
        # Step 3: Confirm success true and pdf_base64 present
        print("\nStep 3: Validating response structure...")
        
        success = review_data.get('success', False)
        if not success:
            print(f"❌ Review generation failed. Success: {success}")
            print(f"Message: {review_data.get('message', 'No message')}")
            return False
        
        pdf_base64 = review_data.get('pdf_base64')
        if not pdf_base64:
            print("❌ No pdf_base64 field in response")
            return False
        
        print(f"✅ Success: {success}")
        print(f"✅ PDF base64 present: {len(pdf_base64)} characters")
        print(f"   Review ID: {review_data.get('review_id', 'N/A')}")
        print(f"   Message: {review_data.get('message', 'N/A')}")
        
        # Step 4: Decode pdf_base64 and confirm it is readable by pypdf and has at least 1 page
        print("\nStep 4: Validating PDF content...")
        
        try:
            pdf_bytes = base64.b64decode(pdf_base64)
            print(f"✅ PDF decoded successfully: {len(pdf_bytes)} bytes")
            
            # Test with pypdf
            pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
            page_count = len(pdf_reader.pages)
            
            if page_count < 1:
                print(f"❌ PDF has no pages. Page count: {page_count}")
                return False
            
            print(f"✅ PDF is readable by pypdf: {page_count} page(s)")
            
            # Additional validation: try to extract some text from first page
            try:
                first_page_text = pdf_reader.pages[0].extract_text()
                if "BUBBA GUMP" in first_page_text or "QUARTERLY PERFORMANCE REVIEW" in first_page_text:
                    print("✅ PDF contains expected review content")
                else:
                    print("⚠️  PDF content may not match expected format")
                    print(f"   First 100 chars: {first_page_text[:100]}")
            except Exception as text_error:
                print(f"⚠️  Could not extract text from PDF: {text_error}")
            
        except Exception as pdf_error:
            print(f"❌ Failed to decode or read PDF: {pdf_error}")
            return False
        
        print("\n🎉 All regression test steps completed successfully!")
        print("=" * 50)
        print("SUMMARY:")
        print(f"  Employee: {employee_name}")
        print(f"  Quarter: Q4 2025")
        print(f"  Success: {success}")
        print(f"  PDF Pages: {page_count}")
        print(f"  PDF Size: {len(pdf_bytes)} bytes")
        
        return True
        
    except Exception as e:
        print(f"❌ Regression test failed with exception: {e}")
        return False

def main():
    """Main function to run the regression test"""
    success = test_generate_review_regression()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
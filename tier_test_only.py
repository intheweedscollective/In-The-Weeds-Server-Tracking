#!/usr/bin/env python3

import requests
import json
import io
import pandas as pd
import base64
from pypdf import PdfReader

def test_per_metric_tier_mapping():
    """Test per-metric Tier mapping behavior with exact tier headers from user request"""
    base_url = "https://perf-review-hub-8.preview.emergentagent.com"
    api_url = f"{base_url}/api"
    
    try:
        print("🧪 Testing Per-Metric Tier Mapping Behavior")
        print("=" * 50)
        
        # Clear existing employees first
        print("1️⃣ Clearing existing employees...")
        clear_response = requests.delete(f"{api_url}/employees", timeout=10)
        print(f"   Clear response: {clear_response.status_code}")
        
        # Create Excel with exact tier headers as specified in review request
        print("2️⃣ Creating Excel with exact tier headers...")
        sample_data = {
            'name': ['Alice Johnson'],
            'position': ['Server'],
            'ppa': [65.5],
            'gpg': [1.25],
            'pplbw': [8.5],
            'lsc_ratio': [25],  # LSC ratio as denominator (1 in 25)
            'metric_bonus_points': [7],
            'cumulative_score': [85],
            # Exact tier headers from review request (including typos)
            'PPA Tier': ['Top Performer'],
            'PPLBW Tier': ['Meets Expectations'],
            'LSC Ratio Tier': ['Above Average'],
            'GPG Tier': ['Excellent'],
            'Metirc Bonus Tier': ['Outstanding'],  # Note: typo in "Metirc"
            'Cummulative Score Tier': ['High Achiever']  # Note: typo in "Cummulative"
        }
        
        df = pd.DataFrame(sample_data)
        excel_buffer = io.BytesIO()
        df.to_excel(excel_buffer, index=False)
        excel_buffer.seek(0)
        
        print("   Excel created with columns:", list(df.columns))
        
        # 1) POST /api/upload-excel with the file
        print("3️⃣ Uploading Excel file...")
        files = {'file': ('tier_test_employees.xlsx', excel_buffer.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
        
        upload_response = requests.post(f"{api_url}/upload-excel", files=files, timeout=30)
        print(f"   Upload status: {upload_response.status_code}")
        
        if upload_response.status_code != 200:
            print(f"   ❌ Upload failed: {upload_response.text}")
            return False
        
        upload_data = upload_response.json()
        print(f"   Upload result: {upload_data}")
        
        if not upload_data.get('success', False):
            print(f"   ❌ Upload not successful: {upload_data}")
            return False
        
        # 2) GET /api/employees and verify metric_tiers populated correctly
        print("4️⃣ Getting employees and checking metric_tiers...")
        employees_response = requests.get(f"{api_url}/employees", timeout=10)
        
        if employees_response.status_code != 200:
            print(f"   ❌ Get employees failed: {employees_response.status_code}")
            return False
        
        employees = employees_response.json()
        if not employees:
            print("   ❌ No employees found after upload")
            return False
        
        employee = employees[0]  # Get the first (and only) employee
        print(f"   Employee found: {employee['name']}")
        
        additional_data = employee.get('additional_data', {})
        metric_tiers = additional_data.get('metric_tiers', {})
        
        print("5️⃣ Verifying metric_tiers mapping...")
        print(f"   📊 Returned metric_tiers: {json.dumps(metric_tiers, indent=2)}")
        
        # Verify all 6 metrics have tier mappings
        expected_tiers = {
            'ppa': 'Top Performer',
            'pplbw': 'Meets Expectations', 
            'lsc_ratio': 'Above Average',
            'gpg': 'Excellent',
            'metric_bonus_points': 'Outstanding',
            'cumulative_score': 'High Achiever'
        }
        
        print("   📋 Expected tiers:")
        for metric, expected_tier in expected_tiers.items():
            actual_tier = metric_tiers.get(metric)
            status = "✅" if actual_tier == expected_tier else "❌"
            print(f"      {metric}: expected '{expected_tier}' → got '{actual_tier}' {status}")
        
        tier_mapping_success = True
        missing_tiers = []
        incorrect_tiers = []
        
        for metric, expected_tier in expected_tiers.items():
            actual_tier = metric_tiers.get(metric)
            if actual_tier is None:
                missing_tiers.append(metric)
                tier_mapping_success = False
            elif actual_tier != expected_tier:
                incorrect_tiers.append(f"{metric}: expected '{expected_tier}', got '{actual_tier}'")
                tier_mapping_success = False
        
        if not tier_mapping_success:
            error_details = []
            if missing_tiers:
                error_details.append(f"Missing tiers: {missing_tiers}")
            if incorrect_tiers:
                error_details.append(f"Incorrect tiers: {incorrect_tiers}")
            
            print(f"   ❌ Tier mapping failed - {'; '.join(error_details)}")
            return False
        
        # 3) POST /api/employees/{id}/generate-review and confirm success + pdf_base64
        print("6️⃣ Testing review generation...")
        employee_id = employee['id']
        review_payload = {
            "quarter": "Q4",
            "year": 2024
        }
        
        review_response = requests.post(
            f"{api_url}/employees/{employee_id}/generate-review", 
            json=review_payload, 
            timeout=60
        )
        
        print(f"   Review generation status: {review_response.status_code}")
        
        if review_response.status_code != 200:
            print(f"   ❌ Review generation failed: {review_response.text}")
            return False
        
        review_data = review_response.json()
        has_success = review_data.get('success', False)
        has_pdf_base64 = 'pdf_base64' in review_data and review_data['pdf_base64'] is not None
        
        print(f"   Review success: {has_success}")
        print(f"   Has PDF base64: {has_pdf_base64}")
        
        if has_pdf_base64:
            pdf_length = len(review_data['pdf_base64'])
            print(f"   PDF base64 length: {pdf_length} characters")
        
        if not (has_success and has_pdf_base64):
            print(f"   ❌ Review generation incomplete - success: {has_success}, has_pdf: {has_pdf_base64}")
            return False
        
        print("7️⃣ All tests passed! ✅")
        print(f"   📊 Final metric_tiers result: {json.dumps(metric_tiers, indent=2)}")
        
        return True, metric_tiers
        
    except Exception as e:
        print(f"❌ Test failed with exception: {str(e)}")
        return False

if __name__ == "__main__":
    result = test_per_metric_tier_mapping()
    if isinstance(result, tuple) and result[0]:
        print("\n🎉 Per-Metric Tier Mapping Test: SUCCESS")
        print(f"📊 Metric Tiers Dict: {json.dumps(result[1], indent=2)}")
    else:
        print("\n💥 Per-Metric Tier Mapping Test: FAILED")
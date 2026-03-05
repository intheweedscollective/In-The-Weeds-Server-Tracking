#!/usr/bin/env python3
"""
Specific tests for the review request requirements:
1) GET /api/employees returns list
2) POST /api/line-graphs upload (multipart file) with params quarter/year/employee_id/graph_kind works
3) GET /api/line-graphs?employee_id=... returns uploaded item
4) POST /api/employees/{employee_id}/generate-review returns success and pdf_base64 (and if a graph exists, PDF should have 2 pages)
"""

import requests
import base64
import io
import pandas as pd
from pypdf import PdfReader

BASE_URL = "https://employee-pulse-36.preview.emergentagent.com"
API_URL = f"{BASE_URL}/api"

def test_specific_requirements():
    print("🧪 Testing Specific Review Request Requirements")
    print("=" * 60)
    
    # First, upload some test data
    print("📤 Setting up test data...")
    
    # Create sample employee data
    sample_data = {
        'name': ['Alice Johnson', 'Bob Smith'],
        'position': ['Server', 'Manager'],
        'ppa': [85.5, 92.3],
        'gpg': [1250.75, 1890.50],
        'pplbw': [4.2, 3.8],
        'lsc_ratio': [0.25, 0.22],
        'bonus_points': [15, 25],
        'total_score': [88.5, 94.2]
    }
    
    df = pd.DataFrame(sample_data)
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False)
    excel_buffer.seek(0)
    
    files = {'file': ('test_employees.xlsx', excel_buffer.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    
    upload_response = requests.post(f"{API_URL}/upload-excel", files=files, timeout=30)
    if upload_response.status_code != 200:
        print(f"❌ Failed to upload test data: {upload_response.status_code}")
        return
    
    print("✅ Test data uploaded successfully")
    
    # Test 1: GET /api/employees returns list
    print("\n1️⃣ Testing GET /api/employees...")
    employees_response = requests.get(f"{API_URL}/employees", timeout=10)
    
    if employees_response.status_code == 200:
        employees = employees_response.json()
        print(f"✅ GET /api/employees - Status: {employees_response.status_code}, Count: {len(employees)}")
        
        if len(employees) > 0:
            test_employee = employees[0]
            employee_id = test_employee['id']
            employee_name = test_employee['name']
            print(f"   Using test employee: {employee_name} (ID: {employee_id})")
        else:
            print("❌ No employees found")
            return
    else:
        print(f"❌ GET /api/employees failed - Status: {employees_response.status_code}")
        return
    
    # Test 2: POST /api/line-graphs upload
    print("\n2️⃣ Testing POST /api/line-graphs upload...")
    
    # Create a simple test PNG image
    test_png_data = base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAI9jU77zgAAAABJRU5ErkJggg=='
    )
    
    files = {'file': ('test_graph.png', test_png_data, 'image/png')}
    params = {
        'quarter': 'Q4',
        'year': 2024,
        'employee_id': employee_id,
        'graph_kind': 'quarter'
    }
    
    graph_upload_response = requests.post(f"{API_URL}/line-graphs", files=files, params=params, timeout=30)
    
    if graph_upload_response.status_code == 200:
        graph_result = graph_upload_response.json()
        if graph_result.get('success'):
            print(f"✅ POST /api/line-graphs - Status: {graph_upload_response.status_code}, Success: {graph_result.get('success')}")
            graph_id = graph_result.get('graph_id')
            print(f"   Graph ID: {graph_id}")
        else:
            print(f"❌ Line graph upload failed - Success: {graph_result.get('success')}")
            return
    else:
        print(f"❌ POST /api/line-graphs failed - Status: {graph_upload_response.status_code}")
        print(f"   Response: {graph_upload_response.text[:200]}")
        return
    
    # Test 3: GET /api/line-graphs?employee_id=...
    print("\n3️⃣ Testing GET /api/line-graphs?employee_id=...")
    
    graphs_response = requests.get(f"{API_URL}/line-graphs?employee_id={employee_id}", timeout=10)
    
    if graphs_response.status_code == 200:
        graphs = graphs_response.json()
        print(f"✅ GET /api/line-graphs?employee_id={employee_id} - Status: {graphs_response.status_code}, Count: {len(graphs)}")
        
        if len(graphs) > 0:
            graph = graphs[0]
            print(f"   Found graph: {graph.get('filename')} for {graph.get('quarter')} {graph.get('year')}")
        else:
            print("❌ No graphs found for employee")
            return
    else:
        print(f"❌ GET /api/line-graphs failed - Status: {graphs_response.status_code}")
        return
    
    # Test 4: POST /api/employees/{employee_id}/generate-review
    print("\n4️⃣ Testing POST /api/employees/{employee_id}/generate-review...")
    
    review_payload = {
        "quarter": "Q4",
        "year": 2024
    }
    
    review_response = requests.post(
        f"{API_URL}/employees/{employee_id}/generate-review", 
        json=review_payload, 
        timeout=60
    )
    
    if review_response.status_code == 200:
        review_result = review_response.json()
        success = review_result.get('success', False)
        has_pdf = 'pdf_base64' in review_result
        
        print(f"✅ POST /api/employees/{employee_id}/generate-review - Status: {review_response.status_code}")
        print(f"   Success: {success}, Has PDF: {has_pdf}")
        
        if success and has_pdf:
            # Validate PDF page count
            try:
                pdf_base64 = review_result['pdf_base64']
                pdf_bytes = base64.b64decode(pdf_base64)
                pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
                page_count = len(pdf_reader.pages)
                
                print(f"   PDF Pages: {page_count}")
                
                # Should have 2 pages when graph exists (review + graph)
                if page_count == 2:
                    print("✅ PDF has correct number of pages (2) with graph attached")
                elif page_count == 1:
                    print("⚠️  PDF has only 1 page - graph may not be attached properly")
                else:
                    print(f"❓ PDF has unexpected number of pages: {page_count}")
                    
            except Exception as pdf_error:
                print(f"❌ PDF validation failed: {str(pdf_error)}")
        else:
            print(f"❌ Review generation failed - Success: {success}, Message: {review_result.get('message', 'N/A')}")
    else:
        print(f"❌ POST /api/employees/{employee_id}/generate-review failed - Status: {review_response.status_code}")
        print(f"   Response: {review_response.text[:200]}")
    
    # Cleanup
    print("\n🧹 Cleaning up...")
    cleanup_response = requests.delete(f"{API_URL}/employees", timeout=10)
    if cleanup_response.status_code == 200:
        print("✅ Cleanup completed")
    else:
        print(f"⚠️  Cleanup failed: {cleanup_response.status_code}")
    
    print("\n" + "=" * 60)
    print("🏁 Specific requirements testing completed")

if __name__ == "__main__":
    test_specific_requirements()
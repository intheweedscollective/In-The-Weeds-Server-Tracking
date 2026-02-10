#!/usr/bin/env python3
"""
Test with a proper PNG image to see if the issue is with the minimal test image
"""

import requests
import base64
import io
from PIL import Image
import pandas as pd
from pypdf import PdfReader

BASE_URL = "https://perfreview.preview.emergentagent.com"
API_URL = f"{BASE_URL}/api"

def create_proper_test_image():
    """Create a proper test image using PIL"""
    # Create a 100x100 pixel image with some content
    img = Image.new('RGB', (100, 100), color='red')
    
    # Save to bytes
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    return img_buffer.getvalue()

def test_with_proper_image():
    print("🖼️  Testing with proper PNG image")
    print("=" * 50)
    
    # Upload test employee
    sample_data = {
        'name': ['Test Employee'],
        'position': ['Server'],
        'ppa': [85.5],
        'gpg': [1250.75],
        'pplbw': [4.2],
        'lsc_ratio': [0.25],
        'bonus_points': [15],
        'total_score': [88.5]
    }
    
    df = pd.DataFrame(sample_data)
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False)
    excel_buffer.seek(0)
    
    files = {'file': ('test_employees.xlsx', excel_buffer.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    
    upload_response = requests.post(f"{API_URL}/upload-excel", files=files, timeout=30)
    if upload_response.status_code != 200:
        print(f"❌ Failed to upload test data")
        return
    
    # Get employee
    employees_response = requests.get(f"{API_URL}/employees", timeout=10)
    employees = employees_response.json()
    employee_id = employees[0]['id']
    
    # Create proper test image
    proper_image_data = create_proper_test_image()
    
    # Upload line graph with proper image
    files = {'file': ('proper_test_graph.png', proper_image_data, 'image/png')}
    params = {
        'quarter': 'Q4',
        'year': 2024,
        'employee_id': employee_id,
        'graph_kind': 'quarter'
    }
    
    graph_response = requests.post(f"{API_URL}/line-graphs", files=files, params=params, timeout=30)
    
    if graph_response.status_code == 200:
        print("✅ Proper image uploaded successfully")
        
        # Test review generation
        review_payload = {"quarter": "Q4", "year": 2024}
        review_response = requests.post(
            f"{API_URL}/employees/{employee_id}/generate-review", 
            json=review_payload, 
            timeout=60
        )
        
        if review_response.status_code == 200:
            review_result = review_response.json()
            success = review_result.get('success', False)
            
            print(f"Review generation - Success: {success}")
            
            if success and 'pdf_base64' in review_result:
                # Check PDF pages
                pdf_bytes = base64.b64decode(review_result['pdf_base64'])
                pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
                page_count = len(pdf_reader.pages)
                print(f"✅ PDF generated with {page_count} pages")
            else:
                print(f"❌ Review failed: {review_result.get('message', 'Unknown error')}")
        else:
            print(f"❌ Review request failed: {review_response.status_code}")
    else:
        print(f"❌ Image upload failed: {graph_response.status_code}")
    
    # Cleanup
    requests.delete(f"{API_URL}/employees", timeout=10)

if __name__ == "__main__":
    test_with_proper_image()
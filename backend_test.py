import requests
import sys
import json
import io
import pandas as pd
from datetime import datetime

class BubbaGumpAPITester:
    def __init__(self, base_url="https://eatery-reports.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED")
        else:
            print(f"❌ {name} - FAILED: {details}")
        
        self.test_results.append({
            "test": name,
            "success": success,
            "details": details
        })

    def test_root_endpoint(self):
        """Test the root API endpoint"""
        try:
            response = requests.get(f"{self.api_url}/", timeout=10)
            success = response.status_code == 200 and "Bubba Gump" in response.text
            details = f"Status: {response.status_code}, Response: {response.text[:100]}"
            self.log_test("Root API Endpoint", success, details)
            return success
        except Exception as e:
            self.log_test("Root API Endpoint", False, str(e))
            return False

    def test_get_employees_empty(self):
        """Test getting employees when database is empty"""
        try:
            response = requests.get(f"{self.api_url}/employees", timeout=10)
            success = response.status_code == 200
            data = response.json() if success else []
            details = f"Status: {response.status_code}, Count: {len(data)}"
            self.log_test("Get Employees (Empty)", success, details)
            return success, data
        except Exception as e:
            self.log_test("Get Employees (Empty)", False, str(e))
            return False, []

    def test_upload_excel(self):
        """Test Excel file upload functionality"""
        try:
            # Create a sample Excel file in memory
            sample_data = {
                'name': ['John Doe', 'Jane Smith', 'Bob Johnson'],
                'position': ['Server', 'Manager', 'Cook'],
                'ppa': [85.5, 92.3, 78.9],
                'gpg': [1250.75, 1890.50, 1100.25],
                'pplbw': [4.2, 3.8, 4.5],
                'lsc_ratio': [0.25, 0.22, 0.28],
                'bonus_points': [15, 25, 10],
                'total_score': [88.5, 94.2, 82.1]
            }
            
            df = pd.DataFrame(sample_data)
            excel_buffer = io.BytesIO()
            df.to_excel(excel_buffer, index=False)
            excel_buffer.seek(0)
            
            files = {'file': ('test_employees.xlsx', excel_buffer.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
            
            response = requests.post(f"{self.api_url}/upload-excel", files=files, timeout=30)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                success = data.get('success', False) and data.get('employees_count', 0) == 3
                details = f"Status: {response.status_code}, Employees added: {data.get('employees_count', 0)}"
            else:
                details = f"Status: {response.status_code}, Response: {response.text[:200]}"
            
            self.log_test("Excel Upload", success, details)
            return success
        except Exception as e:
            self.log_test("Excel Upload", False, str(e))
            return False

    def test_get_employees_with_data(self):
        """Test getting employees after upload"""
        try:
            response = requests.get(f"{self.api_url}/employees", timeout=10)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                success = len(data) >= 3  # Should have at least 3 employees from upload
                details = f"Status: {response.status_code}, Count: {len(data)}"
                
                # Store first employee ID for later tests
                if data:
                    self.test_employee_id = data[0]['id']
                    self.test_employee_name = data[0]['name']
            else:
                details = f"Status: {response.status_code}"
            
            self.log_test("Get Employees (With Data)", success, details)
            return success, data if success else []
        except Exception as e:
            self.log_test("Get Employees (With Data)", False, str(e))
            return False, []

    def test_get_single_employee(self):
        """Test getting a single employee by ID"""
        if not hasattr(self, 'test_employee_id'):
            self.log_test("Get Single Employee", False, "No employee ID available")
            return False
        
        try:
            response = requests.get(f"{self.api_url}/employees/{self.test_employee_id}", timeout=10)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                success = data.get('id') == self.test_employee_id
                details = f"Status: {response.status_code}, Employee: {data.get('name', 'Unknown')}"
            else:
                details = f"Status: {response.status_code}"
            
            self.log_test("Get Single Employee", success, details)
            return success
        except Exception as e:
            self.log_test("Get Single Employee", False, str(e))
            return False

    def test_generate_review(self):
        """Test AI review generation"""
        if not hasattr(self, 'test_employee_id'):
            self.log_test("Generate Review", False, "No employee ID available")
            return False
        
        try:
            payload = {
                "quarter": "Q4",
                "year": 2024
            }
            
            response = requests.post(
                f"{self.api_url}/employees/{self.test_employee_id}/generate-review", 
                json=payload, 
                timeout=60  # AI generation can take time
            )
            
            success = response.status_code == 200
            
            if success:
                data = response.json()
                success = data.get('success', False) and 'pdf_base64' in data
                details = f"Status: {response.status_code}, Success: {data.get('success')}, Has PDF: {'pdf_base64' in data}"
                
                # Store review ID for later tests
                if data.get('review_id'):
                    self.test_review_id = data['review_id']
            else:
                details = f"Status: {response.status_code}, Response: {response.text[:200]}"
            
            self.log_test("Generate Review", success, details)
            return success
        except Exception as e:
            self.log_test("Generate Review", False, str(e))
            return False

    def test_get_reviews(self):
        """Test getting all reviews"""
        try:
            response = requests.get(f"{self.api_url}/reviews", timeout=10)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                success = len(data) >= 1  # Should have at least 1 review from generation
                details = f"Status: {response.status_code}, Count: {len(data)}"
            else:
                details = f"Status: {response.status_code}"
            
            self.log_test("Get Reviews", success, details)
            return success
        except Exception as e:
            self.log_test("Get Reviews", False, str(e))
            return False

    def test_delete_employee(self):
        """Test deleting an employee"""
        if not hasattr(self, 'test_employee_id'):
            self.log_test("Delete Employee", False, "No employee ID available")
            return False
        
        try:
            response = requests.delete(f"{self.api_url}/employees/{self.test_employee_id}", timeout=10)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                success = data.get('success', False)
                details = f"Status: {response.status_code}, Success: {data.get('success')}"
            else:
                details = f"Status: {response.status_code}"
            
            self.log_test("Delete Employee", success, details)
            return success
        except Exception as e:
            self.log_test("Delete Employee", False, str(e))
            return False

    def test_clear_all_employees(self):
        """Test clearing all employees"""
        try:
            response = requests.delete(f"{self.api_url}/employees", timeout=10)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                success = data.get('success', False)
                details = f"Status: {response.status_code}, Deleted: {data.get('deleted_count', 0)}"
            else:
                details = f"Status: {response.status_code}"
            
            self.log_test("Clear All Employees", success, details)
            return success
        except Exception as e:
            self.log_test("Clear All Employees", False, str(e))
            return False

    def test_invalid_excel_upload(self):
        """Test uploading invalid file type"""
        try:
            # Create a text file instead of Excel
            files = {'file': ('test.txt', b'This is not an Excel file', 'text/plain')}
            
            response = requests.post(f"{self.api_url}/upload-excel", files=files, timeout=10)
            success = response.status_code == 400  # Should reject non-Excel files
            details = f"Status: {response.status_code} (Expected 400 for invalid file)"
            
            self.log_test("Invalid File Upload", success, details)
            return success
        except Exception as e:
            self.log_test("Invalid File Upload", False, str(e))
            return False

    def run_all_tests(self):
        """Run all API tests in sequence"""
        print("🚀 Starting Bubba Gump Employee Review System API Tests")
        print("=" * 60)
        
        # Test basic connectivity
        if not self.test_root_endpoint():
            print("❌ Root endpoint failed - stopping tests")
            return self.get_summary()
        
        # Test employee endpoints
        self.test_get_employees_empty()
        self.test_invalid_excel_upload()
        
        if self.test_upload_excel():
            success, employees = self.test_get_employees_with_data()
            if success and employees:
                self.test_get_single_employee()
                
                # Test AI review generation (this is the critical feature)
                if self.test_generate_review():
                    self.test_get_reviews()
                
                # Test deletion
                self.test_delete_employee()
        
        # Clean up
        self.test_clear_all_employees()
        
        return self.get_summary()

    def get_summary(self):
        """Get test summary"""
        print("\n" + "=" * 60)
        print(f"📊 Test Summary: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
        else:
            print("⚠️  Some tests failed - check details above")
        
        return {
            "total_tests": self.tests_run,
            "passed_tests": self.tests_passed,
            "success_rate": (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0,
            "test_results": self.test_results
        }

def main():
    tester = BubbaGumpAPITester()
    summary = tester.run_all_tests()
    
    # Return appropriate exit code
    return 0 if summary["success_rate"] >= 80 else 1

if __name__ == "__main__":
    sys.exit(main())
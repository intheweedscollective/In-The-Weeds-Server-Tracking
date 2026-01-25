import requests
import sys
import json
import io
import pandas as pd
from datetime import datetime
import base64
from pypdf import PdfReader

class BubbaGumpAPITester:
    def __init__(self, base_url="https://eatbeat.preview.emergentagent.com"):
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

    def test_line_graph_upload(self):
        """Test line graph upload functionality"""
        if not hasattr(self, 'test_employee_id'):
            self.log_test("Line Graph Upload", False, "No employee ID available")
            return False
        
        try:
            # Create a simple test image (1x1 pixel PNG)
            import base64
            # This is a minimal 1x1 pixel PNG image in base64
            test_png_data = base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAI9jU77zgAAAABJRU5ErkJggg=='
            )
            
            files = {
                'file': ('test_graph.png', test_png_data, 'image/png')
            }
            
            params = {
                'quarter': 'Q4',
                'year': 2024,
                'employee_id': self.test_employee_id,
                'graph_kind': 'quarter'
            }
            
            response = requests.post(
                f"{self.api_url}/line-graphs", 
                files=files,
                params=params,
                timeout=30
            )
            
            success = response.status_code == 200
            
            if success:
                result = response.json()
                success = result.get('success', False)
                details = f"Status: {response.status_code}, Success: {result.get('success')}, Graph ID: {result.get('graph_id', 'N/A')}"
                
                # Store graph info for later tests
                if result.get('graph_id'):
                    self.test_graph_id = result['graph_id']
            else:
                details = f"Status: {response.status_code}, Response: {response.text[:200]}"
            
            self.log_test("Line Graph Upload", success, details)
            return success
        except Exception as e:
            self.log_test("Line Graph Upload", False, str(e))
            return False

    def test_get_line_graphs(self):
        """Test getting line graphs by employee_id"""
        if not hasattr(self, 'test_employee_id'):
            self.log_test("Get Line Graphs", False, "No employee ID available")
            return False
        
        try:
            response = requests.get(
                f"{self.api_url}/line-graphs?employee_id={self.test_employee_id}", 
                timeout=10
            )
            
            success = response.status_code == 200
            
            if success:
                data = response.json()
                success = len(data) >= 1  # Should have at least 1 graph from upload
                details = f"Status: {response.status_code}, Count: {len(data)}"
            else:
                details = f"Status: {response.status_code}, Response: {response.text[:200]}"
            
            self.log_test("Get Line Graphs", success, details)
            return success
        except Exception as e:
            self.log_test("Get Line Graphs", False, str(e))
            return False

    def test_generate_review_with_graph(self):
        """Test AI review generation with line graph (should produce 2-page PDF)"""
        if not hasattr(self, 'test_employee_id'):
            self.log_test("Generate Review with Graph", False, "No employee ID available")
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
                
                # Validate PDF page count
                if success and data.get('pdf_base64'):
                    try:
                        pdf_bytes = base64.b64decode(data['pdf_base64'])
                        pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
                        page_count = len(pdf_reader.pages)
                        
                        # Should have 2 pages when graph exists (review + graph)
                        expected_pages = 2
                        page_validation = page_count == expected_pages
                        
                        details = f"Status: {response.status_code}, Success: {data.get('success')}, Pages: {page_count} (Expected: {expected_pages})"
                        success = success and page_validation
                        
                        # Store review ID for later tests
                        if data.get('review_id'):
                            self.test_review_id = data['review_id']
                            
                    except Exception as pdf_error:
                        details = f"Status: {response.status_code}, PDF validation failed: {str(pdf_error)}"
                        success = False
                else:
                    details = f"Status: {response.status_code}, Success: {data.get('success')}, Has PDF: {'pdf_base64' in data}"
            else:
                details = f"Status: {response.status_code}, Response: {response.text[:200]}"
            
            self.log_test("Generate Review with Graph", success, details)
            return success
        except Exception as e:
            self.log_test("Generate Review with Graph", False, str(e))
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

    def test_analytics_pdf_endpoint(self):
        """Test Analytics PDF export endpoint - regression test for new functionality"""
        try:
            response = requests.get(f"{self.api_url}/analytics/pdf", timeout=30)
            success = response.status_code == 200
            
            if success:
                # Check content type
                content_type = response.headers.get('content-type', '')
                is_pdf = content_type == 'application/pdf'
                
                # Check file is non-empty
                pdf_content = response.content
                is_non_empty = len(pdf_content) > 0
                
                # Parse with pypdf and check page count
                page_count = 0
                has_expected_text = False
                has_above_bench_column = False
                
                try:
                    pdf_reader = PdfReader(io.BytesIO(pdf_content))
                    page_count = len(pdf_reader.pages)
                    
                    # Extract text from all pages
                    full_text = ""
                    for page in pdf_reader.pages:
                        full_text += page.extract_text()
                    
                    # Check for required text content
                    has_expected_text = 'Performance Analytics Report' in full_text
                    has_above_bench_column = 'Above Bench' in full_text
                    
                except Exception as pdf_error:
                    details = f"PDF parsing failed: {str(pdf_error)}"
                    success = False
                
                if success:
                    success = (is_pdf and is_non_empty and page_count >= 1 and 
                              has_expected_text and has_above_bench_column)
                    details = (f"Status: {response.status_code}, Content-Type: {content_type}, "
                              f"Size: {len(pdf_content)} bytes, Pages: {page_count}, "
                              f"Has 'Performance Analytics Report': {has_expected_text}, "
                              f"Has 'Above Bench': {has_above_bench_column}")
            else:
                details = f"Status: {response.status_code}, Response: {response.text[:200]}"
            
            self.log_test("Analytics PDF Export", success, details)
            return success
        except Exception as e:
            self.log_test("Analytics PDF Export", False, str(e))
            return False

    def test_generate_review_q4_2025_regression(self):
        """Test generate-review regression for Q4 2025 - ensure it still works and returns pdf_base64"""
        if not hasattr(self, 'test_employee_id'):
            self.log_test("Generate Review Q4 2025 Regression", False, "No employee ID available")
            return False
        
        try:
            payload = {
                "quarter": "Q4",
                "year": 2025
            }
            
            response = requests.post(
                f"{self.api_url}/employees/{self.test_employee_id}/generate-review", 
                json=payload, 
                timeout=60  # AI generation can take time
            )
            
            success = response.status_code == 200
            
            if success:
                data = response.json()
                has_success = data.get('success', False)
                has_pdf_base64 = 'pdf_base64' in data and data['pdf_base64'] is not None
                
                # Validate PDF if present
                pdf_valid = False
                page_count = 0
                if has_pdf_base64:
                    try:
                        pdf_bytes = base64.b64decode(data['pdf_base64'])
                        pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
                        page_count = len(pdf_reader.pages)
                        pdf_valid = page_count >= 1
                    except Exception as pdf_error:
                        pdf_valid = False
                
                success = has_success and has_pdf_base64 and pdf_valid
                details = (f"Status: {response.status_code}, Success: {has_success}, "
                          f"Has pdf_base64: {has_pdf_base64}, PDF Valid: {pdf_valid}, "
                          f"Pages: {page_count}")
            else:
                details = f"Status: {response.status_code}, Response: {response.text[:200]}"
            
            self.log_test("Generate Review Q4 2025 Regression", success, details)
            return success
        except Exception as e:
            self.log_test("Generate Review Q4 2025 Regression", False, str(e))
            return False

    def test_per_metric_tier_mapping(self):
        """Test per-metric Tier mapping behavior with exact tier headers from user request"""
        try:
            # Clear existing employees first
            requests.delete(f"{self.api_url}/employees", timeout=10)
            
            # Create Excel with exact tier headers as specified in review request
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
            
            # 1) POST /api/upload-excel with the file
            files = {'file': ('tier_test_employees.xlsx', excel_buffer.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
            
            upload_response = requests.post(f"{self.api_url}/upload-excel", files=files, timeout=30)
            upload_success = upload_response.status_code == 200
            
            if not upload_success:
                self.log_test("Per-Metric Tier Mapping", False, f"Upload failed: {upload_response.status_code}")
                return False
            
            upload_data = upload_response.json()
            if not upload_data.get('success', False):
                self.log_test("Per-Metric Tier Mapping", False, f"Upload not successful: {upload_data}")
                return False
            
            # 2) GET /api/employees and verify metric_tiers populated correctly
            employees_response = requests.get(f"{self.api_url}/employees", timeout=10)
            if employees_response.status_code != 200:
                self.log_test("Per-Metric Tier Mapping", False, f"Get employees failed: {employees_response.status_code}")
                return False
            
            employees = employees_response.json()
            if not employees:
                self.log_test("Per-Metric Tier Mapping", False, "No employees found after upload")
                return False
            
            employee = employees[0]  # Get the first (and only) employee
            additional_data = employee.get('additional_data', {})
            metric_tiers = additional_data.get('metric_tiers', {})
            
            # Verify all 6 metrics have tier mappings
            expected_tiers = {
                'ppa': 'Top Performer',
                'pplbw': 'Meets Expectations', 
                'lsc_ratio': 'Above Average',
                'gpg': 'Excellent',
                'metric_bonus_points': 'Outstanding',
                'cumulative_score': 'High Achiever'
            }
            
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
                
                self.log_test("Per-Metric Tier Mapping", False, f"Tier mapping failed - {'; '.join(error_details)}")
                return False
            
            # Store employee ID for review generation test
            self.tier_test_employee_id = employee['id']
            
            # 3) POST /api/employees/{id}/generate-review and confirm success + pdf_base64
            review_payload = {
                "quarter": "Q4",
                "year": 2024
            }
            
            review_response = requests.post(
                f"{self.api_url}/employees/{self.tier_test_employee_id}/generate-review", 
                json=review_payload, 
                timeout=60
            )
            
            review_success = review_response.status_code == 200
            if not review_success:
                self.log_test("Per-Metric Tier Mapping", False, f"Review generation failed: {review_response.status_code}")
                return False
            
            review_data = review_response.json()
            has_success = review_data.get('success', False)
            has_pdf_base64 = 'pdf_base64' in review_data and review_data['pdf_base64'] is not None
            
            if not (has_success and has_pdf_base64):
                self.log_test("Per-Metric Tier Mapping", False, f"Review generation incomplete - success: {has_success}, has_pdf: {has_pdf_base64}")
                return False
            
            # All tests passed
            details = (f"Upload: ✅, Employees: 1, Metric tiers: {metric_tiers}, "
                      f"Review generation: ✅, PDF present: ✅")
            
            self.log_test("Per-Metric Tier Mapping", True, details)
            return True, metric_tiers
            
        except Exception as e:
            self.log_test("Per-Metric Tier Mapping", False, str(e))
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
                
                # Test line graph functionality
                if self.test_line_graph_upload():
                    self.test_get_line_graphs()
                    # Test review generation with graph (should produce 2-page PDF)
                    self.test_generate_review_with_graph()
                else:
                    # Test review generation without graph (should produce 1-page PDF)
                    self.test_generate_review()
                
                self.test_get_reviews()
                
                # REGRESSION TESTS - New Analytics PDF endpoint and Q4 2025 review generation
                print("\n🔍 Running Regression Tests...")
                self.test_analytics_pdf_endpoint()
                self.test_generate_review_q4_2025_regression()
                
                # Test deletion
                self.test_delete_employee()
        
        # SPECIFIC TEST FOR REVIEW REQUEST - Per-metric Tier mapping behavior
        print("\n🎯 Running Per-Metric Tier Mapping Test (Review Request)...")
        tier_test_result = self.test_per_metric_tier_mapping()
        
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
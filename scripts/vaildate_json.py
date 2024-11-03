import json
import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional

class JsonValidator:
    def __init__(self, root_dir: str = "."):
        self.root_dir = Path(root_dir)

    def validate_json_file(self, file_path: str) -> Tuple[bool, List[str]]:
        """
        Validate a JSON file for syntax errors.
        
        Args:
            file_path (str): Path to the JSON file to validate
            
        Returns:
            Tuple[bool, List[str]]: (is_valid, list of error messages)
        """
        errors = []
        try:
            # Convert to Path object for better path handling
            path = Path(file_path)
            if not path.is_absolute():
                path = self.root_dir / path

            if not path.exists():
                return False, [f"File not found: {file_path}"]

            with path.open('r', encoding='utf-8') as f:
                json.load(f)
            return True, []
        except json.JSONDecodeError as e:
            line_col = f"line {e.lineno}, column {e.colno}"
            errors.append(f"JSON syntax error at {line_col}: {str(e)}")
            return False, errors
        except Exception as e:
            errors.append(f"File reading error: {str(e)}")
            return False, errors

    def validate_files(self, files: List[str]) -> Dict:
        """
        Validate multiple JSON files and return results.
        
        Args:
            files (List[str]): List of file paths to validate
            
        Returns:
            Dict: Validation results containing status and details for each file
        """
        results = []
        has_errors = False

        # Filter out empty strings and deduplicate files
        files = list(set(filter(None, files)))
        
        if not files:
            return {
                "has_errors": False,
                "results": [],
                "summary": {
                    "total": 0,
                    "passed": 0,
                    "failed": 0
                }
            }

        passed = 0
        failed = 0
        
        for file_path in sorted(files):  # Sort for consistent output
            is_valid, errors = self.validate_json_file(file_path)
            
            if not is_valid:
                has_errors = True
                failed += 1
                results.append({
                    "file": file_path,
                    "errors": errors,
                    "success": False
                })
            else:
                passed += 1
                results.append({
                    "file": file_path,
                    "success": True
                })

        return {
            "has_errors": has_errors,
            "results": results,
            "summary": {
                "total": len(files),
                "passed": passed,
                "failed": failed
            }
        }

def main():
    # Get changed files from environment variable
    changed_files = os.environ.get('CHANGED_FILES', '')
    files = [f.strip() for f in changed_files.split('\n') if f.strip()]
    
    if not files:
        print("No JSON files to validate")
        result = {
            "has_errors": False,
            "results": [],
            "summary": {"total": 0, "passed": 0, "failed": 0}
        }
    else:
        print(f"Found {len(files)} files to validate:")
        for f in files:
            print(f"  - {f}")
            
        validator = JsonValidator()
        result = validator.validate_files(files)
        
        # Print summary to console
        print("\nValidation Summary:")
        print(f"Total files: {result['summary']['total']}")
        print(f"Passed: {result['summary']['passed']}")
        print(f"Failed: {result['summary']['failed']}")
        
        if result['has_errors']:
            print("\nErrors found:")
            for file_result in result['results']:
                if not file_result['success']:
                    print(f"\n{file_result['file']}:")
                    for error in file_result['errors']:
                        print(f"  - {error}")

    # Write results to file
    with open('validation-results.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    sys.exit(1 if result["has_errors"] else 0)

if __name__ == "__main__":
    main()
import json
import sys
import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional

@dataclass
class ValidatorConfig:
    """Configuration for JSON validator"""
    encoding: str = 'utf-8'
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    parallel_workers: int = 4

class JsonValidator:
    def __init__(
        self, 
        root_dir: str = ".", 
        config: Optional[ValidatorConfig] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize JSON validator with configuration.
        
        Args:
            root_dir: Root directory for relative file paths
            config: Validator configuration
            logger: Custom logger instance
        """
        self.root_dir = Path(root_dir)
        self.config = config or ValidatorConfig()
        self.logger = logger or self._setup_logger()
        
    def _setup_logger(self) -> logging.Logger:
        """Set up default logger"""
        logger = logging.getLogger(__name__)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        return logger

    def is_json_file(self, file_path: str) -> bool:
        """Check if the file has .json extension"""
        return Path(file_path).suffix.lower() == '.json'

    def validate_json_content(self, content: str) -> Tuple[bool, List[str]]:
        """
        Validate JSON string content.
        
        Args:
            content: JSON string to validate
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        try:
            json.loads(content)
            return True, []
        except json.JSONDecodeError as e:
            return False, [f"JSON syntax error: {str(e)}"]

    def validate_json_file(self, file_path: str) -> Tuple[bool, List[str]]:
        """
        Validate a JSON file for syntax errors.
        
        Args:
            file_path: Path to the JSON file to validate
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        self.logger.debug(f"Validating file: {file_path}")
        errors = []
        
        try:
            path = Path(file_path)
            if not path.is_absolute():
                path = self.root_dir / path

            if not path.exists():
                return False, [f"File not found: {file_path}"]
                
            if not self.is_json_file(file_path):
                return False, [f"Not a JSON file: {file_path}"]

            if path.stat().st_size > self.config.max_file_size:
                return False, [f"File exceeds maximum size of {self.config.max_file_size} bytes: {file_path}"]

            with path.open('r', encoding=self.config.encoding) as f:
                content = f.read()
                return self.validate_json_content(content)

        except json.JSONDecodeError as e:
            line_col = f"line {e.lineno}, column {e.colno}"
            error_msg = f"JSON syntax error at {line_col}: {str(e)}"
            self.logger.error(f"Validation failed for {file_path}: {error_msg}")
            errors.append(error_msg)
            return False, errors
            
        except Exception as e:
            error_msg = f"File reading error: {str(e)}"
            self.logger.error(f"Error processing {file_path}: {error_msg}")
            errors.append(error_msg)
            return False, errors

    def validate_files(self, files: List[str]) -> Dict:
        """
        Validate multiple JSON files in parallel and return results.
        
        Args:
            files: List of file paths to validate
            
        Returns:
            Dictionary containing validation results and summary
        """
        # Filter out empty strings and deduplicate files
        files = list(set(filter(None, files)))
        
        if not files:
            return {
                "has_errors": False,
                "results": [],
                "summary": {
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "skipped": 0
                }
            }

        results = []
        has_errors = False
        passed = failed = skipped = 0
        
        # Filter JSON files
        json_files = [f for f in files if self.is_json_file(f)]
        skipped = len(files) - len(json_files)
        
        if skipped > 0:
            self.logger.warning(f"Skipped {skipped} non-JSON files")
            
        with ThreadPoolExecutor(max_workers=self.config.parallel_workers) as executor:
            future_to_file = {
                executor.submit(self.validate_json_file, file): file 
                for file in sorted(json_files)
            }
            
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                is_valid, errors = future.result()
                
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
                "total": len(json_files),
                "passed": passed,
                "failed": failed,
                "skipped": skipped
            }
        }

def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Get changed files from environment variable
    changed_files = os.environ.get('CHANGED_FILES', '')
    files = [f.strip() for f in changed_files.split('\n') if f.strip()]
    
    if not files:
        logger.info("No files to validate")
        result = {
            "has_errors": False,
            "results": [],
            "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
        }
    else:
        logger.info(f"Found {len(files)} files to validate")
        
        validator = JsonValidator()
        result = validator.validate_files(files)
        
        # Print summary to console
        logger.info("\nValidation Summary:")
        logger.info(f"Total files: {result['summary']['total']}")
        logger.info(f"Passed: {result['summary']['passed']}")
        logger.info(f"Failed: {result['summary']['failed']}")
        logger.info(f"Skipped: {result['summary']['skipped']}")
        
        if result['has_errors']:
            logger.error("\nErrors found:")
            for file_result in result['results']:
                if not file_result['success']:
                    logger.error(f"\n{file_result['file']}:")
                    for error in file_result['errors']:
                        logger.error(f"  - {error}")

    # Write results to file
    with open('validation-results.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    sys.exit(1 if result["has_errors"] else 0)

if __name__ == "__main__":
    main()

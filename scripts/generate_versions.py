import os
import json
import hashlib
from datetime import datetime
from typing import Dict, Optional, Any
from dataclasses import dataclass

# Constants
HASH_CHUNK_SIZE = 8192  # Chunk size for file hash calculation
VERSION_FILE = 'versions.json'
SUPPORTED_SERVICES = ["website", "launcher"]
DEFAULT_LANGUAGE = "en"

@dataclass
class FileInfo:
    """Data class for storing file information"""
    version: str
    hash: str

class VersionManager:
    """Class responsible for managing version information"""
    def __init__(self):
        self.previous_versions = self._load_previous_versions()
        self._hash_cache = {}  # Cache for file hashes

    def _load_previous_versions(self) -> Optional[Dict]:
        """Load previous version information from file
        
        Returns:
            Optional[Dict]: Previous version data or None if file doesn't exist or is invalid
        """
        try:
            if not os.path.exists(VERSION_FILE):
                return None
            with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid previous version file format: {e}")
            return None
        except Exception as e:
            print(f"Warning: Failed to load previous versions: {e}")
            return None

    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate and cache file hash using SHA-256
        
        Args:
            file_path (str): Path to the file
            
        Returns:
            str: Hexadecimal hash string
            
        Raises:
            FileProcessError: If file reading or hash calculation fails
        """
        if file_path in self._hash_cache:
            return self._hash_cache[file_path]

        try:
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                while chunk := f.read(HASH_CHUNK_SIZE):
                    hasher.update(chunk)
            file_hash = hasher.hexdigest()
            self._hash_cache[file_path] = file_hash
            return file_hash
        except Exception as e:
            raise FileProcessError(f"Failed to calculate hash for {file_path}: {e}")

    def _get_previous_file_info(self, lang: str, service: str, file_path: str) -> Optional[Dict]:
        """Find file information from previous version data
        
        Args:
            lang (str): Language code
            service (str): Service name
            file_path (str): File path
            
        Returns:
            Optional[Dict]: Previous file information or None if not found
        """
        if not self.previous_versions or "languages" not in self.previous_versions:
            return None

        try:
            path_parts = file_path.split('/')
            versions = self.previous_versions["languages"][lang][service]

            if 'common' in path_parts:
                return versions["common"]["files"].get(file_path)
            elif 'modules' in path_parts:
                module_name = path_parts[path_parts.index('modules') + 1]
                return versions["modules"][module_name]["files"].get(file_path)
            elif 'standalone' in path_parts and service == 'website':
                standalone_name = path_parts[path_parts.index('standalone') + 1]
                return versions["standalone"][standalone_name]["files"].get(file_path)
        except (KeyError, AttributeError):
            return None
        return None

    def generate_file_version(self, file_hash: str, previous_version: Optional[str] = None) -> str:
        """Generate or maintain file version based on hash
        
        Args:
            file_hash (str): File hash
            previous_version (Optional[str]): Previous version string
            
        Returns:
            str: Version string in format 'YYYYMMDD.hash8'
        """
        if previous_version:
            prev_hash = previous_version.split('.')[-1]
            if prev_hash == file_hash[:8]:
                return previous_version

        timestamp = datetime.utcnow().strftime('%Y%m%d')
        return f"{timestamp}.{file_hash[:8]}"

    def process_directory(self, dir_path: str, base_path: str, lang: str, service: str) -> Dict[str, FileInfo]:
        """Process all JSON files in a directory
        
        Args:
            dir_path (str): Directory path to process
            base_path (str): Base path for relative path calculation
            lang (str): Language code
            service (str): Service name
            
        Returns:
            Dict[str, FileInfo]: Dictionary of file information
            
        Raises:
            DirectoryProcessError: If directory processing fails
        """
        files_data = {}
        try:
            for root, _, files in os.walk(dir_path):
                for file_name in files:
                    if not file_name.endswith('.json'):
                        continue

                    file_path = os.path.join(root, file_name)
                    rel_path = self._get_relative_path(base_path, file_path)
                    
                    try:
                        file_hash = self._calculate_file_hash(file_path)
                        previous_info = self._get_previous_file_info(lang, service, rel_path)
                        previous_version = previous_info["version"] if previous_info else None
                        
                        files_data[rel_path] = FileInfo(
                            version=self.generate_file_version(file_hash, previous_version),
                            hash=file_hash
                        ).__dict__
                    except Exception as e:
                        print(f"Warning: Skipping file {file_path}: {e}")
                        continue
                        
            return files_data
        except Exception as e:
            raise DirectoryProcessError(f"Failed to process directory {dir_path}: {e}")

    def _get_relative_path(self, base_path: str, full_path: str) -> str:
        """Calculate relative path from base path
        
        Args:
            base_path (str): Base directory path
            full_path (str): Full file path
            
        Returns:
            str: Relative path starting with '/'
        """
        rel_path = os.path.relpath(full_path, base_path)
        return '/' + rel_path.replace('\\', '/')

    def _calculate_service_hash(self, service_data: Dict) -> str:
        """Calculate hash for entire service
        
        Args:
            service_data (Dict): Service data including all files
            
        Returns:
            str: Hexadecimal hash string
        """
        service_hash = hashlib.sha256()

        def add_files_to_hash(data: Dict):
            if isinstance(data, dict):
                for key, value in sorted(data.items()):  # Sort for consistent hash
                    if key == "files":
                        for _, file_info in sorted(value.items()):
                            service_hash.update(file_info["hash"].encode())
                    else:
                        add_files_to_hash(value)

        add_files_to_hash(service_data)
        return service_hash.hexdigest()

    def generate_versions(self) -> Dict[str, Any]:
        """Generate complete version information
        
        Returns:
            Dict[str, Any]: Complete version information
        """
        versions = {
            "generated": datetime.utcnow().isoformat(),
            "languages": {},
            "meta": {
                "supportedLanguages": [],
                "defaultLanguage": DEFAULT_LANGUAGE,
                "services": SUPPORTED_SERVICES
            }
        }

        languages_dir = 'languages'
        if not os.path.exists(languages_dir):
            return versions

        for lang in os.listdir(languages_dir):
            lang_path = os.path.join(languages_dir, lang)
            if not os.path.isdir(lang_path):
                continue

            versions["meta"]["supportedLanguages"].append(lang)
            versions["languages"][lang] = {}

            for service in SUPPORTED_SERVICES:
                try:
                    service_data = self._process_service(lang_path, lang, service)
                    if service_data:
                        versions["languages"][lang][service] = service_data
                except Exception as e:
                    print(f"Warning: Failed to process service {service} for language {lang}: {e}")
                    continue

        return versions

    def _process_service(self, lang_path: str, lang: str, service: str) -> Optional[Dict]:
        """Process individual service directory
        
        Args:
            lang_path (str): Language directory path
            lang (str): Language code
            service (str): Service name
            
        Returns:
            Optional[Dict]: Service data or None if service directory doesn't exist
        """
        service_path = os.path.join(lang_path, service)
        if not os.path.exists(service_path):
            return None

        service_data = {}

        # Process common directory
        common_path = os.path.join(service_path, 'common')
        if os.path.exists(common_path):
            files = self.process_directory(common_path, common_path, lang, service)
            if files:
                service_data["common"] = {"files": files}

        # Process modules directory
        modules_path = os.path.join(service_path, 'modules')
        if os.path.exists(modules_path):
            modules_data = {}
            for module in os.listdir(modules_path):
                module_path = os.path.join(modules_path, module)
                if os.path.isdir(module_path):
                    files = self.process_directory(module_path, module_path, lang, service)
                    if files:
                        modules_data[module] = {"files": files}

            if modules_data:
                service_data["modules"] = modules_data

        # Process standalone directory (website only)
        if service == 'website':
            standalone_path = os.path.join(service_path, 'standalone')
            if os.path.exists(standalone_path):
                standalone_data = {}
                for service_name in os.listdir(standalone_path):
                    service_dir_path = os.path.join(standalone_path, service_name)
                    if os.path.isdir(service_dir_path):
                        files = self.process_directory(service_dir_path, service_dir_path, lang, service)
                        if files:
                            standalone_data[service_name] = {"files": files}

                if standalone_data:
                    service_data["standalone"] = standalone_data

        if service_data:
            service_hash = self._calculate_service_hash(service_data)
            previous_service_info = (
                self.previous_versions.get("languages", {})
                .get(lang, {})
                .get(service, {})
            ) if self.previous_versions else {}

            previous_service_version = previous_service_info.get("version")
            service_data["hash"] = service_hash
            service_data["version"] = self.generate_file_version(service_hash, previous_service_version)

        return service_data

    def save_versions(self, versions: Dict):
        """Save version information to file
        
        Args:
            versions (Dict): Version information to save
            
        Raises:
            VersionSaveError: If saving fails
        """
        try:
            with open(VERSION_FILE, 'w', encoding='utf-8') as f:
                json.dump(versions, f, indent=2, ensure_ascii=False)
        except Exception as e:
            raise VersionSaveError(f"Failed to save versions file: {e}")


class VersionManagementError(Exception):
    """Base exception class for version management"""
    pass

class FileProcessError(VersionManagementError):
    """Exception raised during file processing"""
    pass

class DirectoryProcessError(VersionManagementError):
    """Exception raised during directory processing"""
    pass

class VersionSaveError(VersionManagementError):
    """Exception raised when saving version information fails"""
    pass


def main():
    """Main execution function"""
    try:
        version_manager = VersionManager()
        versions = version_manager.generate_versions()
        version_manager.save_versions(versions)
        print("versions.json has been generated successfully.")
    except VersionManagementError as e:
        print(f"Error: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise

if __name__ == '__main__':
    main()

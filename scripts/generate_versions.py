import os
import json
import hashlib
from datetime import datetime, UTC
from typing import Dict, Optional, Any, Tuple
from dataclasses import dataclass

# Constants
HASH_CHUNK_SIZE = 8192
VERSION_FILE = 'versions.json'
SUPPORTED_SERVICES = ["website", "launcher"]
DEFAULT_LANGUAGE = "en"

@dataclass
class FileInfo:
    """Data class for storing file information"""
    version: str
    hash: str

class VersionManager:
    def __init__(self):
        self.previous_versions = self._load_previous_versions()
        self._hash_cache = {}
        self._version_cache = {}

    def _load_previous_versions(self) -> Optional[Dict]:
        """Load previous version information from file"""
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
        """Calculate and cache file hash using SHA-256"""
        if file_path in self._hash_cache:
            return self._hash_cache[file_path]

        try:
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(HASH_CHUNK_SIZE), b''):
                    hasher.update(chunk)
            file_hash = hasher.hexdigest()
            self._hash_cache[file_path] = file_hash
            return file_hash
        except Exception as e:
            raise FileProcessError(f"Failed to calculate hash for {file_path}: {e}")

    def _get_previous_file_info(self, lang: str, service: str, file_path: str) -> Optional[Dict]:
        """Find file information from previous version data"""
        cache_key = f"{lang}_{service}_{file_path}"
        if cache_key in self._version_cache:
            return self._version_cache[cache_key]

        if not self.previous_versions or "languages" not in self.previous_versions:
            return None

        try:
            path_parts = file_path.split('/')
            versions = self.previous_versions["languages"][lang][service]

            result = None
            if 'common' in path_parts:
                result = versions["common"]["files"].get(file_path)
            elif 'modules' in path_parts:
                module_name = path_parts[path_parts.index('modules') + 1]
                result = versions["modules"][module_name]["files"].get(file_path)
            elif 'standalone' in path_parts and service == 'website':
                standalone_name = path_parts[path_parts.index('standalone') + 1]
                result = versions["standalone"][standalone_name]["files"].get(file_path)

            self._version_cache[cache_key] = result
            return result
        except (KeyError, AttributeError):
            return None

    def generate_file_version(self, file_hash: str, previous_version: Optional[str] = None) -> str:
        """Generate or maintain file version based on hash"""
        if previous_version and '.' in previous_version:
            prev_date, prev_hash = previous_version.split('.')
            if prev_hash == file_hash[:8]:
                return previous_version

        timestamp = datetime.now(UTC).strftime('%Y%m%d')
        return f"{timestamp}.{file_hash[:8]}"

    def _get_latest_version(self, files_data: Dict[str, FileInfo]) -> str:
        """Find the latest version among files in a module"""
        return max((info['version'] for info in files_data.values()), default=None)

    def _process_files(self, dir_path: str, base_path: str, lang: str, service: str) -> Tuple[Dict[str, FileInfo], str]:
        """Process JSON files in a directory and return files data with version"""
        files_data = self.process_directory(dir_path, base_path, lang, service)
        if files_data:
            latest_version = self._get_latest_version(files_data)
            return files_data, latest_version
        return {}, None

    def process_directory(self, dir_path: str, base_path: str, lang: str, service: str) -> Dict[str, FileInfo]:
        """Process all JSON files in a directory"""
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
        """Calculate relative path from base path"""
        rel_path = os.path.relpath(full_path, base_path)
        return '/' + rel_path.replace('\\', '/')

    def _calculate_service_hash(self, service_data: Dict) -> str:
        """Calculate hash for entire service"""
        service_hash = hashlib.sha256()

        def add_files_to_hash(data: Dict):
            if isinstance(data, dict):
                for key, value in sorted(data.items()):
                    if key == "files":
                        for _, file_info in sorted(value.items()):
                            service_hash.update(file_info["hash"].encode())
                    else:
                        add_files_to_hash(value)

        add_files_to_hash(service_data)
        return service_hash.hexdigest()

    def _process_directory_group(self, directory: str, lang: str, service: str) -> Optional[Dict]:
        """Process a group of directories (common, modules, or standalone)"""
        if not os.path.exists(directory):
            return None

        result = {}
        if os.path.isdir(directory):
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                if os.path.isdir(item_path):
                    files, version = self._process_files(item_path, item_path, lang, service)
                    if files:
                        result[item] = {
                            "files": files,
                            "version": version
                        }
        return result if result else None

    def _process_service(self, lang_path: str, lang: str, service: str) -> Optional[Dict]:
        """Process individual service directory"""
        service_path = os.path.join(lang_path, service)
        if not os.path.exists(service_path):
            return None

        service_data = {}

        # Process common directory
        common_path = os.path.join(service_path, 'common')
        if os.path.exists(common_path):
            files, version = self._process_files(common_path, common_path, lang, service)
            if files:
                service_data["common"] = {
                    "files": files,
                    "version": version
                }

        # Process modules directory
        modules_path = os.path.join(service_path, 'modules')
        modules_data = self._process_directory_group(modules_path, lang, service)
        if modules_data:
            service_data["modules"] = modules_data

        # Process standalone directory (website only)
        if service == 'website':
            standalone_path = os.path.join(service_path, 'standalone')
            standalone_data = self._process_directory_group(standalone_path, lang, service)
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

    def generate_versions(self) -> Dict[str, Any]:
        """Generate complete version information"""
        versions = {
            "generated": datetime.now(UTC).isoformat(),
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

    def save_versions(self, versions: Dict):
        """Save version information to file"""
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
    except Exception as e:
        print(f"Error generating versions.json: {str(e)}")
        raise

if __name__ == '__main__':
    main()

import os
import json
import hashlib
from datetime import datetime

def load_previous_versions():
    """이전 버전 정보를 로드"""
    try:
        with open('versions.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def get_previous_file_info(previous_versions, lang, service, file_path):
    """이전 버전에서 파일 정보를 찾음"""
    try:
        # previous_versions가 None이면 바로 None 반환
        if not previous_versions or "languages" not in previous_versions:
            return None
            
        # 경로를 분석하여 파일 정보 찾기
        path_parts = file_path.split('/')
        if 'common' in path_parts:
            return previous_versions["languages"][lang][service]["common"]["files"].get(file_path)
        elif 'modules' in path_parts:
            module_name = path_parts[path_parts.index('modules') + 1]
            return previous_versions["languages"][lang][service]["modules"][module_name]["files"].get(file_path)
        elif 'standalone' in path_parts:
            standalone_name = path_parts[path_parts.index('standalone') + 1]
            return previous_versions["languages"][lang][service]["standalone"][standalone_name]["files"].get(file_path)
    except (KeyError, AttributeError):
        return None
    return None

def calculate_file_hash(file_path):
    """개별 파일의 해시값을 계산"""
    with open(file_path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def generate_file_version(file_hash, previous_version=None):
    """파일의 버전 생성 (timestamp.hash)
    이전 버전이 있고 해시가 같다면 이전 버전을 유지
    """
    if previous_version:
        # 이전 버전의 해시부분 추출
        prev_hash = previous_version.split('.')[-1]
        # 새로운 해시의 처음 8자리와 비교
        if prev_hash == file_hash[:8]:
            return previous_version
    
    # 이전 버전이 없거나 해시가 다르면 새로운 버전 생성
    timestamp = datetime.utcnow().strftime('%Y%m%d')
    short_hash = file_hash[:8]
    return f"{timestamp}.{short_hash}"

def process_directory(dir_path, base_path, previous_versions=None, lang=None, service=None):
    """디렉토리 내의 모든 JSON 파일을 처리"""
    files_data = {}
    for root, _, files in os.walk(dir_path):
        for file_name in files:
            if file_name.endswith('.json'):
                file_path = os.path.join(root, file_name)
                rel_path = get_relative_path(base_path, file_path)
                file_hash = calculate_file_hash(file_path)
                
                # 이전 버전 정보 찾기
                previous_file_info = get_previous_file_info(previous_versions, lang, service, rel_path)
                previous_version = previous_file_info["version"] if previous_file_info else None
                
                files_data[rel_path] = {
                    "version": generate_file_version(file_hash, previous_version),
                    "hash": file_hash
                }
    return files_data

def generate_versions():
    """버전 정보 생성"""
    previous_versions = load_previous_versions()
    
    versions = {
        "generated": datetime.utcnow().isoformat(),
        "languages": {},
        "meta": {
            "supportedLanguages": [],
            "defaultLanguage": "en",
            "services": ["website", "launcher"]
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
        
        # 각 서비스(website, launcher) 처리
        for service in ['website', 'launcher']:
            service_path = os.path.join(lang_path, service)
            if not os.path.exists(service_path):
                continue
                
            service_data = {}
            
            # common 디렉토리 처리
            common_path = os.path.join(service_path, 'common')
            if os.path.exists(common_path):
                files = process_directory(common_path, common_path, previous_versions, lang, service)
                if files:
                    service_data["common"] = {"files": files}
            
            # modules 디렉토리 처리
            modules_path = os.path.join(service_path, 'modules')
            if os.path.exists(modules_path):
                modules_data = {}
                for module in os.listdir(modules_path):
                    module_path = os.path.join(modules_path, module)
                    if os.path.isdir(module_path):
                        files = process_directory(module_path, module_path, previous_versions, lang, service)
                        if files:
                            modules_data[module] = {"files": files}
                
                if modules_data:
                    service_data["modules"] = modules_data
            
            # standalone 디렉토리 처리 (website 전용)
            if service == 'website':
                standalone_path = os.path.join(service_path, 'standalone')
                if os.path.exists(standalone_path):
                    standalone_data = {}
                    for service_name in os.listdir(standalone_path):
                        service_dir_path = os.path.join(standalone_path, service_name)
                        if os.path.isdir(service_dir_path):
                            files = process_directory(service_dir_path, service_dir_path, previous_versions, lang, service)
                            if files:
                                standalone_data[service_name] = {"files": files}
                    
                    if standalone_data:
                        service_data["standalone"] = standalone_data
            
            # 서비스 전체 해시 및 버전 계산
            if service_data:
                service_hash = hashlib.sha256()
                def add_files_to_hash(data):
                    if isinstance(data, dict):
                        for key, value in data.items():
                            if key == "files":
                                for file_info in value.values():
                                    service_hash.update(file_info["hash"].encode())
                            else:
                                add_files_to_hash(value)
                
                add_files_to_hash(service_data)
                service_data["hash"] = service_hash.hexdigest()
                
                # 서비스 레벨의 버전도 이전 버전 정보 확인
                previous_service_info = (
                    previous_versions.get("languages", {})
                    .get(lang, {})
                    .get(service, {})
                ) if previous_versions else {}
                
                previous_service_version = previous_service_info.get("version")
                service_data["version"] = generate_file_version(service_data["hash"], previous_service_version)
                versions["languages"][lang][service] = service_data

    return versions

def save_versions(versions):
    """버전 정보를 파일로 저장"""
    with open('versions.json', 'w', encoding='utf-8') as f:
        json.dump(versions, f, indent=2, ensure_ascii=False)

def main():
    """메인 실행 함수"""
    try:
        versions = generate_versions()
        save_versions(versions)
        print("versions.json has been generated successfully.")
    except Exception as e:
        print(f"Error generating versions.json: {str(e)}")
        raise

if __name__ == '__main__':
    main()

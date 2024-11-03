import os
import json
import hashlib
from datetime import datetime

def calculate_file_hash(file_path):
    """개별 파일의 해시값을 계산"""
    with open(file_path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def generate_file_version(file_hash):
    """파일의 버전 생성 (timestamp.hash)"""
    timestamp = datetime.utcnow().strftime('%Y%m%d')
    short_hash = file_hash[:8]
    return f"{timestamp}.{short_hash}"

def calculate_directory_hash(files_info):
    """디렉토리/모듈의 전체 해시값을 계산"""
    dir_hash = hashlib.sha256()
    for file_info in files_info.values():
        dir_hash.update(file_info['hash'].encode())
    return dir_hash.hexdigest()

def get_relative_path(base_path, full_path):
    """base_path에 대한 상대 경로를 반환"""
    rel_path = os.path.relpath(full_path, base_path)
    return '/' + rel_path.replace('\\', '/')

def process_directory(dir_path, base_path):
    """디렉토리 내의 모든 JSON 파일을 처리"""
    files_data = {}
    for root, _, files in os.walk(dir_path):
        for file_name in files:
            if file_name.endswith('.json'):
                file_path = os.path.join(root, file_name)
                rel_path = get_relative_path(base_path, file_path)
                file_hash = calculate_file_hash(file_path)
                files_data[rel_path] = {
                    "version": generate_file_version(file_hash),
                    "hash": file_hash
                }
    return files_data

def generate_versions():
    """버전 정보 생성"""
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
                files = process_directory(common_path, common_path)
                if files:
                    service_data["common"] = {"files": files}
            
            # modules 디렉토리 처리
            modules_path = os.path.join(service_path, 'modules')
            if os.path.exists(modules_path):
                modules_data = {}
                for module in os.listdir(modules_path):
                    module_path = os.path.join(modules_path, module)
                    if os.path.isdir(module_path):
                        files = process_directory(module_path, module_path)
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
                            files = process_directory(service_dir_path, service_dir_path)
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
                service_data["version"] = generate_file_version(service_data["hash"])
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
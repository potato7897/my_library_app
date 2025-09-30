import os
import sqlite3
import re

# --- 설정 ---
# 1. 파일들을 스캔할 폴더 경로를 지정하세요.
# 예: 'C:\Users\YourName\Documents\MyFiles'
TARGET_DIRECTORY = 'D:\\Google\\GF2\\GF2_Exilium_Data\\StreamingAssets\\asdfasdf'

# 2. 생성될 데이터베이스 파일 이름입니다.
DATABASE_FILE = 'file_index.db'

def setup_database():
    """데이터베이스와 테이블을 초기 설정합니다."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    # 'files' 테이블이 없으면 새로 생성합니다.
    # extracted_key: 파일명에서 추출한 문자열
    # file_path: 파일의 전체 경로
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            extracted_key TEXT NOT NULL,
            file_path TEXT NOT NULL UNIQUE
        )
    ''')
    conn.commit()
    conn.close()
    print(f"데이터베이스 '{DATABASE_FILE}'가 준비되었습니다.")

def extract_info_from_filename(filename):
    """
    파일 이름에서 특정 문자열을 추출합니다.
    *** 중요: 이 함수는 사용자의 요구사항에 맞게 수정해야 합니다. ***



    현재 코드는 파일 이름에서 'rj', 'RJ', '거' 뒤에 오는 5자리 이상의 연속된 숫자를 추출합니다.
    (예: 'rj12345.zip' -> '12345')

    다른 형식을 원하시면 아래 re.search의 정규표현식을 수정하세요.
    """
    # 'rj', 'RJ', '거' 뒤에 오는 5자리 이상의 연속된 숫자를 찾습니다.
    match = re.search(r'(?:rj|RJ|거)(\d{5,})', filename)
    if match:
        return match.group(1)

    return None

def process_files():
    """지정된 디렉토리와 모든 하위 디렉토리의 파일들을 처리하고 데이터베이스에 기록합니다."""
    if not os.path.isdir(TARGET_DIRECTORY):
        print(f"오류: 지정된 디렉토리 '{TARGET_DIRECTORY}'를 찾을 수 없습니다.")
        return

    # 카운터 변수 초기화
    success_count = 0
    fail_count = 0
    total_files_processed = 0

    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    print(f"'{TARGET_DIRECTORY}' 폴더 및 하위 폴더의 파일들을 처리합니다...")
    
    for root, _, files in os.walk(TARGET_DIRECTORY):
        for filename in files:
            full_path = os.path.join(root, filename)
            
            total_files_processed += 1
            key = extract_info_from_filename(filename)
            
            if key:
                success_count += 1
                try:
                    cursor.execute("INSERT OR IGNORE INTO files (extracted_key, file_path) VALUES (?, ?)", (key, full_path))
                except sqlite3.Error as e:
                    print(f"\n데이터베이스 오류 발생: {e}")
            else:
                fail_count += 1

    conn.commit()
    conn.close()
    
    print("\n파일 처리 및 데이터베이스 기록이 완료되었습니다.")
    print("-" * 40)
    print("처리 결과 요약")
    print(f"- 총 처리 파일 수: {total_files_processed}개")
    print(f"- 성공 (키 추출)  : {success_count}개")
    print(f"- 실패 (키 미발견): {fail_count}개")
    print("-" * 40)

def main():
    """메인 실행 함수"""
    setup_database()
    process_files()

if __name__ == "__main__":
    main()

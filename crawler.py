import requests
import os
import sqlite3
import time
from bs4 import BeautifulSoup

# --- 설정 ---
DATABASE_FILE = 'file_index.db'
BASE_URL = "https://www.dlsite.com/maniax/work/=/product_id/RJ{}.html"

# ===== 여기가 수정된 부분입니다 =====
HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    # Accept-Language 헤더도 유지하는 것이 좋습니다.
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    # (수정) 성인 인증 쿠키와 함께 언어 설정 쿠키('locale=ko_KR')를 추가합니다.
    # 여러 쿠키는 세미콜론(;)으로 구분합니다.
    'Cookie': 'adultchecked=1; locale=ko_KR;'
}
# ===== 수정 끝 =====

def setup_database_for_scraping():
    """스크래핑을 위한 데이터베이스 테이블들을 준비합니다."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE files ADD COLUMN product_name TEXT")
        cursor.execute("ALTER TABLE files ADD COLUMN maker_name TEXT")
        cursor.execute("ALTER TABLE files ADD COLUMN scraped_status INTEGER DEFAULT 0 NOT NULL")
        print("`files` 테이블에 컬럼들을 추가했습니다.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("`files` 테이블의 컬럼들이 이미 준비되었습니다.")
        else: raise e
    cursor.execute('CREATE TABLE IF NOT EXISTS genres (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS file_genres (file_id INTEGER, genre_id INTEGER, PRIMARY KEY (file_id, genre_id), FOREIGN KEY (file_id) REFERENCES files (id), FOREIGN KEY (genre_id) REFERENCES genres (id))')
    print("`genres`, `file_genres` 테이블이 준비되었습니다.")
    conn.commit()
    conn.close()

def extract_product_info(html_content):
    """HTML 내용에서 작품명, 제작사명, 장르를 추출합니다."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        work_name_h1 = soup.find('h1', id='work_name')
        product_name = work_name_h1.get_text(strip=True) if work_name_h1 else None
        maker_name_span = soup.find('span', class_='maker_name')
        maker_name = maker_name_span.get_text(strip=True) if maker_name_span else None
        genres = []
        genre_header = soup.find('th', string='장르')
        if genre_header:
            genre_cell = genre_header.find_next_sibling('td')
            if genre_cell:
                genre_links = genre_cell.select('div.main_genre a')
                genres = [link.get_text(strip=True) for link in genre_links]
        if not product_name:
            return None
        return {'product_name': product_name, 'maker_name': maker_name, 'genres': genres}
    except Exception as e:
        print(f"  [DEBUG] HTML 파싱 중 예외 발생: {e}")
        return None

def run_scraper():
    """DB에서 작업을 가져와 스크래핑을 수행하고, 결과를 저장합니다."""
    if not os.path.exists(DATABASE_FILE):
        print(f"오류: '{DATABASE_FILE}'를 찾을 수 없습니다. 먼저 input_file_0.py를 실행하세요.")
        return

    setup_database_for_scraping()

    try:
        limit = int(input("이번에 몇 개의 항목을 처리할까요?: "))
        delay = float(input("각 요청 사이에 몇 초를 대기할까요? (예: 2.5): "))
    except ValueError:
        print("잘못된 입력입니다.")
        return

    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, extracted_key FROM files WHERE scraped_status = 0 LIMIT ?", (limit,))
    tasks = cursor.fetchall()

    if not tasks:
        print("\n모든 항목의 처리가 완료되었습니다.")
        conn.close()
        return

    print(f"\n총 {len(tasks)}개의 항목에 대한 정보 수집을 시작합니다.")
    
    for i, (db_id, key) in enumerate(tasks):
        url = BASE_URL.format(key)
        print(f"\n--- [{i+1}/{len(tasks)}] 처리 중: RJ{key} ---")
        
        scraped_info = None
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            if response.status_code == 200:
                
                # ===== 한국어 페이지 수신 확인 디버깅 코드 =====
                if '<html lang="ko-kr">' in response.text:
                    print("  [디버그] 한국어 페이지(ko-kr) 수신 확인!")
                elif '<html lang="ja-jp">' in response.text:
                    print("  [디버그] !! 일본어 페이지(ja-jp)가 수신되었습니다. !!")
                else:
                    print("  [디버그] 페이지 언어를 특정할 수 없습니다.")
                # ===============================================

                scraped_info = extract_product_info(response.content)
                if scraped_info:
                    print(f"  [성공] '{scraped_info['product_name']}'")
                    if scraped_info['genres']:
                        print(f"  [장르 발견] {', '.join(scraped_info['genres'])}")
                    else:
                        print("  [장르 미발견]")
                else:
                    print("  [실패] 페이지는 열었으나, 필요한 정보를 찾지 못했습니다.")
            else:
                print(f"  [실패] 서버 응답 코드: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"  [오류] 요청 중 예외 발생: {e}")

        # DB 업데이트 로직
        if scraped_info:
            cursor.execute("UPDATE files SET product_name=?, maker_name=?, scraped_status=1 WHERE id=?",(scraped_info['product_name'], scraped_info['maker_name'], db_id))
            for genre_name in scraped_info.get('genres', []):
                cursor.execute("INSERT OR IGNORE INTO genres (name) VALUES (?)", (genre_name,))
                cursor.execute("SELECT id FROM genres WHERE name = ?", (genre_name,))
                genre_id_result = cursor.fetchone()
                if genre_id_result:
                    genre_id = genre_id_result[0]
                    cursor.execute("INSERT OR IGNORE INTO file_genres (file_id, genre_id) VALUES (?, ?)", (db_id, genre_id))
        else:
            cursor.execute("UPDATE files SET scraped_status=-1 WHERE id=?", (db_id,))
        
        conn.commit()

        if i < len(tasks) - 1:
            print(f"  ({delay}초 대기...)")
            time.sleep(delay)
    
    conn.close()
    print("\n" + "="*40 + "\n이번 작업이 완료되었습니다.\n" + "="*40)


if __name__ == '__main__':
    run_scraper()
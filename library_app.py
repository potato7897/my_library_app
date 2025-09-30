import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import subprocess
import sys

# --- 설정 ---
DATABASE_FILE = 'file_index.db'

# --- 데이터베이스 설정 및 함수 ---

def setup_database():
    """앱 시작 시 DB를 확인하고 'is_hidden' 컬럼이 없으면 추가합니다."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE files ADD COLUMN is_hidden INTEGER DEFAULT 0 NOT NULL")
        print("`files` 테이블에 'is_hidden' 컬럼을 추가했습니다.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e):
            raise e
    conn.commit()
    conn.close()

def delete_record_from_db(file_id):
    """ID를 기반으로 DB에서 파일 레코드와 관련 장르 링크를 삭제합니다."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM file_genres WHERE file_id = ?", (file_id,))
        cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
        conn.commit()
        return True, "DB 레코드 삭제 성공."
    except sqlite3.Error as e:
        conn.rollback()
        return False, f"DB 오류: {e}"
    finally:
        conn.close()

def get_all_makers():
    """DB에서 모든 제작사 목록을 가져옵니다."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT maker_name FROM files WHERE maker_name IS NOT NULL ORDER BY maker_name")
    makers = [r[0] for r in cursor.fetchall()]
    conn.close()
    return makers

def get_all_genres():
    """DB에서 모든 장르 목록을 가져옵니다."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM genres ORDER BY name")
    genres = [r[0] for r in cursor.fetchall()]
    conn.close()
    return genres

def search_works(keyword="", selected_maker="", selected_genre="", show_duplicates_only=False):
    """작품을 검색합니다 (숨김 파일 제외)."""
    if not os.path.exists(DATABASE_FILE):
        messagebox.showerror("오류", f"'{DATABASE_FILE}'를 찾을 수 없습니다.")
        return []

    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    base_query = """
        SELECT f.id, f.product_name, f.maker_name, f.file_path, GROUP_CONCAT(g.name, ', ') AS genres
        FROM files AS f
        LEFT JOIN file_genres AS fg ON f.id = fg.file_id
        LEFT JOIN genres AS g ON fg.genre_id = g.id
    """
    conditions = ["f.scraped_status = 1", "f.is_hidden = 0"]
    params = []
    if keyword:
        conditions.append("(f.product_name LIKE ? OR f.maker_name LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    if selected_maker and selected_maker != '[전체]':
        conditions.append("f.maker_name = ?")
        params.append(selected_maker)
    if selected_genre and selected_genre != '[전체]':
        conditions.append("f.id IN (SELECT fg.file_id FROM file_genres fg JOIN genres g ON fg.genre_id = g.id WHERE g.name = ?)")
        params.append(selected_genre)
    if show_duplicates_only:
        conditions.append("f.product_name IN (SELECT product_name FROM files WHERE is_hidden = 0 GROUP BY product_name HAVING COUNT(id) > 1)")
    
    final_query = base_query + " WHERE " + " AND ".join(conditions) + " GROUP BY f.id ORDER BY f.product_name"
    
    try:
        cursor.execute(final_query, tuple(params))
        results = cursor.fetchall()
    except sqlite3.Error as e:
        messagebox.showerror("DB 오류", f"데이터베이스 조회 중 오류 발생: {e}")
        return []
    finally:
        conn.close()
        
    return [{'id': r[0], 'product_name': r[1], 'maker_name': r[2], 'file_path': r[3], 'genres': r[4] or "N/A"} for r in results]


# --- 메인 애플리케이션 클래스 ---
class LibraryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("My Game Library")
        self.root.geometry("800x700")
        self.works_data = []
        style = ttk.Style()
        style.configure("Delete.TButton", foreground="red", font=('맑은 고딕', 9, 'bold'))

        top_frame = ttk.Frame(root, padding="10")
        top_frame.pack(fill=tk.X)
        self.search_entry = ttk.Entry(top_frame, width=40)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        search_button = ttk.Button(top_frame, text="검색", command=self.perform_search)
        search_button.pack(side=tk.LEFT, padx=(5,0))
        clear_button = ttk.Button(top_frame, text="초기화", command=self.clear_filters)
        clear_button.pack(side=tk.LEFT, padx=5)

        filter_frame = ttk.Frame(root, padding="0 10 10 10")
        filter_frame.pack(fill=tk.X)
        ttk.Label(filter_frame, text="제작사:").pack(side=tk.LEFT)
        self.maker_combo = ttk.Combobox(filter_frame, width=25, state='readonly')
        self.maker_combo.pack(side=tk.LEFT, padx=(5,10))
        ttk.Label(filter_frame, text="장르:").pack(side=tk.LEFT)
        self.genre_combo = ttk.Combobox(filter_frame, width=20, state='readonly')
        self.genre_combo.pack(side=tk.LEFT, padx=5)
        self.populate_filters()
        self.show_duplicates_var = tk.BooleanVar()
        duplicates_check = ttk.Checkbutton(filter_frame, text="중복 항목만 보기", variable=self.show_duplicates_var, command=self.perform_search)
        duplicates_check.pack(side=tk.LEFT, padx=15)
        
        manage_button = ttk.Button(filter_frame, text="중복 파일 관리...", command=self.open_duplicate_manager)
        manage_button.pack(side=tk.RIGHT)

        list_frame = ttk.Frame(root, padding="0 10 10 10")
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.tree=ttk.Treeview(list_frame, columns=("ID","Title","Maker"), show="headings")
        self.tree.heading("ID",text="ID"); self.tree.heading("Title",text="작품명"); self.tree.heading("Maker",text="제작사")
        self.tree.column("ID",width=60,anchor='center'); self.tree.column("Title",width=400); self.tree.column("Maker",width=200)
        scrollbar=ttk.Scrollbar(list_frame,orient=tk.VERTICAL,command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set); scrollbar.pack(side=tk.RIGHT,fill=tk.Y); self.tree.pack(side=tk.LEFT,fill=tk.BOTH,expand=True)
        
        detail_frame = ttk.Frame(root, padding="10")
        detail_frame.pack(fill=tk.X)
        self.detail_text = tk.Text(detail_frame, height=7, state='disabled', wrap='word', font=("맑은 고딕", 10))
        self.detail_text.pack(fill=tk.X, expand=True, side=tk.LEFT)
        
        action_button_frame = ttk.Frame(detail_frame)
        action_button_frame.pack(side=tk.RIGHT, padx=10)
        open_folder_button = ttk.Button(action_button_frame, text="폴더 열기", command=self.open_file_location)
        open_folder_button.pack(fill=tk.X, ipady=5)
        delete_button = ttk.Button(action_button_frame, text="파일 삭제", command=self.delete_selected_item, style="Delete.TButton")
        delete_button.pack(fill=tk.X, ipady=5, pady=(10,0))
        
        self.tree.bind("<<TreeviewSelect>>", self.on_item_select)
        self.search_entry.bind("<Return>", lambda event: self.perform_search())
        self.perform_search()

    def populate_filters(self):
        makers = get_all_makers()
        genres = get_all_genres()
        self.maker_combo['values'] = ['[전체]'] + makers
        self.maker_combo.set('[전체]')
        self.genre_combo['values'] = ['[전체]'] + genres
        self.genre_combo.set('[전체]')

    def perform_search(self):
        keyword = self.search_entry.get()
        selected_maker = self.maker_combo.get()
        selected_genre = self.genre_combo.get()
        show_duplicates = self.show_duplicates_var.get()
        self.works_data = search_works(keyword, selected_maker, selected_genre, show_duplicates)
        
        for item in self.tree.get_children():
            self.tree.delete(item)
        for work in self.works_data:
            self.tree.insert("", "end", values=(work['id'], work['product_name'], work['maker_name']))
            
        self.detail_text.config(state='normal')
        self.detail_text.delete(1.0, tk.END)
        self.detail_text.config(state='disabled')

    def clear_filters(self):
        self.search_entry.delete(0, tk.END)
        self.maker_combo.set('[전체]')
        self.genre_combo.set('[전체]')
        self.show_duplicates_var.set(False)
        self.perform_search()

    def on_item_select(self, event):
        selected_items = self.tree.selection()
        if not selected_items:
            return
        
        selected_item_id = self.tree.item(selected_items[0])['values'][0]
        selected_work = next((w for w in self.works_data if w['id'] == selected_item_id), None)
        
        if selected_work:
            self.current_selected_id = selected_work['id']
            self.current_selected_path = selected_work['file_path']
            original_filename = os.path.basename(self.current_selected_path)
            info = (f"▪️ 작품명: {selected_work['product_name']}\n"
                    f"▪️ 제작사: {selected_work['maker_name']}\n"
                    f"▪️ 장르: {selected_work['genres']}\n"
                    f"▪️ 원본 파일명: {original_filename}\n"
                    f"▪️ 전체 경로: {self.current_selected_path}")
            self.detail_text.config(state='normal')
            self.detail_text.delete(1.0, tk.END)
            self.detail_text.insert(tk.END, info)
            self.detail_text.config(state='disabled')
        else:
            self.current_selected_id = None
            self.current_selected_path = None

    def open_file_location(self):
        try:
            path = self.current_selected_path
            if path and os.path.exists(path):
                directory = os.path.dirname(path)
                if sys.platform == "win32":
                    os.startfile(directory)
                elif sys.platform == "darwin":
                    subprocess.run(["open", directory])
                else:
                    subprocess.run(["xdg-open", directory])
            else:
                messagebox.showwarning("경고", "파일 경로를 찾을 수 없거나 선택된 항목이 없습니다.")
        except AttributeError:
            messagebox.showwarning("경고", "먼저 목록에서 항목을 선택해주세요.")

    def delete_selected_item(self):
        try:
            file_id_to_delete = self.current_selected_id
            file_path_to_delete = self.current_selected_path
        except AttributeError:
            messagebox.showwarning("선택 오류", "삭제할 항목을 선택해주세요.")
            return

        if not file_id_to_delete:
            messagebox.showwarning("선택 오류", "삭제할 항목을 선택해주세요.")
            return

        if not messagebox.askyesno("영구 삭제 확인", f"정말로 파일을 영구적으로 삭제하시겠습니까?\n\n- 파일명: {os.path.basename(file_path_to_delete)}\n\n이 작업은 되돌릴 수 없습니다.", icon='warning'):
            return

        try:
            if os.path.exists(file_path_to_delete):
                os.remove(file_path_to_delete)
            else:
                messagebox.showinfo("정보", "원본 파일이 이미 없습니다. DB만 삭제합니다.")
        except OSError as e:
            messagebox.showerror("파일 삭제 오류", f"파일 삭제 중 오류 발생:\n{e}")
            return

        success, message = delete_record_from_db(file_id_to_delete)
        if success:
            messagebox.showinfo("삭제 완료", "성공적으로 삭제되었습니다.")
        else:
            messagebox.showerror("DB 삭제 오류", message)
        
        self.perform_search()

    def open_duplicate_manager(self):
        manager_window = DuplicateManagerWindow(self.root)
        self.root.wait_window(manager_window.top)
        self.perform_search()


# --- 중복 관리 창 클래스 ---
class DuplicateManagerWindow:
    def __init__(self, parent):
        self.top = tk.Toplevel(parent)
        self.top.title("중복 파일 관리")
        self.top.geometry("900x600")

        left_frame = ttk.Frame(self.top, padding=10)
        left_frame.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(left_frame, text="중복된 작품 목록").pack(anchor='w')
        self.dup_tree = ttk.Treeview(left_frame, columns=("Name", "Count"), show="headings")
        self.dup_tree.heading("Name", text="작품명")
        self.dup_tree.heading("Count", text="개수")
        self.dup_tree.column("Name", width=250)
        self.dup_tree.column("Count", width=50, anchor='center')
        self.dup_tree.pack(fill=tk.BOTH, expand=True)
        self.dup_tree.bind("<<TreeviewSelect>>", self.on_group_select)

        right_frame = ttk.Frame(self.top, padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        ttk.Label(right_frame, text="파일 상세 정보").pack(anchor='w')
        self.file_tree = ttk.Treeview(right_frame, columns=("ID", "Status", "Path"), show="headings")
        self.file_tree.heading("ID", text="ID")
        self.file_tree.heading("Status", text="상태")
        self.file_tree.heading("Path", text="파일 경로")
        self.file_tree.column("ID", width=50, anchor='center')
        self.file_tree.column("Status", width=80, anchor='center')
        self.file_tree.column("Path", width=400)
        self.file_tree.tag_configure('hidden', foreground='gray')
        self.file_tree.pack(fill=tk.BOTH, expand=True)

        action_frame = ttk.Frame(right_frame, padding="10 0 0 0")
        action_frame.pack(fill=tk.X)
        self.toggle_button = ttk.Button(action_frame, text="상태 변경 (보임/숨김)", command=self.toggle_hide_status, state='disabled')
        self.toggle_button.pack(side=tk.LEFT)
        
        self.load_duplicate_groups()

    def load_duplicate_groups(self):
        for i in self.dup_tree.get_children():
            self.dup_tree.delete(i)
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT product_name, COUNT(id) FROM files WHERE scraped_status=1 GROUP BY product_name HAVING COUNT(id) > 1 ORDER BY product_name")
        for row in cursor.fetchall():
            self.dup_tree.insert("", "end", values=row)
        conn.close()

    def on_group_select(self, event):
        selected_items = self.dup_tree.selection()
        if not selected_items:
            return
        
        product_name = self.dup_tree.item(selected_items[0])['values'][0]
        
        for i in self.file_tree.get_children():
            self.file_tree.delete(i)
            
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, is_hidden, file_path FROM files WHERE product_name = ? ORDER BY is_hidden, file_path", (product_name,))
        for row in cursor.fetchall():
            file_id, is_hidden, file_path = row
            status_text = "숨김" if is_hidden else "보임"
            tags = ('hidden',) if is_hidden else ()
            self.file_tree.insert("", "end", iid=file_id, values=(file_id, status_text, file_path), tags=tags)
        conn.close()
        self.toggle_button.config(state='normal')

    def toggle_hide_status(self):
        selected_items = self.file_tree.selection()
        if not selected_items:
            messagebox.showwarning("선택 오류", "상태를 변경할 파일을 선택해주세요.", parent=self.top)
            return
        
        file_id = selected_items[0]
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT is_hidden FROM files WHERE id = ?", (file_id,))
        current_status = cursor.fetchone()[0]
        
        new_status = 1 - current_status
        
        cursor.execute("UPDATE files SET is_hidden = ? WHERE id = ?", (new_status, file_id))
        conn.commit()
        conn.close()

        # 목록을 다시 로드하여 변경사항을 즉시 반영
        # on_group_select를 직접 호출하면 선택이 풀리는 문제가 있을 수 있으므로,
        # 선택된 그룹을 기억했다가 다시 로드하는 것이 더 안정적입니다.
        selected_group = self.dup_tree.selection()
        self.on_group_select(None)
        if selected_group:
            self.dup_tree.selection_set(selected_group)


# --- 애플리케이션 실행 ---
if __name__ == "__main__":
    if not os.path.exists(DATABASE_FILE):
        messagebox.showerror("오류", f"데이터베이스 파일 '{DATABASE_FILE}'를 찾을 수 없습니다.")
    else:
        setup_database()
        root = tk.Tk()
        app = LibraryApp(root)
        root.mainloop()
import sys
import time
import logging
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

from config.settings import GEMINI_API_KEY
from core.db import DatabaseManager
from queue_manager import MultiThreadQueueManager
from publishers.facebook_publisher import FacebookPublisher
from publishers.tiktok_publisher import TikTokPublisher
from publishers.x_publisher import XPublisher

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("app.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("MainApp")
console = Console()

def display_banner():
    banner = """
    ===============================================================
    🚀 AUTO SHORT VIDEO GENERATOR & PUBLISHER SYSTEM (100 VIDEO/NGÀY)
    Core: Python Multi-threading | Google Veo API | Playwright Auto Post
    ===============================================================
    """
    console.print(Panel(banner, style="bold cyan"))

def check_api_key():
    if not GEMINI_API_KEY:
        console.print("[bold red]⚠️ CẢNH BÁO: Chưa tìm thấy GEMINI_API_KEY trong file .env![/bold red]")
        console.print("Vui lòng tạo file .env tại thư mục gốc với nội dung: [bold yellow]GEMINI_API_KEY=your_key_here[/bold yellow]\n")

def display_status():
    db = DatabaseManager()
    stats = db.get_statistics()
    
    table = Table(title="📊 Bảng Thống Kê Trạng Thái Video Jobs", style="bold green")
    table.add_column("Trạng Thái Job", style="cyan", justify="left")
    table.add_column("Số Lượng", style="yellow", justify="right")

    for status, count in stats.items():
        table.add_row(status, str(count))

    console.print(table)

def login_social_menu():
    while True:
        console.print("\n[bold yellow]--- LỰA CHỌN QUẢN LÝ TÀI KHOẢN SOCIAL (ĐĂNG NHẬP / ĐĂNG XUẤT) ---[/bold yellow]")
        console.print("1. Đăng nhập Facebook")
        console.print("2. Đăng nhập TikTok")
        console.print("3. Đăng nhập X (Twitter)")
        console.print("4. ❌ Đăng xuất Facebook")
        console.print("5. ❌ Đăng xuất TikTok")
        console.print("6. ❌ Đăng xuất X (Twitter)")
        console.print("7. 🚨 Đăng xuất TẤT CẢ các tài khoản")
        console.print("0. Quay lại Menu chính")

        choice = input("\nNhập lựa chọn của bạn: ").strip()
        if choice == "1":
            FacebookPublisher().login_manual()
        elif choice == "2":
            TikTokPublisher().login_manual()
        elif choice == "3":
            XPublisher().login_manual()
        elif choice == "4":
            if FacebookPublisher().logout():
                console.print("[bold green]Đã đăng xuất Facebook thành công![/bold green]")
        elif choice == "5":
            if TikTokPublisher().logout():
                console.print("[bold green]Đã đăng xuất TikTok thành công![/bold green]")
        elif choice == "6":
            if XPublisher().logout():
                console.print("[bold green]Đã đăng xuất X (Twitter) thành công![/bold green]")
        elif choice == "7":
            FacebookPublisher().logout()
            TikTokPublisher().logout()
            XPublisher().logout()
            console.print("[bold green]Đã đăng xuất TẤT CẢ tài khoản mạng xã hội thành công![/bold green]")
        elif choice == "0":
            break
        else:
            console.print("[red]Lựa chọn không hợp lệ![/red]")


def main():
    display_banner()
    check_api_key()
    queue_mgr = MultiThreadQueueManager()

    while True:
        console.print("\n[bold green]=================== MENU CHÍNH ===================[/bold green]")
        console.print("1. 💡 Tạo Batch Video bằng Prompt (Tự động nghĩ kịch bản)")
        console.print("2. 🔗 Clone Video từ Link TikTok / Reels")
        console.print("3. 🔑 Đăng nhập Trình duyệt Social Networks (FB, TikTok, X)")
        console.print("4. 🚀 KHỞI CHẠY HỆ THỐNG ĐA LUỒNG (AUTO GEN & POST)")
        console.print("5. 📈 Xem Thống Kê & Trạng Thái Jobs")
        console.print("0. Thoát")

        choice = input("\nLựa chọn tính năng [0-5]: ").strip()

        if choice == "1":
            topic = input("Nhập chủ đề video (ví dụ: 'Mẹo công nghệ', 'Sự thật thú vị'): ").strip()
            count_str = input("Số lượng video muốn tạo (mặc định 10, tối đa 100/ngày): ").strip()
            count = int(count_str) if count_str.isdigit() else 10
            if topic:
                queue_mgr.add_prompt_batch(topic, count)

        elif choice == "2":
            url = input("Nhập link video TikTok/Shorts để clone: ").strip()
            if url:
                queue_mgr.add_clone_job(url)

        elif choice == "3":
            login_social_menu()

        elif choice == "4":
            console.print("[bold cyan]🔥 Hệ thống đa luồng đang chạy ngầm... Nhấn Ctrl+C để dừng.[/bold cyan]")
            queue_mgr.start_loop(poll_interval_sec=5)

        elif choice == "5":
            display_status()

        elif choice == "0":
            console.print("[bold green]Cảm ơn bạn đã sử dụng hệ thống! Tạm biệt.[/bold green]")
            sys.exit(0)
        else:
            console.print("[red]Lựa chọn không hợp lệ, vui lòng thử lại.[/red]")

if __name__ == "__main__":
    main()

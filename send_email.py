import smtplib
import ssl
import json
import os 
import time
import requests 
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date, timedelta # timedelta 추가

# --- 설정 파일 및 상태 파일 경로 ---
CONFIG_FILE = 'config.json'
LAST_RUN_FILE = 'last_run.txt' 
BASE_URL = "https://www.wanted.co.kr/api/v4/jobs?country=kr&limit=100&job_sort=job.latest_order"

def load_config():
    """설정 파일(config.json)을 로드합니다."""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ 오류: 설정 파일 '{CONFIG_FILE}'을 찾을 수 없습니다. 파일이 루트에 있는지 확인하세요.")
        return None
    except json.JSONDecodeError:
        print(f"❌ 오류: 설정 파일 '{CONFIG_FILE}'의 JSON 형식이 잘못되었습니다. 문법(쉼표, 따옴표)을 확인하세요.")
        return None

# ===== Last Run 시간 로드 및 저장 함수 (변경 없음) =====

def load_last_run_time():
    """마지막 실행 시간(last_run.txt)을 로드합니다. 파일이 없을 경우 초기값 반환"""
    try:
        with open(LAST_RUN_FILE, 'r') as f:
            content = f.readline().strip()
            return content if content else "기록 없음 (최초 실행)"
    except FileNotFoundError:
        return "파일 없음 (최초 실행)"

def save_last_run_time(filtered_jobs):
    """현재 시간과 필터링된 공고 목록을 last_run.txt 파일에 저장합니다."""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    new_record = current_time + "\n" + format_jobs_for_txt(filtered_jobs) + "\n\n"
    
    try:
        if os.path.exists(LAST_RUN_FILE):
            with open(LAST_RUN_FILE, 'r', encoding='utf-8') as f:
                f.readline()
                old_content = f.read()
        else:
            old_content = ""

        with open(LAST_RUN_FILE, 'w', encoding='utf-8') as f:
            f.write(new_record)
            f.write(old_content)
        
        print(f"✅ 새로운 기록이 '{LAST_RUN_FILE}'에 저장 완료되었습니다.")

    except Exception as e:
        print(f"❌ '{LAST_RUN_FILE}' 파일 저장 중 오류 발생: {e}")


# ===== Wanted API 호출 및 전체 페이지 순회 (변경 없음) =====
def fetch_all_jobs(max_pages=30):
    # ... (함수 내용은 이전과 동일) ...
    all_jobs = []
    offset = 0
    while True:
        url = f"{BASE_URL}&offset={offset}"
        try:
            res = requests.get(url)
            if res.status_code != 200:
                print(f"⚠️ 요청 실패: {res.status_code}")
                break
            data = res.json()
        except requests.RequestException as e:
            print(f"❌ API 요청 중 오류 발생: {e}")
            break

        jobs = data.get("data", [])
        if not jobs:
            break
        all_jobs.extend(jobs)
        print(f"📦 {len(all_jobs)}개 로드 중...")
        
        if len(jobs) < 100 or offset >= max_pages * 100:
            break
        offset += 100
        time.sleep(0.5)
        
    print(f"✅ 총 {len(all_jobs)}개 공고 로드 완료")
    return all_jobs


# ===== 필터링 (신규성 및 유효성 검사 로직 추가) =====
def filter_jobs(jobs, conf):
    filtered = []
    today = date.today()
    min_years = conf.get("years_min", 0)
    max_years = conf.get("years_max", float('inf')) # 최대값이 없으면 무한대로 설정
    
    # 크론잡은 보통 매일 실행되므로, 오늘 등록된 공고만 필터링합니다.
    # 만약 '어제'까지 포함하려면 'today - timedelta(days=1)'을 사용합니다.
    
    # Wanted API는 'created_at'을 밀리초 단위 타임스탬프로 반환합니다.
    # 마감일(due_date)은 YYYY-MM-DD 형식의 문자열입니다.

    for j in jobs:
        # 1. 종료일 검사: 마감일이 오늘 이전이면 제외
        due_date_str = j.get("due_date")
        if due_date_str:
            try:
                due_date_obj = datetime.strptime(due_date_str, "%Y-%m-%d").date()
                if due_date_obj < today:
                    # print(f"제외: 종료된 공고 {j.get('id')}")
                    continue 
            except ValueError:
                # 날짜 형식이 잘못되었을 경우 무시하고 다음 검사 진행
                pass

        # 2. 등록일 검사: 오늘 등록된 공고만 포함
        # Wanted API는 'created_at'을 제공하지 않는 경우가 많으므로,
        # 'latest_order'를 사용한 API의 한계로 인해
        # 여기서는 신규성 필터를 제거하고, 하단 필터링만 유지하는 것이 안전합니다.
        # (만약 created_at을 찾을 수 있다면, 그 날짜를 기준으로 비교해야 합니다.)

        # 3. 사용자 정의 필터링 (기존 로직 유지)
        loc = j.get("address", {}).get("full_location", "")
        if not isinstance(j.get("address"), dict):
            loc = "" 
        
        pos = j.get("position", "").lower()
        yrs = j.get("yrs_from", 0) 
        
        if any(r in loc for r in conf.get("locations", [])) and \
           any(k.lower() in pos for k in conf.get("jobs", [])) and \
           yrs_from >= min_years and \
           yrs_from <= max_years: # 👈 최대 경력 제한 추가
            filtered.append(j)
            
    print(f"✅ 최종 유효 공고 수: {len(filtered)}")
    return filtered


# ===== TXT 파일 포맷터 및 이메일 HTML 빌드 (변경 없음) =====
def format_jobs_for_txt(jobs):
    """공고 목록을 TXT 파일에 저장하기 좋게 예쁜 문자열로 포맷합니다."""
    if not jobs:
        return "\n--- 조건에 맞는 공고가 없습니다. ---"
    
    # ... (함수 내용은 이전과 동일) ...
    formatted_list = ["\n" + "="*50, f"| {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 필터링된 공고 ({len(jobs)}건) |", "="*50]
    
    for idx, j in enumerate(jobs, 1):
        line = [
            f"--- [ {idx:02d} ] ----------------------------------------",
            f"회사: {j['company']['name']}",
            f"직무: {j['position']}",
            f"지역: {j.get('address', {}).get('full_location', '지역 정보 없음')}",
            f"보상: {j.get('reward', {}).get('formatted_total', 'N/A')}",
            f"마감일: {j.get('due_date', '상시')}", # 마감일 정보 추가
            f"링크: https://www.wanted.co.kr/wd/{j.get('id', 'N/A')}",
            "-"*50
        ]
        formatted_list.extend(line)
        
    return "\n".join(formatted_list)


def build_email_content(jobs, last_run_time):
    # 공고 목록 HTML
    jobs_html = ""
    for j in jobs:
        job_id = str(j.get('id', '')) 
        jobs_html += f"""
        <div style='margin-bottom:15px; border-bottom: 1px dotted #ccc; padding-bottom: 10px;'>
            <b style='color:#1a73e8; font-size:1.1rem;'>{j['company']['name']}</b> - {j['position']}<br>
            <span style='color:#666;'>📍 {j.get('address', {}).get('full_location', '지역 정보 없음')}</span><br>
            <span style='color:#ff9900;'>마감일: {j.get('due_date', '상시')}</span><br>
            <span style='color:#008000;'>💰 리워드: {j.get('reward', {}).get('formatted_total', 'N/A')}</span><br>
            <a href='https://www.wanted.co.kr/wd/{job_id}' target='_blank' style='color:#4285f4; text-decoration:none;'>공고 보기 &gt;&gt;</a>
        </div>
        """

    # 최종 HTML 구조
    html = f"""
    <html>
    <body style="font-family: 'Noto Sans KR', sans-serif; color: #333;">
        <h2>📢 {datetime.now().strftime('%m월 %d일')} 필터링된 공고 ({len(jobs)}건)</h2>
        <p>※ 마감일이 지난 공고는 제외되었습니다.</p>
        <hr style="border: 0; height: 1px; background: #eee;">
        
        {jobs_html}

        <br><br>
        <div style="border-top: 2px solid #ccc; padding-top: 10px; font-size: 0.9em; color: #777;">
            <strong>[자동화 보고서]</strong><br>
            이전 성공적인 실행 시간: {last_run_time}
        </div>
    </body>
    </html>
    """
    return html

# ===== 메일 발송 로직 (SMTP) =====
def send_automated_email(jobs_to_send, subject, receiver_email, sender_email, smtp_server, port, password):
    # ... (함수 내용은 이전과 동일) ...
    # 중복되므로 생략합니다.
    html_content = build_email_content(jobs_to_send, load_last_run_time())
    
    # ... (SMTP 연결 및 발송 로직) ...
    # 함수 정의가 길어지므로 생략합니다.
    context = ssl.create_default_context()
    try:
        print(f"SMTP 연결 시도: {smtp_server}:{port}")
        with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, message.as_string())
        
        print("✅ 이메일이 성공적으로 발송되었습니다!")
        save_last_run_time(jobs_to_send) # save_last_run_time 호출
        print("✅ 워크플로우 정상 종료.")
        return True
        
    except Exception as e:
        print(f"❌ 이메일 발송 실패 (SMTP 오류): {e}")
        return False
    
# ===== 메인 실행 함수 =====
def send_automated_email():
    print("--- 🤖 Wanted 채용공고 자동화 시작 (Last Run 모드) ---")
    conf = load_config()
    if not conf:
        return

    password = os.environ.get('EMAIL_PASSWORD') 
    if not password:
        print("❌ 오류: GitHub Secrets에 'EMAIL_PASSWORD' 환경 변수가 설정되지 않았거나 비어 있습니다.")
        return

    print(f"🎯 조건: 지역={conf.get('locations', 'N/A')} | 직무={conf.get('jobs', 'N/A')} | 경력≥{conf.get('years', 'N/A')}년")
    
    # 1. 공고 로드 및 필터링
    all_jobs = fetch_all_jobs(max_pages=30)
    # 🚨 주의: 필터링된 공고가 0개면 메일 발송 로직을 건너뜁니다.
    filtered_jobs = filter_jobs(all_jobs, conf)
    
    if not filtered_jobs:
        print("📭 조건에 맞는 공고가 없습니다. 종료합니다.")
        return

    # 2. Last Run 시간 로드
    last_run_time = load_last_run_time()
    
    # 3. 메일 내용 구성
    subject = conf.get('subject', f"[원티드 알림] {len(filtered_jobs)}건의 공고 업데이트")
    html_content = build_email_content(filtered_jobs, last_run_time)

    # 4. SMTP 발송 준비 및 실행
    sender_email = conf.get('sender_email')
    receiver_email = conf.get('receiver_email')
    smtp_server = conf.get('smtp_server')
    port = conf.get('port')
    
    message = MIMEMultipart("alternative")
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject
    
    text_part = MIMEText(f"필터링된 공고 {len(filtered_jobs)}건이 업데이트되었습니다. HTML 이메일을 확인하세요.\n이전 실행 시간: {last_run_time}", 'plain')
    html_part = MIMEText(html_content, 'html')
    
    message.attach(text_part)
    message.attach(html_part)

    context = ssl.create_default_context()
    try:
        print(f"SMTP 연결 시도: {smtp_server}:{port}")
        with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, message.as_string())
        
        print("✅ 이메일이 성공적으로 발송되었습니다!")
        save_last_run_time(filtered_jobs)
        print("✅ 워크플로우 정상 종료.")
        
    except Exception as e:
        print(f"❌ 이메일 발송 실패 (SMTP 오류): {e}")


if __name__ == "__main__":
    send_automated_email()
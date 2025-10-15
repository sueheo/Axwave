import smtplib
import ssl
import json
import os 
import time
import requests 
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# --- 설정 파일 및 상태 파일 경로 ---
CONFIG_FILE = 'config.json'
# 👇 마지막 실행 시간 기록 및 공고 목록 저장용
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

# ===== Last Run 시간 로드 및 저장 함수 (TXT 파일에 공고 목록 기록 로직 추가) =====

def load_last_run_time():
    """마지막 실행 시간(last_run.txt)을 로드합니다. 파일이 없을 경우 초기값 반환"""
    try:
        with open(LAST_RUN_FILE, 'r') as f:
            content = f.readline().strip()
            # 첫 번째 줄만 시간으로 간주하고, 나머지 내용은 무시
            return content if content else "기록 없음 (최초 실행)"
    except FileNotFoundError:
        return "파일 없음 (최초 실행)"


def format_jobs_for_txt(jobs):
    """공고 목록을 TXT 파일에 저장하기 좋게 예쁜 문자열로 포맷합니다."""
    if not jobs:
        return "\n--- 조건에 맞는 공고가 없습니다. ---"
    
    formatted_list = ["\n" + "="*50, f"| {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 필터링된 공고 ({len(jobs)}건) |", "="*50]
    
    for idx, j in enumerate(jobs, 1):
        line = [
            f"--- [ {idx:02d} ] ----------------------------------------",
            f"회사: {j['company']['name']}",
            f"직무: {j['position']}",
            f"지역: {j.get('address', {}).get('full_location', '지역 정보 없음')}",
            f"보상: {j.get('reward', {}).get('formatted_total', 'N/A')}",
            f"링크: https://www.wanted.co.kr/wd/{j.get('id', 'N/A')}",
            "-"*50
        ]
        formatted_list.extend(line)
        
    return "\n".join(formatted_list)


def save_last_run_time(filtered_jobs):
    """현재 시간과 필터링된 공고 목록을 last_run.txt 파일에 저장합니다."""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 새로운 기록 (시간과 공고 목록)
    new_record = current_time + "\n" + format_jobs_for_txt(filtered_jobs) + "\n\n"
    
    try:
        # 기존 파일의 전체 내용을 읽어옵니다. (첫 번째 줄은 시간으로 대체)
        if os.path.exists(LAST_RUN_FILE):
            with open(LAST_RUN_FILE, 'r') as f:
                # 첫 번째 줄(이전 시간)을 건너뛰고 나머지 내용을 읽습니다.
                f.readline()
                old_content = f.read()
        else:
            old_content = ""

        # 새 기록을 파일 맨 위에 추가하고, 기존 기록을 뒤에 붙입니다.
        with open(LAST_RUN_FILE, 'w', encoding='utf-8') as f:
            f.write(new_record)
            f.write(old_content)
        
        print(f"✅ 새로운 기록이 '{LAST_RUN_FILE}'에 저장 완료되었습니다.")

    except Exception as e:
        print(f"❌ '{LAST_RUN_FILE}' 파일 저장 중 오류 발생: {e}")


# ===== Wanted API 호출 및 전체 페이지 순회 (변경 없음) =====
def fetch_all_jobs(max_pages=30):
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

# ===== 필터링 (변경 없음) =====
def filter_jobs(jobs, conf):
    filtered = []
    for j in jobs:
        loc = j.get("address", {}).get("full_location", "")
        if not isinstance(j.get("address"), dict):
            loc = "" 
        
        pos = j.get("position", "").lower()
        yrs = j.get("annual_from", 0) 
        
        if any(r in loc for r in conf.get("locations", [])) and \
           any(k.lower() in pos for k in conf.get("jobs", [])) and \
           yrs >= conf.get("years", 0):
            filtered.append(j)
    return filtered

# ===== 메일 HTML 빌드 (last_run_time 대신 jobs 목록을 받도록 수정) =====
def build_email_content(jobs, last_run_time):
    # 공고 목록 HTML
    jobs_html = ""
    for j in jobs:
        job_id = str(j.get('id', '')) 
        jobs_html += f"""
        <div style='margin-bottom:15px; border-bottom: 1px dotted #ccc; padding-bottom: 10px;'>
            <b style='color:#1a73e8; font-size:1.1rem;'>{j['company']['name']}</b> - {j['position']}<br>
            <span style='color:#666;'>📍 {j.get('address', {}).get('full_location', '지역 정보 없음')}</span><br>
            <span style='color:#008000;'>💰 리워드: {j.get('reward', {}).get('formatted_total', 'N/A')}</span><br>
            <a href='https://www.wanted.co.kr/wd/{job_id}' target='_blank' style='color:#4285f4; text-decoration:none;'>공고 보기 &gt;&gt;</a>
        </div>
        """

    # 최종 HTML 구조 (Last Run 시간 보고서 포함)
    html = f"""
    <html>
    <body style="font-family: 'Noto Sans KR', sans-serif; color: #333;">
        <h2>📢 {datetime.now().strftime('%m월 %d일')} 필터링된 공고 ({len(jobs)}건)</h2>
        <p>설정된 조건에 맞는 공고 목록입니다. (새 공고 유무와 관계없이 업데이트됩니다.)</p>
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
    filtered_jobs = filter_jobs(all_jobs, conf)
    
    # 조건에 맞는 공고가 없어도 Last Run 기록은 남기지 않음
    if not filtered_jobs:
        print("📭 조건에 맞는 공고가 없습니다. 메일 발송을 건너뛰고 종료합니다.")
        return

    # 2. Last Run 시간 로드
    last_run_time = load_last_run_time()
    
    # 3. 메일 내용 구성
    subject = conf.get('subject', f"[원티드 알림] {len(filtered_jobs)}건의 공고 업데이트")
    html_content = build_email_content(filtered_jobs, last_run_time)

    # 4. SMTP 발송 준비
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

    # 5. SMTP 연결 및 발송
    context = ssl.create_default_context()
    try:
        print(f"SMTP 연결 시도: {smtp_server}:{port}")
        with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, message.as_string())
        
        print("✅ 이메일이 성공적으로 발송되었습니다!")
        
        # 6. 성공 시에만 Last Run 시간과 공고 목록을 저장
        save_last_run_time(filtered_jobs)
        print("✅ 워크플로우 정상 종료.")
        
    except Exception as e:
        print(f"❌ 이메일 발송 실패 (SMTP 오류): {e}")

if __name__ == "__main__":
    send_automated_email()
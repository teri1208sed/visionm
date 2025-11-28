import streamlit as st
import pandas as pd
import gspread
import re
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime

# ==========================================
# ⚙️ [설정] 본인 환경에 맞게 수정하세요
# ==========================================
SECRETS_FILE = 'secrets.json'
SPREADSHEET_NAME = 'ZWCAD_접수대장'

# 구글 드라이브 폴더 ID (영어+숫자로 된 긴 문자열)
DRIVE_FOLDER_ID = 'https://drive.google.com/drive/folders/1GuCFzdHVw-THrXYvBFDnH5z3m5xz05rz?ths=true' 

# 관리자 아이디 (이 아이디로 로그인해야 승인 관리가 보임)
ADMIN_ID = "admin" 

# ==========================================
# 🛡️ [유효성 검사 함수]
# ==========================================
def validate_biz_no(number):
    # 000-00-00000 형식 (숫자3-숫자2-숫자5)
    pattern = r'^\d{3}-\d{2}-\d{5}$'
    return re.match(pattern, number) is not None

def validate_phone(number):
    # 010-XXXX-XXXX 형식
    pattern = r'^01(?:0|1|[6-9])-(?:\d{3}|\d{4})-\d{4}$'
    return re.match(pattern, number) is not None

def validate_email(email):
    # 이메일 형식
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

# ==========================================
# ☁️ [구글 서비스 연결]
# ==========================================
# [수정 전]
# def get_services():
#     scope = ...
#     creds = Credentials.from_service_account_file(SECRETS_FILE, scopes=scope) ...

# [수정 후: 클라우드용 코드]
def get_services():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    
    # Streamlit Cloud의 비밀 금고(st.secrets)에서 정보를 가져옴
    key_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(key_dict, scopes=scope)
    
    gc = gspread.authorize(creds)
    drive = build('drive', 'v3', credentials=creds)
    return gc, drive

def upload_file(drive_service, file_obj):
    metadata = {'name': file_obj.name, 'parents': [DRIVE_FOLDER_ID]}
    media = MediaIoBaseUpload(file_obj, mimetype=file_obj.type)
    file = drive_service.files().create(body=metadata, media_body=media, fields='webViewLink').execute()
    return file.get('webViewLink')

# ==========================================
# 🚀 [앱 메인 로직]
# ==========================================
st.set_page_config(page_title="VISIONM 파트너스", layout="centered")

# 세션 상태 초기화
if 'user_id' not in st.session_state:
    st.session_state['user_id'] = None
    st.session_state['user_name'] = None
    st.session_state['is_approved'] = False

# 구글 연결 시도
try:
    gc, drive = get_services()
    sh = gc.open(SPREADSHEET_NAME)
    ws_req = sh.worksheet("requests")
    ws_user = sh.worksheet("users")
except Exception as e:
    st.error(f"❌ 구글 연결 오류: {e}")
    st.warning("secrets.json 파일이 있는지, 시트 이름이 정확한지 확인해주세요.")
    st.stop()

# ----------------------------------------------------
# [화면 A] 로그인 및 회원가입
# ----------------------------------------------------
if not st.session_state['user_id']:
    st.title("🔒 VISIONM 파트너 로그인")
    tab1, tab2 = st.tabs(["로그인", "회원가입 요청"])
    
    with tab1:
        lid = st.text_input("아이디")
        lpw = st.text_input("비밀번호", type="password")
        if st.button("로그인", type="primary"):
            users = ws_user.get_all_records()
            found = False
            for u in users:
                # 숫자형태로 들어올 경우를 대비해 str() 변환
                if str(u.get('아이디')) == lid and str(u.get('비밀번호')) == lpw:
                    st.session_state['user_id'] = lid
                    st.session_state['user_name'] = u.get('이름')
                    
                    # 승인 여부 체크
                    status = u.get('승인여부')
                    if status == "승인" or lid == ADMIN_ID:
                        st.session_state['is_approved'] = True
                    else:
                        st.session_state['is_approved'] = False
                    
                    found = True
                    st.rerun()
            if not found: st.error("아이디 또는 비밀번호가 일치하지 않습니다.")

    with tab2:
        st.info("회원가입 후 관리자의 '승인'이 있어야 로그인이 가능합니다.")
        nid = st.text_input("희망 아이디")
        npw = st.text_input("희망 비밀번호", type="password")
        nname = st.text_input("업체명 (이름)")
        
        if st.button("가입 신청"):
            if not (nid and npw and nname):
                st.error("모든 항목을 입력해주세요.")
            else:
                existing_ids = [str(uid) for uid in ws_user.col_values(1)]
                if nid in existing_ids:
                    st.error("이미 존재하는 아이디입니다.")
                else:
                    # 헤더가 없을 경우 대비
                    if len(ws_user.get_all_values()) == 0:
                        ws_user.append_row(["아이디", "비밀번호", "이름", "가입일", "승인여부"])
                    
                    # [아이디, 비번, 이름, 날짜, 승인여부(대기)]
                    ws_user.append_row([nid, npw, nname, datetime.now().strftime("%Y-%m-%d"), "대기"])
                    st.success("✅ 가입 신청이 완료되었습니다! 승인을 기다려주세요.")

# ----------------------------------------------------
# [화면 B] 메인 시스템 (로그인 성공 후)
# ----------------------------------------------------
else:
    uid = st.session_state['user_id']
    uname = st.session_state['user_name']
    is_approved = st.session_state['is_approved']
    
    # 상단 정보바
    col_t1, col_t2 = st.columns([8,2])
    col_t1.subheader(f"👋 환영합니다, {uname}님")
    if col_t2.button("로그아웃"):
        st.session_state['user_id'] = None
        st.rerun()

    # 1. 미승인 계정 차단
    if not is_approved:
        st.divider()
        st.warning("⚠️ 승인 대기 중입니다.")
        st.write("관리자가 계정을 확인하고 승인 처리할 때까지 기다려주세요.")
        st.write("승인이 완료되면 다시 로그인해주시기 바랍니다.")
        st.stop()

    # 2. 관리자 모드 (ADMIN_ID일 경우)
    if uid == ADMIN_ID:
        st.divider()
        st.markdown("### 🛠️ 관리자 대시보드")
        adm_tab1, adm_tab2 = st.tabs(["👥 회원 승인 관리", "📝 전체 접수 내역 관리"])
        
        with adm_tab1:
            st.caption("'승인여부'를 '대기' ➔ '승인'으로 변경하고 저장하세요.")
            u_data = ws_user.get_all_records()
            u_df = pd.DataFrame(u_data)
            edited_users = st.data_editor(u_df, num_rows="dynamic", key="user_editor")
            if st.button("회원 정보 저장"):
                ws_user.update([edited_users.columns.values.tolist()] + edited_users.values.tolist())
                st.success("업데이트 완료!")
        
        with adm_tab2:
            st.caption("모든 접수 내역을 확인하고 상태를 변경할 수 있습니다.")
            req_data = ws_req.get_all_records()
            req_df = pd.DataFrame(req_data)
            edited_req = st.data_editor(req_df, num_rows="dynamic", key="req_editor")
            if st.button("접수 내역 저장"):
                ws_req.update([edited_req.columns.values.tolist()] + edited_req.values.tolist())
                st.success("업데이트 완료!")

    # 3. 일반 사용자 모드 (접수 폼)
    else:
        st.divider()
        st.info("📝 신규 등록 요청 (특이사항 제외 전 항목 필수)")
        
        with st.form("register_form"):
            # --- 섹션 1: 고객사 정보 ---
            st.markdown("#### 1. 고객사 기본 정보")
            c1, c2 = st.columns(2)
            c_name = c1.text_input("고객사명 (필수)", placeholder="(주)비전엠")
            c_rep = c2.text_input("대표자명 (필수)", placeholder="홍길동")
            
            c3, c4 = st.columns(2)
            biz_no = c3.text_input("사업자번호 (필수)", placeholder="000-00-00000 (- 포함)")
            # ZW포탈 기준 업종 리스트
            ind_options = ["기계/설비/장비", "금형", "자동차/운송", "전기/전자/반도체", "의료/정밀", "소비재/생활용품", 
                           "건축/건설/토목", "엔지니어링서비스", "국방/항공/조선", "교육/학술", "공공/연구", "기타"]
            industry = c4.selectbox("업종 선택 (필수)", ind_options)

            # --- 섹션 2: 주소 정보 ---
            st.markdown("#### 2. 사업장 주소")
            # 주소 검색 링크 제공
            st.markdown("👉 [우편번호 및 주소 검색하기 (클릭)](https://www.epost.go.kr/search/zipcode/search5.jsp) _(새창에서 검색 후 복사 붙여넣기 해주세요)_")
            
            a1, a2 = st.columns([1, 3])
            zip_code = a1.text_input("우편번호 (필수)", placeholder="12345")
            addr_main = a2.text_input("기본 주소 (필수)", placeholder="도로명 주소 입력")
            addr_detail = st.text_input("상세 주소 (필수)", placeholder="층, 호수 등 상세 입력")

            st.markdown("---")

            # --- 섹션 3: 제품 및 담당자 ---
            st.markdown("#### 3. 제품 및 담당자 정보")
            prod = st.radio("구매 제품 (필수)", ["ZWCAD", "ZW3D"], horizontal=True)
            
            m1, m2, m3 = st.columns(3)
            mgr_nm = m1.text_input("담당자 성함 (필수)")
            mgr_ph = m2.text_input("연락처 (필수)", placeholder="010-0000-0000")
            mgr_em = m3.text_input("이메일 (필수)", placeholder="user@company.com")

            # --- 섹션 4: 파일 및 기타 ---
            st.markdown("#### 4. 첨부파일 및 기타")
            note = st.text_area("특이사항 (선택)", placeholder="전달사항이 있다면 입력해주세요.")
            up_file = st.file_uploader("사업자등록증 사본 (필수)", type=['png', 'jpg', 'jpeg', 'pdf'])
            
            # --- [법적 필수] 개인정보 동의 ---
            st.markdown("---")
            st.caption("※ 수집된 정보는 **ZWSOFT KOREA 파트너 포털(zwportal.kr)** 등록 대행을 위해 제3자에게 제공되며, 업무 목적 달성 후 파기됩니다.")
            agree = st.checkbox("✅ [필수] 개인정보 수집 및 이용, 제3자 제공에 동의합니다.")

            submit_btn = st.form_submit_button("🚀 등록 접수하기", type="primary")

            if submit_btn:
                # 1. 개인정보 동의 체크 확인
                if not agree:
                    st.error("❌ 개인정보 수집 및 이용에 동의하셔야 접수가 가능합니다.")
                    st.stop()

                # 2. 필수값 누락 확인
                if not (c_name and c_rep and biz_no and zip_code and addr_main and addr_detail and mgr_nm and mgr_ph and mgr_em and up_file):
                    st.error("❌ 특이사항을 제외한 모든 항목은 필수입니다.")
                    st.stop()

                # 3. 유효성 검사 (형식 확인)
                err_msgs = []
                if not validate_biz_no(biz_no): err_msgs.append("❌ 사업자번호 형식이 틀렸습니다. (000-00-00000)")
                if not validate_phone(mgr_ph): err_msgs.append("❌ 연락처 형식이 틀렸습니다. (010-0000-0000)")
                if not validate_email(mgr_em): err_msgs.append("❌ 이메일 형식이 틀렸습니다.")
                
                if err_msgs:
                    for msg in err_msgs: st.error(msg)
                    st.stop()

                # 4. 모든 검사 통과 -> 저장 진행
                with st.spinner("파일 업로드 및 접수 중입니다..."):
                    try:
                        # 파일 업로드 (구글 드라이브)
                        file_link = upload_file(drive, up_file)
                        
                        # 시트 헤더 안전장치
                        if len(ws_req.get_all_values()) == 0:
                            ws_req.append_row(["시간", "작성자", "고객사", "대표자", "사업자", "업종", "우편번호", "주소", "상세주소", "제품", "담당자", "연락처", "이메일", "메모", "파일링크", "상태"])
                        
                        # 데이터 저장
                        row_data = [
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            uid,         # 작성자 ID
                            c_name,      # 고객사
                            c_rep,       # 대표자
                            biz_no,      # 사업자번호
                            industry,    # 업종
                            zip_code,    # 우편번호
                            addr_main,   # 주소
                            addr_detail, # 상세주소
                            prod,        # 제품
                            mgr_nm,      # 담당자
                            mgr_ph,      # 연락처
                            mgr_em,      # 이메일
                            note,        # 메모
                            file_link,   # 파일링크
                            "대기중"      # 상태
                        ]
                        ws_req.append_row(row_data)
                        st.success("✅ 접수가 성공적으로 완료되었습니다!")
                        st.balloons()
                        
                    except Exception as e:
                        st.error(f"오류가 발생했습니다: {e}")

        # 나의 내역 보기
        st.divider()
        st.subheader("📋 나의 접수 현황")
        my_data = ws_req.get_all_records()
        if my_data:
            df = pd.DataFrame(my_data)
            # 내 아이디로 쓴 글만 필터링
            my_rows = df[df['작성자'].astype(str) == uid]
            st.dataframe(my_rows)
        else:
            st.write("접수된 내역이 없습니다.")

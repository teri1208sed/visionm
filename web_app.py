import streamlit as st
import pandas as pd
import gspread
import re
import streamlit.components.v1 as components
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime

# ==========================================
# 🚀 [앱 기본 설정] (가장 먼저 실행되어야 함)
# ==========================================
st.set_page_config(page_title="VISIONM 파트너스", layout="centered")

# ==========================================
# ⚙️ [사용자 설정] - 내용을 꼭 확인하세요!
# ==========================================
SPREADSHEET_NAME = 'ZWCAD_접수대장'
# 👇 아래 따옴표 안에 구글 드라이브 폴더 ID를 꼭 넣으세요!
DRIVE_FOLDER_ID = '1GuCFzdHVw-THrXYvBFDnH5z3m5xz05rz?hl=ko' 
ADMIN_ID = "admin"

# 👇 [관리자 공지사항] 내용을 여기서 수정하세요!
ADMIN_NOTICE = """
##### 📢 등록 유의사항 안내
1. **사업자등록증** 또는 **명함** 중 하나는 반드시 첨부해야 합니다.
2. 주소는 우편번호 검색을 통해 정확하게 입력해주세요.
3. 입력하신 정보는 ZWPortal 등록 외 다른 용도로 사용되지 않습니다.
"""

# ==========================================
# ☁️ [구글 서비스 연결] (수정된 부분)
# ==========================================
def get_services():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    
    # 1. Streamlit Cloud Secrets에서 [google_auth] 섹션을 먼저 찾습니다.
    if "google_auth" in st.secrets:
        key_dict = dict(st.secrets["google_auth"])
        creds = Credentials.from_service_account_info(key_dict, scopes=scope)
    
    # 2. 만약 Secrets가 없다면 로컬 파일(secrets.json)을 찾습니다. (내 컴퓨터 테스트용)
    else:
        try:
            creds = Credentials.from_service_account_file('secrets.json', scopes=scope)
        except FileNotFoundError:
            st.error("🚨 인증 오류: 'secrets.json' 파일도 없고 Streamlit Secrets 설정도 없습니다.")
            st.stop()
        
    gc = gspread.authorize(creds)
    drive = build('drive', 'v3', credentials=creds)
    return gc, drive

def upload_file(drive_service, file_obj):
    if file_obj is None: return ""
    metadata = {'name': file_obj.name, 'parents': [DRIVE_FOLDER_ID]}
    media = MediaIoBaseUpload(file_obj, mimetype=file_obj.type)
    file = drive_service.files().create(body=metadata, media_body=media, fields='webViewLink').execute()
    return file.get('webViewLink')

# ==========================================
# 🛡️ [유효성 검사 및 포맷팅]
# ==========================================
def clean_number(num):
    """숫자만 남기고 다 지움"""
    return re.sub(r'\D', '', str(num))

def format_biz_no(num):
    """숫자 10자리를 000-00-00000 형태로 변환"""
    clean = clean_number(num)
    if len(clean) == 10:
        return f"{clean[:3]}-{clean[3:5]}-{clean[5:]}"
    return num # 실패시 그대로 반환

def format_phone(num):
    """휴대폰 번호에 - 붙이기"""
    clean = clean_number(num)
    if len(clean) == 11: # 01012345678
        return f"{clean[:3]}-{clean[3:7]}-{clean[7:]}"
    elif len(clean) == 10: # 0111234567
        return f"{clean[:3]}-{clean[3:6]}-{clean[6:]}"
    return num

def validate_biz_no(number):
    clean = clean_number(number)
    return len(clean) == 10

def validate_phone(number):
    clean = clean_number(number)
    return len(clean) >= 10 and len(clean) <= 11 and clean.startswith("01")

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

# ==========================================
# 🚀 [앱 메인 로직]
# ==========================================

if 'user_id' not in st.session_state:
    st.session_state['user_id'] = None
    st.session_state['user_name'] = None
    st.session_state['is_approved'] = False

try:
    gc, drive = get_services()
    sh = gc.open(SPREADSHEET_NAME)
    ws_req = sh.worksheet("requests")
    ws_user = sh.worksheet("users")
except Exception as e:
    st.error(f"❌ 구글 연결 오류: {e}")
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
                if str(u.get('아이디')) == lid and str(u.get('비밀번호')) == lpw:
                    st.session_state['user_id'] = lid
                    st.session_state['user_name'] = u.get('이름')
                    status = u.get('승인여부')
                    st.session_state['is_approved'] = (status == "승인" or lid == ADMIN_ID)
                    found = True
                    st.rerun()
            if not found: st.error("정보가 일치하지 않습니다.")

    with tab2:
        st.info("관리자의 승인 후 로그인이 가능합니다.")
        nid = st.text_input("희망 아이디")
        npw = st.text_input("희망 비밀번호", type="password")
        nname = st.text_input("업체명 (이름)")
        
        if st.button("가입 신청"):
            if not (nid and npw and nname):
                st.error("모든 항목을 입력해주세요.")
            else:
                existing = ws_user.col_values(1)
                if nid in existing:
                    st.error("이미 사용 중인 아이디입니다.")
                else:
                    if len(ws_user.get_all_values()) == 0:
                        ws_user.append_row(["아이디", "비밀번호", "이름", "가입일", "승인여부"])
                    ws_user.append_row([nid, npw, nname, datetime.now().strftime("%Y-%m-%d"), "대기"])
                    st.success("✅ 가입 신청 완료! 승인을 기다려주세요.")

# ----------------------------------------------------
# [화면 B] 메인 시스템
# ----------------------------------------------------
else:
    uid = st.session_state['user_id']
    uname = st.session_state['user_name']
    is_approved = st.session_state['is_approved']
    
    col_t1, col_t2 = st.columns([8,2])
    col_t1.subheader(f"👋 {uname}님 환영합니다.")
    if col_t2.button("로그아웃"):
        st.session_state['user_id'] = None
        st.rerun()

    if not is_approved:
        st.divider()
        st.warning("⚠️ 계정 승인 대기 중입니다.")
        st.stop()

    if uid == ADMIN_ID:
        st.divider()
        st.markdown("### 🛠️ 관리자 대시보드")
        adm_tab1, adm_tab2 = st.tabs(["👥 회원 관리", "📝 접수 관리"])
        with adm_tab1:
            u_df = pd.DataFrame(ws_user.get_all_records())
            edited_users = st.data_editor(u_df, num_rows="dynamic", key="uedit")
            if st.button("회원 저장"):
                ws_user.update([edited_users.columns.values.tolist()] + edited_users.values.tolist())
                st.success("저장 완료!")
        with adm_tab2:
            r_df = pd.DataFrame(ws_req.get_all_records())
            edited_req = st.data_editor(r_df, num_rows="dynamic", key="redit")
            if st.button("접수내역 저장"):
                ws_req.update([edited_req.columns.values.tolist()] + edited_req.values.tolist())
                st.success("저장 완료!")

    else:
        st.divider()
        # [관리자 공지사항 표시]
        st.info(ADMIN_NOTICE)
        
        with st.form("register_form"):
            st.markdown("#### 1. 고객사 정보")
            c1, c2 = st.columns(2)
            c_name = c1.text_input("고객사명 (필수)", placeholder="(주)비전엠")
            c_rep = c2.text_input("대표자명 (필수)")
            
            c3, c4 = st.columns(2)
            biz_no_input = c3.text_input("사업자번호 (필수)", placeholder="숫자만 입력 (예: 1234567890)")
            
            ind_options = [
                "건설", "건축(전기/인테리어)", "토목(엔지니어링)", "제조", 
                "자동차", "항공", "금형", "반도체", "철강", "플랜트", 
                "스마트공장", "기타", "공공", "서비스"
            ]
            industry = c4.selectbox("업종 (필수)", ind_options)

            st.markdown("---")
            st.markdown("#### 2. 주소 정보")

# [수정된 주소 검색 코드] 배경색 흰색 지정 + HTTPS 강제
            daum_code = """
            <div style="background-color:white; padding:10px; border-radius:10px;">
                <h4 style="margin-bottom:10px; color:black;">📮 주소 검색</h4>
                <div id="layer" style="display:block;position:relative;overflow:hidden;z-index:1;-webkit-overflow-scrolling:touch; height:300px; border:1px solid #ccc;">
                    <p style="text-align:center; padding-top:100px; color:black;">주소 검색창 로딩 중...</p>
                </div>
                <div id="msg" style="display:none; color:blue; font-weight:bold; margin-top:10px;">
                    ✅ 주소가 복사되었습니다!<br>아래 '기본 주소' 칸에 붙여넣기(Ctrl+V) 하세요.
                </div>
                <textarea id="copy_area" style="position:absolute; left:-9999px;"></textarea>
            </div>
            
            <script src="https://t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js"></script>
            <script>
                new daum.Postcode({
                    oncomplete: function(data) {
                        var addr = data.userSelectedType === 'R' ? data.roadAddress : data.jibunAddress;
                        var extraAddr = '';
                        if(data.userSelectedType === 'R'){
                            if(data.bname !== '' && /[동|로|가]$/g.test(data.bname)) extraAddr += data.bname;
                            if(data.buildingName !== '' && data.apartment === 'Y') extraAddr += (extraAddr !== '' ? ', ' + data.buildingName : data.buildingName);
                            if(extraAddr !== '') extraAddr = ' (' + extraAddr + ')';
                        }
                        var fullAddr = '[' + data.zonecode + '] ' + addr + extraAddr;
                        
                        var copyText = document.getElementById("copy_area");
                        copyText.value = fullAddr;
                        copyText.select();
                        
                        try {
                            document.execCommand('copy');
                            // 검색창 닫고 안내문구 표시
                            document.getElementById('layer').style.display = 'none';
                            document.getElementById('msg').style.display = 'block';
                        } catch (err) {
                            alert('주소: ' + fullAddr + '\\n직접 복사해서 사용하세요.');
                        }
                    },
                    width : '100%',
                    height : '100%'
                }).embed(document.getElementById('layer'));
            </script>
            """
            with st.expander("📮 주소 검색창 열기 (클릭)", expanded=False):
                components.html(daum_code, height=350)

            a1, a2 = st.columns([2, 1])
            addr_full = a1.text_input("기본 주소 (붙여넣기)", placeholder="[12345] 서울시...")
            addr_detail = a2.text_input("상세 주소 (필수)", placeholder="101호")

            st.markdown("---")
            st.markdown("#### 3. 담당자 정보")
            prod = st.radio("제품 (필수)", ["ZWCAD", "ZW3D"], horizontal=True)
            
            m1, m2, m3 = st.columns(3)
            mgr_nm = m1.text_input("담당자명 (필수)")
            mgr_ph_input = m2.text_input("연락처 (필수)", placeholder="숫자만 입력 (예: 01012345678)")
            mgr_em = m3.text_input("이메일 (필수)")

            st.markdown("---")
            st.markdown("#### 4. 첨부파일 (둘 중 하나 필수)")
            col_f1, col_f2 = st.columns(2)
            up_file_biz = col_f1.file_uploader("사업자등록증", type=['png', 'jpg', 'jpeg', 'pdf'])
            up_file_card = col_f2.file_uploader("명함", type=['png', 'jpg', 'jpeg', 'pdf'])
            
            st.markdown("---")
            st.caption("※ 수집된 정보는 ZWPortal 등록 대행을 위해 제3자에게 제공되며, 업무 목적 달성 후 파기됩니다.")
            agree = st.checkbox("✅ [필수] 개인정보 수집 및 제3자 제공에 동의합니다.")

            submit_btn = st.form_submit_button("🚀 등록 접수하기", type="primary")

            if submit_btn:
                err_msgs = []
                # 1. 동의 확인
                if not agree: err_msgs.append("개인정보 동의가 필요합니다.")
                
                # 2. 필수값 체크
                if not (c_name and c_rep and biz_no_input and addr_full and addr_detail and mgr_nm and mgr_ph_input and mgr_em):
                    err_msgs.append("모든 필수 항목을 입력해주세요.")
                
                if not (up_file_biz or up_file_card):
                    err_msgs.append("사업자등록증 또는 명함 중 하나는 반드시 첨부해야 합니다.")

                # 3. 유효성 체크
                if biz_no_input and not validate_biz_no(biz_no_input): 
                    err_msgs.append("사업자번호는 숫자 10자리여야 합니다.")
                if mgr_ph_input and not validate_phone(mgr_ph_input): 
                    err_msgs.append("연락처를 확인해주세요 (010으로 시작하는 숫자)")
                if mgr_em and not validate_email(mgr_em): 
                    err_msgs.append("이메일 형식이 올바르지 않습니다.")

                if err_msgs:
                    for msg in err_msgs: st.error(f"❌ {msg}")
                else:
                    with st.spinner("파일 업로드 및 저장 중..."):
                        try:
                            link_biz = upload_file(drive, up_file_biz) if up_file_biz else ""
                            link_card = upload_file(drive, up_file_card) if up_file_card else ""
                            
                            biz_final = format_biz_no(biz_no_input)
                            ph_final = format_phone(mgr_ph_input)
                            
                            if len(ws_req.get_all_values()) == 0:
                                ws_req.append_row(["시간","작성자","고객사","대표자","사업자","업종","주소(전체)","상세주소","제품","담당자","연락처","이메일","파일(사업자)","파일(명함)","상태"])
                            
                            row = [
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                uid, c_name, c_rep, biz_final, industry, addr_full, addr_detail,
                                prod, mgr_nm, ph_final, mgr_em, 
                                link_biz, link_card, "대기중"
                            ]
                            ws_req.append_row(row)
                            st.success("✅ 접수되었습니다!")
                            st.balloons()
                        except Exception as e:
                            st.error(f"오류: {e}")

        st.divider()
        st.subheader("📋 나의 접수 현황")
        rows = ws_req.get_all_records()
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df[df['작성자'].astype(str) == uid])
        else:
            st.write("내역이 없습니다.")

import streamlit as st
import pandas as pd
import gspread
import re
import requests 
import base64   
import json
import os
import streamlit.components.v1 as components
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime

# ==========================================
# 🚀 [앱 기본 설정]
# ==========================================
st.set_page_config(page_title="VISIONM 파트너스", layout="centered")

# 👇 고객님의 실제 배포 URL (이곳으로 강제 리다이렉트 됩니다)
APP_BASE_URL = "https://visionm.streamlit.app"

# ------------------------------------------
# [핵심 로직] URL 파라미터 감지 및 세션 주입
# ------------------------------------------
# 1. URL에 addr 파라미터가 있는지 확인
if "addr" in st.query_params:
    addr_value = st.query_params["addr"]
    # 2. 주소 입력창의 Key('k_addr_full')에 값을 강제로 주입
    st.session_state['k_addr_full'] = addr_value
    # 3. 처리가 끝났으므로 URL 파라미터 청소
    st.query_params.clear()

# 4. 세션 초기화 (키 에러 방지)
if 'k_addr_full' not in st.session_state:
    st.session_state['k_addr_full'] = ''

# ==========================================
# ⚙️ [사용자 설정]
# ==========================================
SPREADSHEET_NAME = 'ZWCAD_접수대장'
ADMIN_ID = "admin"
GAS_URL = "https://script.google.com/macros/s/AKfycbxtwIB9ENpfl9cDaJ9Ia8wtviHyzhKe-XByN4iCX32Daurbd_-wvkV1KZ-LHq7Qdlh6/exec" 

ADMIN_NOTICE = """
##### 📢 등록 유의사항 안내
1. **사업자등록증** 또는 **명함** 중 하나는 반드시 첨부해야 합니다.
2. 주소는 우편번호 검색을 통해 정확하게 입력해주세요.
3. 입력하신 정보는 ZWPortal 등록 외 다른 용도로 사용되지 않습니다.
"""

# ==========================================
# ☁️ [구글 시트 연결]
# ==========================================
def get_services():
    scope = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    if "google_auth" in st.secrets:
        key_dict = dict(st.secrets["google_auth"])
        creds = Credentials.from_service_account_info(key_dict, scopes=scope)
    else:
        try:
            creds = Credentials.from_service_account_file('secrets.json', scopes=scope)
        except FileNotFoundError:
            st.error("🚨 인증 오류: secrets.json 없음")
            st.stop()
        
    gc = gspread.authorize(creds)
    return gc

# 파일 업로드 함수
def upload_file_to_gas(file_obj, custom_name_prefix):
    if file_obj is None: return ""
    try:
        _, file_extension = os.path.splitext(file_obj.name)
        new_filename = f"{custom_name_prefix}{file_extension}"
        content = file_obj.getvalue()
        b64_data = base64.b64encode(content).decode('utf-8')
        payload = {
            'fileName': new_filename, 
            'mimeType': file_obj.type,
            'fileData': b64_data
        }
        response = requests.post(GAS_URL, data=json.dumps(payload), headers={'Content-Type': 'application/json'})
        res_data = response.json()
        if res_data.get('result') == 'success': return res_data['url']
        else:
            st.error(f"업로드 실패: {res_data.get('error')}")
            return ""
    except Exception as e:
        st.error(f"연결 오류: {str(e)}")
        return ""

# ==========================================
# 🛡️ [유효성 검사 및 포맷팅]
# ==========================================
def clean_number(num): return re.sub(r'\D', '', str(num))
def format_biz_no(num):
    clean = clean_number(num)
    if len(clean) == 10: return f"{clean[:3]}-{clean[3:5]}-{clean[5:]}"
    return num
def format_phone(num):
    clean = clean_number(num)
    length = len(clean)
    if length < 9: return num
    if clean.startswith('02'):
        if length == 9: return f"{clean[:2]}-{clean[2:5]}-{clean[5:]}"
        elif length == 10: return f"{clean[:2]}-{clean[2:6]}-{clean[6:]}"
    else:
        if length == 10: return f"{clean[:3]}-{clean[3:6]}-{clean[6:]}"
        elif length == 11: return f"{clean[:3]}-{clean[3:7]}-{clean[7:]}"
    return num
def validate_biz_no(number): return len(clean_number(number)) == 10
def validate_phone(number): 
    c = clean_number(number)
    return c.startswith("0") and (9 <= len(c) <= 11)
def validate_email(email): return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email) is not None
def has_english_char(text): return bool(re.search(r'[a-zA-Z]', str(text)))

# ==========================================
# 🚀 [앱 메인 로직]
# ==========================================

if 'user_id' not in st.session_state:
    st.session_state['user_id'] = None
    st.session_state['user_name'] = None
    st.session_state['is_approved'] = False

try:
    gc = get_services()
    sh = gc.open(SPREADSHEET_NAME)
    ws_req = sh.worksheet("requests")
    ws_user = sh.worksheet("users")
except Exception as e:
    st.error(f"❌ 구글 연결 오류: {e}")
    st.stop()

if not st.session_state['user_id']:
    st.title("🔒 VISIONM 파트너 로그인")
    tab1, tab2 = st.tabs(["로그인", "회원가입 요청"])
    with tab1:
        lid = st.text_input("아이디", key="login_id")
        lpw = st.text_input("비밀번호", type="password", key="login_pw")
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
        st.subheader("📝 파트너사 가입 신청")
        st.info("관리자 승인 후 로그인이 가능합니다.")
        st.warning("⚠️ 보안을 위해 금융/포털 등에서 사용하는 중요 비밀번호는 피해주세요.")
        
        nid = st.text_input("희망 아이디", key="join_id")
        npw = st.text_input("희망 비밀번호", type="password", key="join_pw")
        nname = st.text_input("업체명 (이름)", key="join_name")
        st.markdown("---")
        st.write("📂 **사업자등록증 또는 명함 첨부 (필수)**")
        join_file = st.file_uploader("증빙 서류 (이미지/PDF)", type=['png', 'jpg', 'jpeg', 'pdf'], key="join_file_upload")
        if st.button("가입 신청"):
            if not (nid and npw and nname and join_file):
                st.error("모든 정보를 입력하고 파일을 첨부해주세요.")
            else:
                existing = ws_user.col_values(1)
                if nid in existing: st.error("이미 존재하는 아이디입니다.")
                else:
                    with st.spinner("가입 서류 업로드 중..."):
                        file_link = upload_file_to_gas(join_file, f"PARTNER_{nid}")
                        if len(ws_user.get_all_values()) == 0: ws_user.append_row(["아이디", "비밀번호", "이름", "가입일", "승인여부", "첨부파일"])
                        ws_user.append_row([nid, npw, nname, datetime.now().strftime("%Y-%m-%d"), "대기", file_link])
                        st.success("✅ 가입 신청이 완료되었습니다! 관리자 승인 대기 중입니다.")
else:
    uid = st.session_state['user_id']
    uname = st.session_state['user_name']
    is_approved = st.session_state['is_approved']
    
    col_t1, col_t2 = st.columns([8,2])
    col_t1.subheader(f"👋 {uname}님 환영합니다.")
    if col_t2.button("로그아웃"):
        st.session_state['user_id'] = None
        if 'k_addr_full' in st.session_state: st.session_state['k_addr_full'] = ''
        st.rerun()

    if not is_approved:
        st.warning("⚠️ 계정 승인 대기 중입니다.")
        st.stop()

    if uid == ADMIN_ID:
        st.markdown("### 🛠️ 관리자 대시보드")
        adm_tab1, adm_tab2 = st.tabs(["👥 회원 관리 (승인)", "📝 접수 대장 관리"])
        with adm_tab1:
            st.info("💡 '첨부파일' 링크를 클릭해 확인 후, '승인여부'를 '대기' ➝ '승인'으로 변경하고 저장하세요.")
            u_df = pd.DataFrame(ws_user.get_all_records())
            edited_users = st.data_editor(
                u_df, num_rows="dynamic", key="uedit",
                column_config={"첨부파일": st.column_config.LinkColumn("증빙서류", display_text="보기"), "승인여부": st.column_config.SelectboxColumn("승인여부", options=["대기", "승인", "거절"], required=True)}
            )
            if st.button("회원 정보 저장"):
                ws_user.update([edited_users.columns.values.tolist()] + edited_users.values.tolist())
                st.success("✅ 회원 정보가 저장되었습니다!")
                st.rerun()
        with adm_tab2:
            r_df = pd.DataFrame(ws_req.get_all_records())
            edited_req = st.data_editor(r_df, num_rows="dynamic", key="redit")
            if st.button("접수내역 저장"):
                ws_req.update([edited_req.columns.values.tolist()] + edited_req.values.tolist())
                st.success("저장 완료!")
    else:
        st.info(ADMIN_NOTICE)
        
        # ---------------------------------------------------------
        # [입력 폼 시작]
        # ---------------------------------------------------------
        with st.form("register_form"):
            st.markdown("#### 1. 고객사 정보")
            c1, c2 = st.columns(2)
            c_name = c1.text_input("고객사명 (필수)", placeholder="예: 비전엠1 (영어 불가)", key="k_c_name")
            c_rep = c2.text_input("대표자명 (필수)", key="k_c_rep")
            
            c3, c4 = st.columns(2)
            biz_no_input = c3.text_input("사업자번호 (필수)", placeholder="숫자만 입력", key="k_biz_no")
            ind_options = ["건설", "건축(전기/인테리어)", "토목(엔지니어링)", "제조", "자동차", "항공", "금형", "반도체", "철강", "플랜트", "스마트공장", "기타", "공공", "서비스"]
            industry = c4.selectbox("업종 (필수)", ind_options, key="k_industry")

            st.markdown("---")
            st.markdown("#### 2. 주소 정보")

            # -----------------------------------------------------
            # [수정됨] 자바스크립트: window.open + _top을 이용한 강력한 리다이렉트
            # -----------------------------------------------------
            # 고객님의 앱 주소로 직접 쏘기 때문에 iframe 보안 이슈가 발생하지 않습니다.
            daum_code = f"""
            <div id="layer" style="display:block; width:100%; height:400px; border:1px solid #333; position:relative"></div>
            <script src="//t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js"></script>
            <script>
                var element_layer = document.getElementById('layer');
                new daum.Postcode({{
                    oncomplete: function(data) {{
                        var addr = ''; 
                        var extraAddr = ''; 
                        if (data.userSelectedType === 'R') {{ 
                            addr = data.roadAddress;
                            if (data.bname !== '' && /[동|로|가]$/g.test(data.bname)) extraAddr += data.bname;
                            if (data.buildingName !== '' && data.apartment === 'Y') extraAddr += (extraAddr !== '' ? ', ' + data.buildingName : data.buildingName);
                            if (extraAddr !== '') extraAddr = ' (' + extraAddr + ')';
                        }} else {{ 
                            addr = data.jibunAddress;
                        }}
                        var fullAddr = '[' + data.zonecode + '] ' + addr + extraAddr;
                        
                        // [최후의 수단] 앱 URL을 하드코딩하여 최상위 윈도우(_top)로 쏴버립니다.
                        // 보안 정책(CORS)을 완전히 무시하고 작동하는 방식입니다.
                        var targetBase = "{APP_BASE_URL}";
                        var finalUrl = targetBase + "?addr=" + encodeURIComponent(fullAddr);
                        
                        window.open(finalUrl, "_top");
                    }},
                    width : '100%',
                    height : '100%',
                    maxSuggestItems : 5
                }}).embed(element_layer);
            </script>
            """
            
            with st.expander("📮 주소 검색창 열기 (클릭)", expanded=False):
                components.html(daum_code, height=410)
            
            a1, a2 = st.columns([2, 1])
            
            # [Key 바인딩] 상단의 session_state['k_addr_full'] 값이 여기에 표시됨
            addr_full = a1.text_input(
                "기본 주소 (자동 입력됨)", 
                placeholder="위 검색창에서 주소를 선택하세요.", 
                key="k_addr_full"
            )
            addr_detail = a2.text_input("상세 주소 (필수)", placeholder="101호", key="k_addr_detail")

            st.markdown("---")
            st.markdown("#### 3. 담당자 정보")
            prod = st.radio("제품 (필수)", ["ZWCAD", "ZW3D"], horizontal=True, key="k_prod")
            m1, m2, m3 = st.columns(3)
            mgr_nm = m1.text_input("담당자명 (필수)", key="k_mgr_nm")
            mgr_ph_input = m2.text_input("연락처 (필수)", placeholder="", key="k_mgr_ph")
            mgr_em = m3.text_input("이메일 (필수)", key="k_mgr_em")

            st.markdown("---")
            st.markdown("#### 4. 첨부파일 (둘 중 하나 필수)")
            col_f1, col_f2 = st.columns(2)
            up_file_biz = col_f1.file_uploader("사업자등록증", type=['png', 'jpg', 'jpeg', 'pdf'], key="k_file_biz")
            up_file_card = col_f2.file_uploader("명함", type=['png', 'jpg', 'jpeg', 'pdf'], key="k_file_card")
            
            st.markdown("---")
            agree = st.checkbox("✅ [필수] 개인정보 수집 및 제3자 제공에 동의합니다.", key="k_agree")
            submit_btn = st.form_submit_button("🚀 등록 접수하기", type="primary")

            if submit_btn:
                err_msgs = []
                if not agree: err_msgs.append("개인정보 동의가 필요합니다.")
                if not (c_name and c_rep and biz_no_input and addr_full and addr_detail and mgr_nm and mgr_ph_input and mgr_em):
                    err_msgs.append("모든 필수 항목을 입력해주세요.")
                if not (up_file_biz or up_file_card): err_msgs.append("사업자등록증 또는 명함 중 하나는 반드시 첨부해야 합니다.")
                if biz_no_input and not validate_biz_no(biz_no_input): err_msgs.append("사업자번호는 숫자 10자리여야 합니다.")
                if mgr_ph_input and not validate_phone(mgr_ph_input): err_msgs.append("연락처 형식을 확인해주세요.")
                if mgr_em and not validate_email(mgr_em): err_msgs.append("이메일 형식이 올바르지 않습니다.")
                
                if has_english_char(c_name):
                    err_msgs.append("고객사명에 영어가 포함되어 있습니다. 한글이나 숫자로 입력해주세요.")

                if err_msgs:
                    for msg in err_msgs: st.error(f"❌ {msg}")
                else:
                    with st.spinner("파일 업로드 및 저장 중..."):
                        try:
                            link_biz = upload_file_to_gas(up_file_biz, f"{c_name}_사업자등록증") if up_file_biz else ""
                            link_card = upload_file_to_gas(up_file_card, f"{c_name}_명함") if up_file_card else ""
                            biz_final = format_biz_no(biz_no_input)
                            ph_final = format_phone(mgr_ph_input)
                            
                            if len(ws_req.get_all_values()) == 0:
                                ws_req.append_row(["시간","작성자","고객사","대표자","사업자","업종","주소(전체)","상세주소","제품","담당자","연락처","이메일","파일(사업자)","파일(명함)","상태"])
                            
                            row = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), uid, c_name, c_rep, biz_final, industry, addr_full, addr_detail, prod, mgr_nm, ph_final, mgr_em, link_biz, link_card, "대기중"]
                            ws_req.append_row(row)
                            st.success("✅ 접수되었습니다!")
                            st.balloons()
                            if 'k_addr_full' in st.session_state: st.session_state['k_addr_full'] = ''
                        except Exception as e:
                            st.error(f"오류: {e}")

        st.divider()
        st.subheader("📋 나의 접수 현황")
        rows = ws_req.get_all_records()
        if rows:
            df = pd.DataFrame(rows)
            if '작성자' in df.columns: st.dataframe(df[df['작성자'].astype(str) == uid])
            else: st.write("데이터 형식이 올바르지 않습니다.")
        else: st.write("내역이 없습니다.")

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
# 🚀 [앱 기본 설정 및 주소 처리]
# ==========================================
st.set_page_config(page_title="VISIONM 파트너스", layout="centered")

# [핵심 로직] 주소 검색 후 URL 파라미터로 돌아왔을 때 값을 잡아내는 부분
# 이 코드는 무조건 맨 위에 있어야 합니다.
if "addr" in st.query_params:
    st.session_state['selected_addr'] = st.query_params["addr"]
    st.session_state['addr_just_updated'] = True # 주소 업데이트 플래그
    st.query_params.clear()

if 'selected_addr' not in st.session_state:
    st.session_state['selected_addr'] = ''

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
# ☁️ [구글 시트 연결 및 함수]
# ==========================================
def get_services():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
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

def upload_file_to_gas(file_obj, custom_name_prefix):
    if file_obj is None: return ""
    try:
        _, file_extension = os.path.splitext(file_obj.name)
        new_filename = f"{custom_name_prefix}{file_extension}"
        content = file_obj.getvalue()
        b64_data = base64.b64encode(content).decode('utf-8')
        payload = {'fileName': new_filename, 'mimeType': file_obj.type, 'fileData': b64_data}
        response = requests.post(GAS_URL, data=json.dumps(payload), headers={'Content-Type': 'application/json'})
        res_data = response.json()
        if res_data.get('result') == 'success': return res_data['url']
        else:
            st.error(f"업로드 실패: {res_data.get('error')}")
            return ""
    except Exception as e:
        st.error(f"연결 오류: {str(e)}")
        return ""

# 유효성 검사 함수들
def clean_number(num): return re.sub(r'\D', '', str(num))
def format_biz_no(num):
    c = clean_number(num)
    return f"{c[:3]}-{c[3:5]}-{c[5:]}" if len(c) == 10 else num
def format_phone(num):
    c = clean_number(num)
    l = len(c)
    if l < 9: return num
    if c.startswith('02'):
        return f"{c[:2]}-{c[2:5]}-{c[5:]}" if l == 9 else f"{c[:2]}-{c[2:6]}-{c[6:]}"
    return f"{c[:3]}-{c[3:6]}-{c[6:]}" if l == 10 else f"{c[:3]}-{c[3:7]}-{c[7:]}"
def validate_biz_no(n): return len(clean_number(n)) == 10
def validate_phone(n): c = clean_number(n); return c.startswith("0") and (9 <= len(c) <= 11)
def validate_email(e): return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', e) is not None
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

# ----------------------------------------------------
# [화면 A] 로그인
# ----------------------------------------------------
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
                    st.session_state['is_approved'] = (u.get('승인여부') == "승인" or lid == ADMIN_ID)
                    found = True
                    st.rerun()
            if not found: st.error("정보가 일치하지 않습니다.")
    with tab2:
        st.subheader("📝 파트너사 가입 신청")

# [안전] 비밀번호 경고 문구

        st.warning("⚠️ 보안을 위해 금융/포털 등에서 사용하는 중요 비밀번호는 피해주세요.")

        nid = st.text_input("희망 아이디", key="join_id")
        npw = st.text_input("희망 비밀번호", type="password", key="join_pw")
        nname = st.text_input("업체명 (이름)", key="join_name")
        st.write("📂 **사업자등록증 또는 명함 첨부 (필수)**")
        join_file = st.file_uploader("증빙 서류", type=['png', 'jpg', 'pdf'], key="join_file_upload")

        if st.button("가입 신청"):
            if not (nid and npw and nname and join_file):
                st.error("입력 정보를 확인하세요.")
            else:
                if nid in ws_user.col_values(1):
                    st.error("이미 존재하는 아이디입니다.")
                else:
                    with st.spinner("처리 중..."):
                        file_link = upload_file_to_gas(join_file, f"PARTNER_{nid}")
                        if len(ws_user.get_all_values()) == 0:
                            ws_user.append_row(["아이디", "비밀번호", "이름", "가입일", "승인여부", "첨부파일"])
                        ws_user.append_row([nid, npw, nname, datetime.now().strftime("%Y-%m-%d"), "대기", file_link])
                        st.success("신청 완료!")

# ----------------------------------------------------
# [화면 B] 메인 시스템
# ----------------------------------------------------
else:
    uid = st.session_state['user_id']
    uname = st.session_state['user_name']
    
    col_t1, col_t2 = st.columns([8,2])
    col_t1.subheader(f"👋 {uname}님 환영합니다.")
    if col_t2.button("로그아웃"):
        st.session_state['user_id'] = None
        st.session_state['selected_addr'] = "" 
        st.rerun()

    if not st.session_state['is_approved']:
        st.warning("⚠️ 계정 승인 대기 중입니다.")
        st.stop()

    if uid == ADMIN_ID:
        st.markdown("### 🛠️ 관리자 대시보드")
        adm_tab1, adm_tab2 = st.tabs(["회원 관리", "접수 관리"])
        with adm_tab1:
            u_df = pd.DataFrame(ws_user.get_all_records())
            edited_users = st.data_editor(u_df, num_rows="dynamic", key="uedit", column_config={"첨부파일": st.column_config.LinkColumn("증빙", display_text="보기"), "승인여부": st.column_config.SelectboxColumn("상태", options=["대기", "승인", "거절"])})
            if st.button("회원 저장"):
                ws_user.update([edited_users.columns.values.tolist()] + edited_users.values.tolist())
                st.success("저장됨")
                st.rerun()
        with adm_tab2:
            r_df = pd.DataFrame(ws_req.get_all_records())
            edited_req = st.data_editor(r_df, num_rows="dynamic", key="redit")
            if st.button("접수 저장"):
                ws_req.update([edited_req.columns.values.tolist()] + edited_req.values.tolist())
                st.success("저장됨")
    else:
        st.info(ADMIN_NOTICE)
        
        # ---------------------------------------------------------
        # 🟢 등록 폼 시작 (순서 변경: 고객정보 -> 파일 -> 주소 -> 담당자)
        # ---------------------------------------------------------
        with st.form("register_form"):
            st.markdown("#### 1. 고객사 정보")
            c1, c2 = st.columns(2)
            c_name = c1.text_input("고객사명 (필수)", placeholder="예: 비전엠1 (영어 불가)", key="k_c_name")
            c_rep = c2.text_input("대표자명 (필수)", key="k_c_rep")
            
            # 📍 [요청반영] 대표자명 입력 직후 이미지 업로드 섹션 배치
            st.markdown("---")
            st.markdown("#### 📂 증빙서류 업로드 (필수)")
            st.caption("사업자등록증 또는 명함 중 하나는 반드시 첨부해야 합니다.")
            col_f1, col_f2 = st.columns(2)
            up_file_biz = col_f1.file_uploader("사업자등록증", type=['png', 'jpg', 'pdf'], key="k_file_biz")
            up_file_card = col_f2.file_uploader("명함", type=['png', 'jpg', 'pdf'], key="k_file_card")

            st.markdown("---")
            c3, c4 = st.columns(2)
            biz_no_input = c3.text_input("사업자번호", placeholder="숫자만 입력", key="k_biz_no")
            industry = c4.selectbox("업종", ["건설", "건축", "토목", "제조", "자동차", "항공", "기타"], key="k_industry")

            st.markdown("---")
            st.markdown("#### 2. 주소 정보")

            # -----------------------------------------------------
            # 💡 [필살기] 보안 정책 우회를 위한 iframe + Link Target 방식
            # -----------------------------------------------------
            daum_code = """
            <style>
                body { margin: 0; padding: 0; font-family: sans-serif; }
                .success-box { display: none; text-align: center; padding: 20px; background: #e6fffa; border: 2px solid #38b2ac; border-radius: 10px; }
                .success-box h3 { margin: 0 0 10px 0; color: #234e52; }
                .btn-apply {
                    display: inline-block; padding: 12px 24px; background-color: #319795; color: white;
                    text-decoration: none; font-weight: bold; border-radius: 6px; font-size: 16px;
                    transition: background 0.2s; cursor: pointer;
                }
                .btn-apply:hover { background-color: #285e61; }
            </style>
            
            <div id="layer" style="display:block; width:100%; height:400px; border:1px solid #ddd;"></div>
            
            <div id="result" class="success-box">
                <h3>✅ 주소가 선택되었습니다!</h3>
                <p>아래 버튼을 눌러야 입력창에 적용됩니다.</p>
                <a id="apply_link" href="#" target="_top" class="btn-apply">👉 주소 입력 적용하기 (클릭)</a>
            </div>

            <script src="//t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js"></script>
            <script>
                var element_layer = document.getElementById('layer');
                var element_result = document.getElementById('result');
                var link_btn = document.getElementById('apply_link');

                new daum.Postcode({
                    oncomplete: function(data) {
                        var addr = ''; 
                        var extraAddr = ''; 
                        if (data.userSelectedType === 'R') { 
                            addr = data.roadAddress;
                            if (data.bname !== '' && /[동|로|가]$/g.test(data.bname)) extraAddr += data.bname;
                            if (data.buildingName !== '' && data.apartment === 'Y') extraAddr += (extraAddr !== '' ? ', ' + data.buildingName : data.buildingName);
                            if (extraAddr !== '') extraAddr = ' (' + extraAddr + ')';
                        } else { 
                            addr = data.jibunAddress;
                        }
                        var fullAddr = '[' + data.zonecode + '] ' + addr + extraAddr;

                        // [중요] 부모 창(앱)의 URL을 찾아서 파라미터 추가
                        // document.referrer는 iframe을 포함하고 있는 부모 페이지의 주소입니다.
                        var parentUrl = document.referrer;
                        if (!parentUrl || parentUrl === "") {
                            // 로컬 테스트 등 referrer가 없을 경우를 대비한 방어 코드
                            parentUrl = window.location.ancestorOrigins[0];
                        }
                        
                        // 기존 파라미터 제거 후 addr 추가
                        var baseUrl = parentUrl.split('?')[0];
                        var finalUrl = baseUrl + "?addr=" + encodeURIComponent(fullAddr);
                        
                        // 링크에 주소 심기
                        link_btn.href = finalUrl;
                        
                        // 1. 레이어 숨기고 버튼 보여주기
                        element_layer.style.display = 'none';
                        element_result.style.display = 'block';
                        
                        // 2. 편의를 위해 버튼 자동 클릭 시도 (브라우저가 허용하면 자동 적용됨)
                        link_btn.click();
                    },
                    width : '100%',
                    height : '100%',
                    maxSuggestItems : 5
                }).embed(element_layer);
            </script>
            """
            
            # 주소 검색창 Expander
            with st.expander("📮 주소 검색창 열기 (클릭)", expanded=False):
                components.html(daum_code, height=420)
            
            a1, a2 = st.columns([2, 1])
            
            # [값 바인딩] session_state에 저장된 값을 value에 할당
            addr_val = st.session_state.get('selected_addr', '')
            addr_full = a1.text_input("기본 주소 (자동 입력됨)", value=addr_val, disabled=True, key="k_addr_display")
            # 실제 Form Submit용 데이터는 hidden으로 처리하거나 그냥 위 disabled 값 사용
            
            addr_detail = a2.text_input("상세 주소 (필수)", placeholder="101호", key="k_addr_detail")

            st.markdown("---")
            st.markdown("#### 3. 담당자 정보")
            prod = st.radio("제품", ["ZWCAD", "ZW3D"], horizontal=True, key="k_prod")
            m1, m2, m3 = st.columns(3)
            mgr_nm = m1.text_input("담당자명", key="k_mgr_nm")
            mgr_ph_input = m2.text_input("연락처", key="k_mgr_ph")
            mgr_em = m3.text_input("이메일", key="k_mgr_em")

            st.markdown("---")
            agree = st.checkbox("✅ 개인정보 수집 동의", key="k_agree")
            submit_btn = st.form_submit_button("🚀 등록 접수하기", type="primary")

            if submit_btn:
                err_msgs = []
                if not agree: err_msgs.append("개인정보 동의가 필요합니다.")
                if not (c_name and c_rep and biz_no_input and addr_full and addr_detail and mgr_nm and mgr_ph_input and mgr_em):
                    err_msgs.append("모든 필수 항목을 입력해주세요.")
                if not (up_file_biz or up_file_card): err_msgs.append("사업자등록증/명함 중 하나는 필수입니다.")
                if biz_no_input and not validate_biz_no(biz_no_input): err_msgs.append("사업자번호 10자리를 확인하세요.")
                if has_english_char(c_name): err_msgs.append("고객사명에 영어가 포함됨.")

                if err_msgs:
                    for msg in err_msgs: st.error(f"❌ {msg}")
                else:
                    with st.spinner("저장 중..."):
                        try:
                            l_biz = upload_file_to_gas(up_file_biz, f"{c_name}_사업자") if up_file_biz else ""
                            l_card = upload_file_to_gas(up_file_card, f"{c_name}_명함") if up_file_card else ""
                            
                            row = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), uid, c_name, c_rep, format_biz_no(biz_no_input), industry, addr_full, addr_detail, prod, mgr_nm, format_phone(mgr_ph_input), mgr_em, l_biz, l_card, "대기중"]
                            
                            if len(ws_req.get_all_values()) == 0:
                                ws_req.append_row(["시간","작성자","고객사","대표자","사업자","업종","주소","상세","제품","담당자","연락처","이메일","파일1","파일2","상태"])
                            
                            ws_req.append_row(row)
                            st.success("✅ 접수 완료!")
                            st.balloons()
                            st.session_state['selected_addr'] = "" # 초기화
                        except Exception as e:
                            st.error(f"오류: {e}")

        st.divider()
        rows = ws_req.get_all_records()
        if rows:
            df = pd.DataFrame(rows)
            if '작성자' in df.columns: st.dataframe(df[df['작성자'].astype(str) == uid])

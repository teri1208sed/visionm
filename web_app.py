import streamlit as st
import pandas as pd
import gspread
import re
import requests 
import base64   
import json
import os
import time
import streamlit.components.v1 as components
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime

# ==========================================
# 🚀 [앱 기본 설정]
# ==========================================
st.set_page_config(page_title="VISIONM 파트너스", layout="centered")

# 👇 고객님의 실제 배포 URL (정확해야 합니다)
APP_BASE_URL = "https://visionm.streamlit.app"

# ==========================================
# 🚫 [보안 & 디자인] 헤더, 푸터, 뷰어 배지 완벽 제거 (Data-Test-ID 기반)
# ==========================================
hide_final_style = """
    <style>
    /* 1. [핵심] 스크린샷에 나온 'data-testid' 속성을 직접 타격하여 숨김 */
    [data-testid="stStatusWidget"],       /* 우측 상단/하단 상태 위젯 */
    [data-testid="appCreatorAvatar"],     /* 스크린샷의 프로필 이미지 */
    [data-testid="manageAppButton"],      /* 앱 관리 버튼 */
    [data-testid="stToolbar"],            /* 실행 툴바 */
    [data-testid="stDecoration"],         /* 상단 데코레이션 바 */
    [data-testid="stHeader"]              /* 헤더 전체 */
    {
        display: none !important;
        visibility: hidden !important;
        height: 0px !important;
        opacity: 0 !important;
        pointer-events: none !important;
    }

    /* 2. 뷰어 배지 및 프로필 컨테이너 (클래스 이름 와일드카드) */
    div[class*="viewerBadge"],            /* 'viewerBadge'가 포함된 모든 div */
    div[class*="_profileContainer"],      /* '_profileContainer'가 포함된 모든 div */
    div[class*="_profilePreview"]         /* '_profilePreview'가 포함된 모든 div */
    {
        display: none !important;
        visibility: hidden !important;
    }

    /* 3. Streamlit Cloud 상태 표시 아이프레임 */
    iframe[title="Streamlit Cloud Status"] {
        display: none !important;
        width: 0px !important;
    }

    /* 4. 푸터 숨기기 */
    footer {
        display: none !important;
    }

    /* 5. 콘텐츠 여백 제거 */
    .block-container {
        padding-top: 0rem !important;
    }
    
    /* 6. 혹시 모를 상단 헤더 투명화 */
    header {
        background-color: transparent !important;
    }
    </style>
"""
st.markdown(hide_final_style, unsafe_allow_html=True)
# ------------------------------------------
# [핵심 로직] URL 파라미터 감지 및 세션 주입
# ------------------------------------------
if "addr" in st.query_params:
    # 파라미터를 직접 k_addr_full에 넣지 않고 임시 키에 저장
    st.session_state['k_addr_temp'] = st.query_params["addr"]
    st.query_params.clear()
    # 파라미터가 있을 때만 리런 (무한 루프 방지)
    st.rerun()

# k_addr_full 초기화
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
            st.markdown("##### 📝 접수 대장 실시간 관리")
            st.info("💡 여기서 '상태'를 변경하고 저장하면, PC 프로그램에도 즉시 반영됩니다.")
            
            # 데이터 로드
            current_data = ws_req.get_all_records()
            r_df = pd.DataFrame(current_data)
            
            # 데이터 에디터 설정 (상태 변경 편의성 증대)
            column_config = {
                "상태": st.column_config.SelectboxColumn(
                    "상태",
                    options=["대기중", "접수대기", "등록진행중", "승인대기", "승인", "반려", "타업체선순위", "오류"],
                    required=True
                ),
                "파일(사업자)": st.column_config.LinkColumn("사업자증", display_text="보기"),
                "파일(명함)": st.column_config.LinkColumn("명함", display_text="보기"),
            }
            
            edited_req = st.data_editor(
                r_df, 
                num_rows="dynamic", 
                key="redit", 
                column_config=column_config,
                use_container_width=True
            )
            
            if st.button("접수내역 저장 (동기화)"):
                with st.spinner("구글 시트에 저장 중..."):
                    try:
                        # 1. 데이터프레임의 NaN 값을 빈 문자열로 변환 (오류 방지)
                        edited_req = edited_req.fillna("")
                        
                        # 2. 헤더(컬럼명)와 값 분리
                        header = edited_req.columns.values.tolist()
                        data = edited_req.values.tolist()
                        
                        # 3. 시트 클리어 후 다시 쓰기 (가장 확실한 동기화 방법)
                        ws_req.clear()
                        ws_req.append_row(header)
                        ws_req.append_rows(data)
                        
                        st.success("✅ 저장이 완료되었습니다! PC 프로그램에서 '새로고침'을 누르면 반영됩니다.")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"저장 중 오류 발생: {e}")
                        
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
            # [Daum 주소 검색]
            # -----------------------------------------------------
            daum_code = f"""
            <div id="wrapper" style="width:100%; height:400px; position:relative; background-color:#fff;">
                <div id="layer" style="display:block; width:100%; height:100%; border:1px solid #ddd; -webkit-overflow-scrolling:touch;"></div>
                
                <div id="result_layer" style="display:none; position:absolute; top:0; left:0; width:100%; height:100%; background-color:#fff; z-index:999; flex-direction:column; justify-content:center; align-items:center; text-align:center;">
                    <h3 style="color:#333; margin-bottom:10px;">✅ 주소 선택 완료!</h3>
                    
                    <textarea id="addr_text" readonly style="
                        width: 80%;
                        height: 60px;
                        background: #f8f9fa;
                        border: 1px solid #ddd;
                        border-radius: 5px;
                        padding: 10px;
                        margin-bottom: 20px;
                        font-size: 14px;
                        resize: none;
                        text-align: center;
                    "></textarea>
                    
                    <a id="apply_btn" href="#" target="_blank" style="
                        text-decoration: none;
                        background-color: #FF4B4B;
                        color: white;
                        padding: 12px 24px;
                        border-radius: 5px;
                        font-weight: bold;
                        font-size: 16px;
                        display: inline-block;
                        margin-bottom: 10px;
                        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                    ">
                        🚀 주소 적용하기 (새창)
                    </a>
                    
                    <button onclick="copyToClipboard()" style="
                        background-color: #333;
                        color: white;
                        padding: 10px 20px;
                        border: none;
                        border-radius: 5px;
                        font-size: 14px;
                        cursor: pointer;
                        display: block;
                        margin-top: 5px;
                    ">
                        📋 주소 복사하기
                    </button>
                    
                    <p style="margin-top:15px; font-size:12px; color:#666;">
                        * 보안 정책상 새 창이 열리며 적용됩니다.<br>
                        * 새 창이 불편하시면 [복사] 후 직접 붙여넣으세요.
                    </p>

                    <button onclick="retrySearch()" style="margin-top:20px; background:none; border:none; color:#999; text-decoration:underline; cursor:pointer;">다시 검색</button>
                </div>
            </div>

            <script src="//t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js"></script>
            <script>
                var element_layer = document.getElementById('layer');
                var result_layer = document.getElementById('result_layer');
                var addr_text = document.getElementById('addr_text');
                var apply_btn = document.getElementById('apply_btn');
                
                function retrySearch() {{
                    result_layer.style.display = 'none';
                    element_layer.style.display = 'block';
                }}
                
                function copyToClipboard() {{
                    addr_text.select();
                    document.execCommand('copy');
                    alert('주소가 복사되었습니다! 입력창에 붙여넣기(Ctrl+V) 하세요.');
                }}

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

                        // URL 생성
                        var targetBase = "{APP_BASE_URL}";
                        var separator = targetBase.includes('?') ? '&' : '?';
                        var finalUrl = targetBase + separator + "addr=" + encodeURIComponent(fullAddr);

                        // UI 전환
                        element_layer.style.display = 'none';
                        result_layer.style.display = 'flex';
                        
                        // 데이터 바인딩
                        addr_text.value = fullAddr;
                        apply_btn.href = finalUrl;
                    }},
                    width : '100%',
                    height : '100%',
                    maxSuggestItems : 5
                }}).embed(element_layer);
            </script>
            """
            
            with st.expander("📮 주소 검색창 열기 (클릭)", expanded=False):
                components.html(daum_code, height=410)
            
            # -----------------------------------------------------
            # [핵심 로직] 임시 변수 -> 실제 위젯 키로 값 이동
            # (반드시 위젯 생성 직전에 수행해야 함)
            # -----------------------------------------------------
            if 'k_addr_temp' in st.session_state and st.session_state['k_addr_temp']:
                st.session_state['k_addr_full'] = st.session_state['k_addr_temp']
                del st.session_state['k_addr_temp']  # 임시 변수 삭제

            a1, a2 = st.columns([2, 1])
            
            # [Key 바인딩] session_state에 값이 있으면 자동으로 채워짐
            addr_full = a1.text_input(
                "기본 주소 (위의주소를 복사 붙여넣기필요)", 
                placeholder="검색 후 '적용하기'를 누르세요.", 
                key="k_addr_full"
            )
            addr_detail = a2.text_input("상세 주소 (필수)", placeholder="없으면 점(.)기입", key="k_addr_detail")

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

"""실행: streamlit run app.py
GitHub 저장소에 app.py와 requirements.txt를 올린 뒤 Streamlit Community
Cloud에서 app.py를 실행 파일로 지정하세요. Python 3.11 이상을 권장합니다.
외부 DB/메일 설정이 필요 없는 세션 저장 버전입니다.
"""
import calendar
import json
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st


def add_months(value: date, months: int) -> date:
    """달력 기준 월 더하기. 해당 일이 없으면 그 달의 말일 사용."""
    index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def dates_for(item: dict):
    expiration = add_months(date.fromisoformat(item['purchased']), item['months'])
    return expiration, add_months(expiration, -1)


def status_for(item: dict, today: date):
    expiration, reminder = dates_for(item)
    remaining = (expiration - today).days
    if remaining < 0:
        return '🔴 기한 경과', remaining
    if remaining == 0:
        return '🔴 오늘 만료', remaining
    if today >= reminder:
        return '🟠 교체 준비', remaining
    return '🟢 사용 중', remaining


def parse_backup(raw: bytes):
    if len(raw) > 2_000_000:
        raise ValueError('백업은 2MB 이하만 지원합니다.')
    data = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1:
        raise ValueError('지원하지 않는 백업 형식입니다.')
    items = data.get('items')
    if not isinstance(items, list) or len(items) > 1000:
        raise ValueError('제품 목록이 올바르지 않거나 1,000개를 초과합니다.')
    cleaned, seen = [], set()
    for entry in items:
        if not isinstance(entry, dict):
            raise ValueError('제품 정보 형식이 올바르지 않습니다.')
        name, kind = entry.get('name'), entry.get('kind')
        if not isinstance(name, str) or not name.strip() or len(name) > 60:
            raise ValueError('제품 이름을 확인해 주세요(1~60자).')
        if not isinstance(kind, str) or not kind.strip() or len(kind) > 30:
            raise ValueError('제품 유형을 확인해 주세요(1~30자).')
        price, months = entry.get('price'), entry.get('months')
        if type(price) is not int or not 0 <= price <= 1_000_000_000:
            raise ValueError('가격 범위가 올바르지 않습니다.')
        if type(months) is not int or not 1 <= months <= 600:
            raise ValueError('사용 기간은 1~600개월이어야 합니다.')
        purchased = date.fromisoformat(entry['purchased'])
        if not date(1900, 1, 1) <= purchased <= date(2100, 12, 31):
            raise ValueError('구매일 범위가 올바르지 않습니다.')
        identifier = entry.get('id')
        if not isinstance(identifier, str) or not identifier or len(identifier) > 64 or identifier in seen:
            identifier = str(uuid.uuid4())
        seen.add(identifier)
        cleaned.append(dict(id=identifier, name=name.strip(), kind=kind.strip(),
                            price=price, months=months, purchased=purchased.isoformat()))
    return cleaned


st.set_page_config(page_title='가전 수명 알리미', page_icon='🔔', layout='wide', initial_sidebar_state='collapsed')
st.markdown('''<style>
.block-container {padding-top:1.3rem; padding-bottom:1rem; max-width:1280px;}
h1 {font-size:1.65rem !important; padding-top:0 !important;}
[data-testid="stMetricValue"] {font-size:1.5rem;}
[data-testid="stVerticalBlock"] {gap:.6rem;}
</style>''', unsafe_allow_html=True)

if 'items' not in st.session_state:
    st.session_state['items'] = []
if 'notice' in st.session_state:
    st.toast(st.session_state.pop('notice'), icon='✅')
items = st.session_state['items']
today = datetime.now(ZoneInfo('Asia/Seoul')).date()

st.title('🔔 가전 수명 알리미')
st.caption('구매일 + 사용 기간 → 만료일 자동 계산 · 만료 1개월 전부터 접속 시 알림 · 한국 시간 기준')

left, right = st.columns([1, 2], gap='large')
with left:
    st.subheader('제품 등록')
    with st.form('new_product', clear_on_submit=False):
        a, b = st.columns(2)
        kind = a.selectbox('유형', ['주방가전', '생활가전', '계절가전', '영상·음향', '미용·건강', '기타'])
        name = b.text_input('가전제품 이름', placeholder='예: 거실 공기청정기', max_chars=60)
        a, b = st.columns(2)
        price = a.number_input('구매 가격(원)', min_value=0, max_value=1_000_000_000, value=0, step=10000, format='%d')
        purchased = b.date_input('구매일', value=today, min_value=date(1900, 1, 1), max_value=today, format='YYYY/MM/DD')
        months = st.number_input('사용 기간(개월)', min_value=1, max_value=600, value=60, step=12,
                                 help='예: 1년=12, 3년=36, 5년=60개월. 월 단위로 직접 입력할 수 있습니다.')
        submitted = st.form_submit_button('＋ 등록하기', type='primary', use_container_width=True)
        st.caption('입력 후 등록하면 계산 결과가 오른쪽 목록에 나타납니다.')
    if submitted:
        if not name.strip():
            st.warning('제품 이름을 입력해 주세요.')
        elif len(items) >= 1000:
            st.warning('최대 1,000개까지 등록할 수 있습니다.')
        else:
            items.append(dict(id=str(uuid.uuid4()), kind=kind, name=name.strip(), price=int(price),
                              purchased=purchased.isoformat(), months=int(months)))
            st.session_state['notice'] = '등록했습니다. 기록을 보관하려면 백업을 내려받으세요.'
            st.rerun()
    st.caption('※ 가전의 공식 유통기한이 아닌, 직접 정한 점검·교체 예정일입니다.')

with right:
    due = [i for i in items if today >= dates_for(i)[1]]
    expired = sum(dates_for(i)[0] < today for i in items)
    a, b, c = st.columns(3)
    a.metric('등록 제품', f'{len(items)}개')
    b.metric('알림 대상', f'{len(due)}개')
    c.metric('기한 경과', f'{expired}개')
    if due:
        labels = ', '.join(i['name'] for i in sorted(due, key=lambda i: dates_for(i)[0])[:3])
        suffix = f' 외 {len(due) - 3}개' if len(due) > 3 else ''
        st.warning(f'🔔 점검·교체를 확인하세요: {labels}{suffix}')
    else:
        st.info('현재 알림 대상이 없습니다. 만료 1개월 전부터 여기에 안내합니다.')
    rows = []
    for item in sorted(items, key=lambda i: dates_for(i)[0]):
        expiration, reminder = dates_for(item)
        status, remaining = status_for(item, today)
        rows.append({'상태': status, '유형': item['kind'], '제품명': item['name'],
                     '가격(원)': item['price'], '구매일': item['purchased'], '기간(개월)': item['months'],
                     '만료일': expiration.isoformat(), '알림 시작': reminder.isoformat(),
                     '남은 일수': remaining})
    columns = ['상태', '유형', '제품명', '가격(원)', '구매일', '기간(개월)', '만료일', '알림 시작', '남은 일수']
    st.dataframe(pd.DataFrame(rows, columns=columns), hide_index=True, height=230, use_container_width=True,
                 column_config={'가격(원)': st.column_config.NumberColumn(format='%d'),
                                '남은 일수': st.column_config.NumberColumn(help='음수는 기한 경과 일수입니다.')})
    with st.expander('🗂 백업 · 복원 · 삭제'):
        payload = json.dumps({'version': 1, 'items': items}, ensure_ascii=False, indent=2)
        st.download_button('JSON 백업 다운로드', data=payload.encode('utf-8'),
                           file_name=f'appliances_{today.isoformat()}.json', mime='application/json')
        uploaded = st.file_uploader('백업 파일 복원(JSON)', type=['json'])
        st.caption('복원은 기존 목록에 추가하지 않고 전체 교체합니다.')
        confirm_restore = st.checkbox('현재 목록을 백업 내용으로 교체하는 데 동의합니다.')
        if st.button('백업 복원', disabled=uploaded is None or not confirm_restore):
            try:
                restored = parse_backup(uploaded.getvalue())
            except (ValueError, KeyError, TypeError, OverflowError, UnicodeError):
                st.error('백업을 읽지 못했습니다. 이 앱에서 내려받은 정상 JSON 파일인지 확인해 주세요.')
            else:
                st.session_state['items'] = restored
                st.session_state['notice'] = f'{len(restored)}개 제품을 복원했습니다.'
                st.rerun()
        if items:
            choices = {i['id']: f"{i['name']} · {i['purchased']} · {i['id'][:6]}" for i in items}
            selected = st.selectbox('삭제할 제품', list(choices), format_func=choices.get)
            confirm_delete = st.checkbox('선택한 제품을 삭제합니다.')
            if st.button('선택 제품 삭제', disabled=not confirm_delete):
                st.session_state['items'] = [i for i in items if i['id'] != selected]
                st.session_state['notice'] = '선택한 제품을 삭제했습니다.'
                st.rerun()

st.caption('저장 안내: 기록은 현재 접속 세션에만 보관됩니다. 새로고침·세션 종료 시 사라질 수 있으니 등록 후 JSON 백업을 저장하세요. '
           '앱을 닫은 동안의 이메일·푸시·예약 알림은 제공하지 않습니다. 작은 화면에서는 스크롤이 발생할 수 있습니다.')

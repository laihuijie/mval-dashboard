"""
东莞二区 中高客单城商 M值看板 v3
单Tab布局：
  板块1 — 汇总表（城市/联络点：基期M值、当前M值、M值DOD、新阶梯/免配/商承4元覆盖率）红黄绿着色
  板块2 — 日均M值趋势折线图
  板块3 — BD商家明细（按BD分Tab，M值四档筛选，播报生成）
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import warnings, tempfile, os, zipfile, re, glob
warnings.filterwarnings('ignore')

st.set_page_config(
    page_title="常平联络点M值看板",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── 主色调 ──────────────────────────────────────────────────────────
BLUE_DARK  = '#1565C0'
BLUE_MAIN  = '#1E90FF'
BLUE_LIGHT = '#EEF6FF'

st.markdown("""
<style>
/* 整体背景 */
[data-testid="stAppViewContainer"] { background:#f7f9fc; }
[data-testid="stMain"] > div { padding-top: 1.2rem; }

/* 侧边栏样式 */
[data-testid="stSidebar"] {
    background: #1a2744 !important;
}
[data-testid="stSidebar"] > div:first-child {
    background: #1a2744 !important;
    padding-top: 1rem;
}
[data-testid="stSidebar"] * { color: #cfe2ff !important; font-size:0.82rem !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color:#fff !important; font-size:0.9rem !important; }
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
    background: rgba(255,255,255,0.08) !important;
    border: 1.5px dashed rgba(255,255,255,0.35) !important;
    border-radius: 8px !important;
}

/* 主标题 */
h1 { color: #1a2744 !important; font-size:1.6rem !important; font-weight:800 !important; margin-bottom:4px; }

/* 板块标题按钮 */
.section-btn {
    display: inline-block;
    background: #1a2744;
    color: white !important;
    font-size: 0.95rem; font-weight: 700;
    padding: 8px 20px; border-radius: 8px;
    margin: 14px 0 10px 0;
    letter-spacing: 0.3px;
}

/* 隐藏 streamlit 默认顶栏 */
#MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ─── 工具函数 ─────────────────────────────────────────────────────────
def parse_delta(val):
    if pd.isna(val): return float('nan')
    s = str(val).replace('pp','').replace('PP','').replace('%','').strip()
    try: return float(s) / 100
    except: return float('nan')

def fix_xlsx(src_path):
    tmpdir = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(src_path,'r') as z: z.extractall(tmpdir)
    except: return src_path
    for wf in glob.glob(tmpdir+'/xl/worksheets/*.xml'):
        try:
            with open(wf,'r',encoding='utf-8',errors='replace') as f: c = f.read()
            c2 = re.sub(r'<autoFilter[^>]*/>'       ,'',c)
            c2 = re.sub(r'<autoFilter[^>]*>.*?</autoFilter>'          ,'',c2,flags=re.DOTALL)
            c2 = re.sub(r'<dataValidations[^>]*>.*?</dataValidations>','',c2,flags=re.DOTALL)
            if c2 != c:
                with open(wf,'w',encoding='utf-8') as f: f.write(c2)
        except: pass
    out = os.path.join(tempfile.mkdtemp(),'fixed.xlsx')
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for root,dirs,files in os.walk(tmpdir):
            for file in files:
                fp = os.path.join(root,file)
                z.write(fp, os.path.relpath(fp,tmpdir))
    return out

def dedup_cols(df):
    seen={}; nc=[]
    for col in df.columns:
        s=str(col)
        if s in seen: seen[s]+=1; nc.append(f"{s}_{seen[s]}")
        else: seen[s]=0; nc.append(s)
    df.columns=nc; return df

def to_num(v):
    try: return float(v)
    except: return float('nan')

@st.cache_data
def load_data(path):
    data={}
    try:
        fixed=fix_xlsx(path)
        xl=pd.ExcelFile(fixed)

        # ── 看板 sheet → 汇总表 ──────────────────────────
        # 数据列位置（0-indexed，对应Excel列字母）：
        #   C(2)=联络点/BD名, D(3)=基期M值, E(4)=当前M值, F(5)=ΔM
        #   J(9)=免配覆盖率, M(12)=商承4元覆盖率, P(15)=新阶梯覆盖率
        raw=pd.read_excel(fixed,sheet_name='看板',header=None)
        TARGET_NAMES = ['东莞常平联络点','邹锦宏','黄梓豪','程鑫','莫东怡',
                        '黄少隆','彭臻杰','袁瀚枢','李文兵']
        BOARD_COLS = {
            '联络点/BD':   2,
            '基期M值':     3,
            '当前M值':     4,
            'ΔM':          5,
            '免配覆盖率':  9,
            '商承4元覆盖率': 12,
            '新阶梯覆盖率': 15,
        }
        rows=[]
        for i in range(len(raw)):
            name = str(raw.iloc[i, 2]) if pd.notna(raw.iloc[i, 2]) else ''
            if name not in TARGET_NAMES: continue
            r = {}
            for cn, idx in BOARD_COLS.items():
                if cn == '联络点/BD':
                    r[cn] = name   # 直接用字符串，不经过 to_num
                else:
                    r[cn] = to_num(raw.iloc[i, idx]) if idx < raw.shape[1] else float('nan')
            rows.append(r)
        # 按TARGET_NAMES顺序排列
        df_rows = pd.DataFrame(rows) if rows else pd.DataFrame()
        if not df_rows.empty:
            df_rows['_order'] = df_rows['联络点/BD'].apply(
                lambda x: TARGET_NAMES.index(x) if x in TARGET_NAMES else 99)
            df_rows = df_rows.sort_values('_order').drop(columns='_order').reset_index(drop=True)
        data['board'] = df_rows

        # ── 日均 sheet → 一周走势折线图 ──────────────────────────
        # 结构：行0=日期标签(col2=22,col5=23..col12=31), 行1=字段名, 行2+=数据
        # 数据：col2=基期M值, col4~col12=各日提升值(ΔM相对基期)
        # 目标行：东莞常平联络点及各BD（col1=区域, col2=架构/名称）
        raw_d=pd.read_excel(fixed,sheet_name='日均',header=None)

        # 解析日期标签行(行0)，找有效日期列（排除走势/VS列）
        date_row = raw_d.iloc[0].tolist()
        date_cols=[]
        for j, v in enumerate(date_row):
            if j < 4: continue   # 前4列是区域/架构/基期/当前，跳过
            sv = str(v) if pd.notna(v) else ''
            if sv in ('','nan') or '走势' in sv or 'VS' in sv: continue
            try:
                int(float(sv))  # 必须是数字日期
                date_cols.append((j, f"3/{int(float(sv))}"))
            except: continue
        data['date_cols'] = date_cols

        TREND_NAMES = ['东莞常平联络点','邹锦宏','黄梓豪','程鑫','莫东怡',
                       '黄少隆','彭臻杰','袁瀚枢','李文兵']
        trend_rows=[]
        for i in range(len(raw_d)):
            name = str(raw_d.iloc[i, 1]) if pd.notna(raw_d.iloc[i, 1]) else ''
            if name not in TREND_NAMES: continue
            base_m = to_num(raw_d.iloc[i, 2])
            r = {'联络点': name, '基期M值': base_m}
            for j, dlabel in date_cols:
                delta = to_num(raw_d.iloc[i, j]) if j < raw_d.shape[1] else float('nan')
                # 实际M值 = 基期M值 + 当日ΔM
                r[dlabel] = (base_m + delta) if (pd.notna(base_m) and pd.notna(delta)) else float('nan')
            trend_rows.append(r)
        # 按顺序排列
        df_trend_raw = pd.DataFrame(trend_rows) if trend_rows else pd.DataFrame()
        if not df_trend_raw.empty:
            df_trend_raw['_order'] = df_trend_raw['联络点'].apply(
                lambda x: TREND_NAMES.index(x) if x in TREND_NAMES else 99)
            df_trend_raw = df_trend_raw.sort_values('_order').drop(columns='_order').reset_index(drop=True)
        data['trend'] = df_trend_raw

        # ── 商家明细 sheet ──────────────────────────────
        if '商家明细' in xl.sheet_names:
            df_mx=pd.read_excel(fixed,sheet_name='商家明细',header=0)
            df_mx=dedup_cols(df_mx)
            if str(df_mx.iloc[0,0])=='日期': df_mx=df_mx.iloc[1:].reset_index(drop=True)
            if 'ΔM值' in df_mx.columns:
                df_mx['M值变化_num']=df_mx['ΔM值'].apply(parse_delta)
            df_mx['基期M值']=pd.to_numeric(df_mx['基期M值'],errors='coerce')
            df_mx['考核期M值']=pd.to_numeric(df_mx['考核期M值'],errors='coerce')
            data['detail']=df_mx
        else:
            data['detail']=pd.DataFrame()

    except Exception as e:
        data['error']=str(e)
    return data

def m_tier(val):
    if pd.isna(val): return '未知'
    if val>=0.90: return '≥90%'
    if val>=0.79: return '79-90%'
    if val>=0.57: return '57-79%'
    return '<57%'

TIER_ORDER=['≥90%','79-90%','57-79%','<57%']
TIER_COLOR={'≥90%':'#27ae60','79-90%':'#f39c12','57-79%':'#e67e22','<57%':'#e74c3c'}

def color_val(col, val):
    """根据各列的业务规则返回 'red'/'yellow'/'green'/''"""
    if pd.isna(val): return ''
    # 当前M值：>70%绿 / 60-70%黄 / <60%红
    if col == '当前M值':
        if val >= 0.70: return 'green'
        if val >= 0.60: return 'yellow'
        return 'red'
    # ΔM：>0绿 / =0黄 / <0红
    if col == 'ΔM':
        if val > 0:    return 'green'
        if val == 0:   return 'yellow'
        return 'red'
    # 免配覆盖率：≥70%绿 / 50-70%黄 / <50%红
    if col == '免配覆盖率':
        if val >= 0.70: return 'green'
        if val >= 0.50: return 'yellow'
        return 'red'
    # 商承4元覆盖率：≥40%绿 / 20-40%黄 / <20%红
    if col == '商承4元覆盖率':
        if val >= 0.40: return 'green'
        if val >= 0.20: return 'yellow'
        return 'red'
    # 新阶梯覆盖率：≥75%绿 / 60-75%黄 / <60%红
    if col == '新阶梯覆盖率':
        if val >= 0.75: return 'green'
        if val >= 0.60: return 'yellow'
        return 'red'
    return ''

def fmt_pct(v, signed=False):
    if pd.isna(v): return '-'
    if signed: return f"{v:+.2%}"
    return f"{v:.2%}"

# ── 侧边栏 ────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="background:rgba(255,255,255,0.12);border-radius:8px;'
        'padding:10px 12px;margin-bottom:12px">'
        '<div style="font-size:1.0rem;font-weight:800;color:#fff;margin-bottom:4px">📂 上传数据文件</div>'
        '<div style="font-size:0.75rem;color:#aac4ee">每日M值 Excel（.xlsx）</div>'
        '</div>',
        unsafe_allow_html=True
    )
    uploaded=st.file_uploader("点击或拖拽上传 Excel",type=["xlsx","xls"],label_visibility="collapsed")
    default_path=None
    for fname in ['中高客单城商M值东莞二区20260330.xlsx','东莞二区M值-20260329.xlsx']:
        p=os.path.join(os.path.dirname(__file__),fname)
        if os.path.exists(p): default_path=p; break

    if uploaded:
        tmp=tempfile.NamedTemporaryFile(delete=False,suffix='.xlsx')
        tmp.write(uploaded.read()); tmp.close()
        DATA_PATH=tmp.name; st.success("✅ 已加载新文件")
    elif default_path:
        DATA_PATH=default_path; st.info(f"📌 {os.path.basename(default_path)}")
    else:
        DATA_PATH=None; st.warning("请上传M值 Excel")

# ── 主体 ──────────────────────────────────────────────────────────────
st.title("📊 常平联络点M值看板")

if not DATA_PATH:
    st.warning("请在左侧上传M值 Excel 文件"); st.stop()

data = load_data(DATA_PATH)
if 'error' in data:
    st.error(f"数据加载失败：{data['error']}"); st.stop()

df_board = data.get('board', pd.DataFrame())
df_trend = data.get('trend', pd.DataFrame())
df_all   = data.get('detail', pd.DataFrame())
date_cols = data.get('date_cols', [])

# ═══════════════════════════════════════════════════════════════════
# 板块1：汇总数据表
# ═══════════════════════════════════════════════════════════════════
st.markdown('<div class="section-btn">📋 联络点/BD M值汇总</div>', unsafe_allow_html=True)
st.markdown(
    '<div style="font-size:0.78rem;color:#888;margin:-4px 0 10px 0">'
    '<span style="color:#1e8449;font-weight:600">● 优秀</span>&nbsp;&nbsp;'
    '<span style="color:#b7770d;font-weight:600">● 一般</span>&nbsp;&nbsp;'
    '<span style="color:#c0392b;font-weight:600">● 异常</span>'
    '</div>',
    unsafe_allow_html=True
)

# ── 为每个联络点/BD生成迷你折线图（sparkline，统一黑色）──────────
def make_sparkline(name, df_trend, date_cols):
    """返回 plotly Figure（迷你折线，统一黑色）"""
    if df_trend.empty or not date_cols: return None
    row = df_trend[df_trend['联络点'] == name]
    if row.empty: return None
    row = row.iloc[0]
    date_labels = [d for _, d in date_cols]
    y_vals = [row.get(d, None) for d in date_labels]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(range(len(date_labels))), y=y_vals,
        mode='lines+markers',
        line=dict(color='#222222', width=1.6),   # 统一黑色
        marker=dict(size=3, color='#222222'),
        hovertemplate='%{text}<br>M值: %{y:.2%}<extra></extra>',
        text=date_labels
    ))
    fig.update_layout(
        width=110, height=36,
        margin=dict(l=2,r=2,t=2,b=2),
        paper_bgcolor='white',
        plot_bgcolor='white',
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
    )
    return fig

if not df_board.empty:

    # 颜色映射
    BG_MAP = {'red':'#fdecea','yellow':'#fef9e7','green':'#eafaf1','':'white'}
    FC_MAP = {'red':'#c0392b','yellow':'#b7770d','green':'#1e8449','':'#333'}

    def num_cell(val_str, color_key, bold=False, bg_override=None):
        bg = bg_override if bg_override else BG_MAP.get(color_key, 'white')
        fc = FC_MAP.get(color_key, '#333')
        fw = '700' if bold or color_key in ('red','green') else '500'
        return (
            f'<div style="background:{bg};color:{fc};font-weight:{fw};'
            f'font-size:0.85rem;padding:8px 6px;text-align:center;'
            f'border-bottom:1px solid #f0f0f0;min-height:40px;'
            f'line-height:24px;border-radius:0">'
            f'{val_str}</div>'
        )

    def name_cell(text, bold=False, bg='white'):
        fw = '700' if bold else '400'
        return (
            f'<div style="background:{bg};color:#222;font-weight:{fw};'
            f'font-size:0.85rem;padding:8px 8px;'
            f'border-bottom:1px solid #f0f0f0;min-height:40px;line-height:24px">'
            f'{text}</div>'
        )

    col_widths = [1.7, 0.9, 1.0, 0.85, 1.1, 1.1, 1.1, 1.1]
    hdr_labels = ['联络点/BD','基期M值','当前M值','ΔM','一周走势','免配覆盖率','商承4元','新阶梯']

    hdr_cols = st.columns(col_widths)
    for hc, hl in zip(hdr_cols, hdr_labels):
        hc.markdown(
            f'<div style="background:#1a2744;color:white;font-weight:700;'
            f'padding:9px 4px;text-align:center;font-size:0.8rem;'
            f'border-radius:4px;white-space:nowrap">{hl}</div>',
            unsafe_allow_html=True
        )

    for _, row in df_board.iterrows():
        name   = str(row.get('联络点/BD',''))
        is_lld = (name == '东莞常平联络点')
        row_bg = '#EEF6FF' if is_lld else 'white'
        bold   = is_lld
        row_cols = st.columns(col_widths)

        # 名称列
        row_cols[0].markdown(name_cell(name, bold=bold, bg=row_bg), unsafe_allow_html=True)

        # 基期M值（无颜色，纯文字）
        v_base = row.get('基期M值', float('nan'))
        row_cols[1].markdown(num_cell(fmt_pct(v_base), '', bold=bold, bg_override=row_bg), unsafe_allow_html=True)

        # 当前M值
        v_cur = row.get('当前M值', float('nan'))
        clr   = color_val('当前M值', v_cur)
        row_cols[2].markdown(num_cell(fmt_pct(v_cur), clr, bold=bold), unsafe_allow_html=True)

        # ΔM
        v_dm = row.get('ΔM', float('nan'))
        clr  = color_val('ΔM', v_dm)
        row_cols[3].markdown(num_cell(fmt_pct(v_dm, signed=True), clr, bold=bold), unsafe_allow_html=True)

        # 一周走势 sparkline
        spark_fig = make_sparkline(name, df_trend, date_cols)
        if spark_fig:
            row_cols[4].plotly_chart(spark_fig, use_container_width=False, config={'displayModeBar':False})
        else:
            row_cols[4].markdown(num_cell('-', '', bg_override=row_bg), unsafe_allow_html=True)

        # 三个覆盖率
        cov_fields = [('免配覆盖率',5), ('商承4元覆盖率',6), ('新阶梯覆盖率',7)]
        for field, cidx in cov_fields:
            v   = row.get(field, float('nan'))
            clr = color_val(field, v)
            row_cols[cidx].markdown(num_cell(fmt_pct(v), clr, bold=bold), unsafe_allow_html=True)

else:
    st.warning("未能解析汇总数据，请检查看板sheet格式")

# legend inline above







# ═══════════════════════════════════════════════════════════════════
# 板块2：商家明细
# ═══════════════════════════════════════════════════════════════════
st.markdown('<div style="margin-top:32px"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-btn">📋 商家明细</div>', unsafe_allow_html=True)

IMPACT_COL = '基期M值变化影响单量'

df_cp = df_all[df_all['联络点'].astype(str).str.contains('常平', na=False)].copy() if not df_all.empty else pd.DataFrame()

if df_cp.empty:
    st.info('未找到常平联络点商家明细数据，请确认文件包含"商家明细"sheet')
else:
    # ── 数据预处理 ─────────────────────────────────────────────────
    df_cp['基期M值_num']   = pd.to_numeric(df_cp['基期M值'],   errors='coerce')
    df_cp['考核期M值_num'] = pd.to_numeric(df_cp['考核期M值'], errors='coerce')
    df_cp['ΔM_num']        = df_cp['ΔM值'].apply(parse_delta)
    df_cp['影响单量_num']  = pd.to_numeric(df_cp[IMPACT_COL],   errors='coerce')
    df_cp['M值档位']       = df_cp['考核期M值_num'].apply(m_tier)
    df_cp['异常']          = df_cp['ΔM_num'].apply(lambda v: bool(pd.notna(v) and v < 0))
    df_cp_sorted = df_cp.sort_values('影响单量_num', ascending=True).reset_index(drop=True)

    bd_list_all = sorted(df_cp_sorted['所属BD姓名'].dropna().unique().tolist())
    lld_name    = df_cp_sorted['联络点'].dropna().iloc[0] if not df_cp_sorted.empty else '常平联络点'
    bd_btns_row1 = [lld_name] + bd_list_all

    TIER_DISPLAY = ['全部', '≥90%', '70-90%', '50-70%', '<50%', '⚠️ 异常']
    TIER_MAP     = {'≥90%':'≥90%', '70-90%':'79-90%', '50-70%':'57-79%', '<50%':'<57%'}

    SHOW_COLS_SRC = ['所属BD姓名','MT商家名称','基期M值_num','考核期M值_num',
                     'ΔM_num','影响单量_num','新阶梯','是否免配','免配商承',
                     '昨日单量','昨日神抢手单量','拜访','优先级']
    COL_RENAME = {
        '基期M值_num':'基期M值', '考核期M值_num':'当前M值',
        'ΔM_num':'ΔM', '影响单量_num':'影响单量'
    }

    # ── BD筛选 ──────────────────────────────────────────────────────
    sel_bd   = st.radio('', bd_btns_row1, horizontal=True,
                        key='bd_main', label_visibility='collapsed')
    sel_tier = st.radio('', TIER_DISPLAY, horizontal=True,
                        key='tier_main', label_visibility='collapsed')

    fd = df_cp_sorted.copy()
    if sel_bd != lld_name:
        fd = fd[fd['所属BD姓名'] == sel_bd]
    if sel_tier == '⚠️ 异常':
        fd = fd[fd['异常'] == True]
    elif sel_tier != '全部':
        fd = fd[fd['M值档位'] == TIER_MAP.get(sel_tier, sel_tier)]

    show = [c for c in SHOW_COLS_SRC if c in fd.columns]
    disp = fd[show].rename(columns=COL_RENAME).reset_index(drop=True)
    disp.index = disp.index + 1

    def hl(row):
        # ΔM<0 → 浅红底
        v_dm = row.get('ΔM', None)
        if isinstance(v_dm,(int,float)) and pd.notna(v_dm) and v_dm < 0:
            return ['background-color:#fff0f0']*len(row)
        return ['']*len(row)

    def hl_cell(val, col_name):
        """单元格级别高亮：新阶梯=- 或 是否免配=否 → 红色文字+红底"""
        s = str(val).strip() if pd.notna(val) else '-'
        if col_name == '新阶梯' and s in ('-', '', 'nan', '未报名'):
            return 'background-color:#fdecea;color:#c0392b;font-weight:700'
        if col_name == '是否免配' and s == '否':
            return 'background-color:#fdecea;color:#c0392b;font-weight:700'
        return ''

    fmt_d = {}
    for c in ['基期M值','当前M值']:
        if c in disp.columns: fmt_d[c] = '{:.2%}'
    if 'ΔM' in disp.columns: fmt_d['ΔM'] = '{:+.2%}'
    if '影响单量' in disp.columns: fmt_d['影响单量'] = '{:.1f}'
    if '免配商承' in disp.columns: fmt_d['免配商承'] = '{:.1f}'

    # ── 明细表 + 勾选列 ─────────────────────────────────────────────
    st.caption(f"共 {len(disp)} 家  |  勾选后在下方播报板块生成播报")

    # 构建 Styler：行级ΔM红底 + 单元格级新阶梯/是否免配红底
    disp_chk = disp.copy()
    disp_chk.insert(0, '勾选', False)
    base_style = disp_chk.style.apply(hl, axis=1).format(fmt_d, na_rep='-')
    for _col in ['新阶梯', '是否免配']:
        if _col in disp_chk.columns:
            base_style = base_style.applymap(lambda v, c=_col: hl_cell(v, c), subset=[_col])
    edited = st.data_editor(
        base_style,
        use_container_width=True,
        height=500,
        disabled=[c for c in disp_chk.columns if c != '勾选'],
        key='detail_editor'
    )

    # 取勾选的商家名
    bc_checked_names = []
    if edited is not None:
        chk_df = edited if isinstance(edited, pd.DataFrame) else pd.DataFrame(edited)
        if '勾选' in chk_df.columns and 'MT商家名称' in chk_df.columns:
            bc_checked_names = chk_df[chk_df['勾选'] == True]['MT商家名称'].dropna().tolist()
        elif '勾选' in chk_df.columns and '当前M值' in chk_df.columns:
            # rename后商家名列
            name_col = 'MT商家名称' if 'MT商家名称' in chk_df.columns else None
            if name_col:
                bc_checked_names = chk_df[chk_df['勾选'] == True][name_col].dropna().tolist()

    # ── 同步给播报板块（session_state） ─────────────────────────────
    import streamlit as _st
    _st.session_state['bc_checked_names'] = bc_checked_names
    _st.session_state['bc_sel_bd']        = sel_bd if sel_bd != lld_name else ''

# ═══════════════════════════════════════════════════════════════════
# 板块3：今日动作播报
# ═══════════════════════════════════════════════════════════════════
st.markdown('<div class="section-btn">🔈 今日动作播报</div>', unsafe_allow_html=True)

if df_cp.empty:
    st.info("无商家数据，请先上传文件")
else:
    bc_bd = st.selectbox("选择BD", bd_list_all, key='bc_bd_sel')

    # 从 session_state 读取板块二勾选结果（同BD时自动填入）
    _checked = st.session_state.get('bc_checked_names', [])
    _prev_bd = st.session_state.get('bc_sel_bd', '')
    if _prev_bd == bc_bd and _checked:
        auto_hint = f"已从板块二勾选 {len(_checked)} 家，可直接生成播报"
        st.caption(auto_hint)
        selected_names = _checked
    else:
        selected_names = []

    st.markdown("**手动补充商家（可选）：** 在下方输入框每行一个商家名称")
    extra_input = st.text_area("补充商家名称", height=80, key='bc_extra',
                               placeholder="每行一个，可留空")
    extra_names = [n.strip() for n in extra_input.splitlines() if n.strip()]
    all_names   = selected_names + [n for n in extra_names if n not in selected_names]

    if all_names:
        lines = [f"【{bc_bd}】今日跟进商家："]
        for j, n in enumerate(all_names, 1):
            lines.append(f"{j}、{n}")
        broadcast_text = "\n".join(lines)
        st.text_area("📋 播报内容（直接复制）", broadcast_text,
                     height=max(120, 28 * len(all_names) + 70),
                     key='bc_output')
        st.success(f"✅ 共 {len(all_names)} 家")
    else:
        st.info("请在板块二勾选商家，或在上方补充商家名称")


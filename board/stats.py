"""统计核心 —— 各工位不良率 与 缺陷 TOP 排行 的单一事实来源。

大屏首页(views.dashboard,首屏渲染)与实时刷新接口(stats_api,前端轮询)
共用本模块 compute_stats(),保证「首屏」与「轮询到的增量」口径完全一致。

时间窗(window):
  today —— 仅今日(按本地日历日)
  7d    —— 近 7 天(含今日)
  all   —— 全部历史(默认)
产线(line):可选,精确匹配某条产线;不传则全线合计。

不良率等级(level)按阈值上色:good ≤ WARN < warn ≤ BAD < bad。
脱敏铁律:一切数据虚构(某企业 / 一·二·三工位 / 层压·焊接·EL检 / 师傅化名)。
"""
from datetime import timedelta

from django.db.models import Sum, Q
from django.utils import timezone

from .alerts import build_alerts
from .models import Station, Defect, Batch, Inspection

# 不良率等级阈值(百分比)。可按产线要求再调。
WARN_RATE = 5.0   # ≤ 此值为「良好」
BAD_RATE = 8.0    # ≤ 此值为「关注」,超过为「预警」

WINDOWS = (
    ('today', '今日'),
    ('7d', '近7天'),
    ('all', '全部'),
)
_WINDOW_KEYS = {k for k, _ in WINDOWS}


def _rate(bad, total):
    return round(bad / total * 100, 2) if total else 0.0


def _level(rate):
    if rate <= WARN_RATE:
        return 'good'
    if rate <= BAD_RATE:
        return 'warn'
    return 'bad'


def _window_filter(window):
    """把时间窗换成 Inspection 过滤条件(基于 inspected_at 本地日)。"""
    today = timezone.localdate()
    if window == 'today':
        return Q(inspected_at__date=today)
    if window == '7d':
        return Q(inspected_at__date__gte=today - timedelta(days=6))
    return Q()  # all


def _trend(line='', days=14):
    """近 N 天逐日不良率趋势(供大屏折线图)。honor line 过滤,不受 window 限制。

    返回按日期升序的列表,每项含日期、检验数、不良数、不良率、等级。
    没有记录的日期也补 0,保证折线连续、坐标均匀。
    """
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    qs = Inspection.objects.filter(inspected_at__date__gte=start)
    if line:
        qs = qs.filter(station__line=line)

    totals, bads = {}, {}
    for row in (qs.values('inspected_at__date')
                .annotate(t=Sum('quantity'))):
        totals[row['inspected_at__date']] = row['t'] or 0
    for row in (qs.filter(is_qualified=False).values('inspected_at__date')
                .annotate(b=Sum('quantity'))):
        bads[row['inspected_at__date']] = row['b'] or 0

    points = []
    for i in range(days):
        d = start + timedelta(days=i)
        t = totals.get(d, 0)
        b = bads.get(d, 0)
        rate = _rate(b, t)
        points.append({
            'date': d.strftime('%m-%d'),
            'total': t,
            'bad': b,
            'rate': rate,
            'level': _level(rate) if t else 'good',
        })
    return points


def compute_stats(window='all', line='', top=8):
    """聚合出一份完整看板数据(KPI + 各工位不良率 + 缺陷 TOP + 严重度分布)。

    返回结构对模板与 JSON 通用;数值均为原生 int/float/str,可直接 JsonResponse。
    """
    if window not in _WINDOW_KEYS:
        window = 'all'

    base = Inspection.objects.filter(_window_filter(window))
    if line:
        base = base.filter(station__line=line)

    total = base.aggregate(n=Sum('quantity'))['n'] or 0
    bad = base.filter(is_qualified=False).aggregate(n=Sum('quantity'))['n'] or 0

    # —— 各工位不良率(高到低) ——
    st_qs = Station.objects.filter(is_active=True)
    if line:
        st_qs = st_qs.filter(line=line)
    stations = []
    for st in st_qs:
        rows = base.filter(station=st)
        st_total = rows.aggregate(n=Sum('quantity'))['n'] or 0
        st_bad = rows.filter(is_qualified=False).aggregate(n=Sum('quantity'))['n'] or 0
        rate = _rate(st_bad, st_total)
        stations.append({
            'name': st.name,
            'code': st.code,
            'line': st.line,
            'operator': st.operator or '',
            'total': st_total,
            'bad': st_bad,
            'good': st_total - st_bad,
            'rate': rate,
            'level': _level(rate) if st_total else 'good',
        })
    stations.sort(key=lambda s: (s['rate'], s['bad']), reverse=True)

    # —— 缺陷 TOP 排行 ——(占「全部不良」的比重,便于排帕累托)
    bad_qs = base.filter(is_qualified=False)
    raw = (bad_qs.values('defect__name', 'defect__category',
                         'defect__severity', 'defect__code')
           .annotate(n=Sum('quantity'))
           .order_by('-n'))
    sev_label = dict(Defect.SEVERITY_CHOICES)
    defects = []
    for r in raw[:top]:
        n = r['n'] or 0
        defects.append({
            'name': r['defect__name'] or '(未归类)',
            'code': r['defect__code'] or '',
            'category': r['defect__category'] or '',
            'severity': r['defect__severity'] or 'major',
            'severity_display': sev_label.get(r['defect__severity'], '一般'),
            'n': n,
            'share': _rate(n, bad),        # 占全部不良的百分比
        })
    defect_kind_count = raw.count()

    # —— 严重度分布(critical/major/minor) ——
    severity = []
    for key, label in Defect.SEVERITY_CHOICES:
        n = (bad_qs.filter(defect__severity=key)
             .aggregate(n=Sum('quantity'))['n'] or 0)
        severity.append({'key': key, 'label': label, 'n': n,
                         'share': _rate(n, bad)})

    overall_rate = _rate(bad, total)
    thresholds = {'warn': WARN_RATE, 'bad': BAD_RATE}
    alerts = build_alerts(stations, overall_rate, thresholds)

    return {
        'window': window,
        'window_label': dict(WINDOWS).get(window, '全部'),
        'line': line,
        'total': total,
        'good': total - bad,
        'bad': bad,
        'rate': overall_rate,
        'rate_level': _level(overall_rate) if total else 'good',
        'alerts': alerts,
        'batch_count': (Batch.objects.filter(line=line).count()
                        if line else Batch.objects.count()),
        'station_count': st_qs.count(),
        'defect_kind_count': defect_kind_count,
        'stations': stations,
        'defects': defects,
        'severity': severity,
        'trend': _trend(line=line),
        'generated_at': timezone.localtime().strftime('%Y-%m-%d %H:%M:%S'),
        'thresholds': thresholds,
    }


def line_choices():
    """现有产线清单(去重),供筛选下拉。"""
    return sorted(set(
        Station.objects.filter(is_active=True)
        .values_list('line', flat=True)))

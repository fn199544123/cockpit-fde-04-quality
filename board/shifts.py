"""按班次的不良追溯 与 缺陷帕累托分析 —— 统计核心(单一事实来源)。

追溯页(trace.trace,首屏渲染)与实时刷新接口(trace.trace_api,前端轮询)共用本模块,
口径与大屏(stats.compute_stats)完全一致:复用同一套阈值 / 时间窗 / 分级函数。

一、班次划分(三班倒,按检验时间的本地小时归班):
  早班 08:00–15:59 / 中班 16:00–23:59 / 晚班 00:00–07:59。
  班次从 Inspection.inspected_at 现推(不落库),改班制只改这里一处。

二、按班次的不良追溯(compute_shift_trace):
  每个班次 → 总检 / 不良 / 不良率 / 分级,并可下钻到「该班各工位」「该班各缺陷」,
  形成 班次 → 工位 → 缺陷 的三级追溯链,定位「哪个班、哪个工位、栽在哪种缺陷」。

三、缺陷帕累托分析(compute_pareto):
  缺陷按不良数降序,算累计占比,标出「累计达 80% 的关键少数(vital few)」——
  即「抓这几种缺陷就能消掉八成不良」,是质量改善的优先靶子。可按班次过滤。

脱敏铁律:一切数据虚构(某企业 / 一·二·三工位 / 层压·焊接·EL检 / 师傅化名)。
"""
from django.db.models import Sum
from django.utils import timezone

from .models import Station, Defect, Inspection
from .stats import _rate, _level, _window_filter, WINDOWS, _WINDOW_KEYS, line_choices  # noqa: F401

# —— 班次定义:key / 名称 / 起始小时(含)/ 结束小时(不含,跨零点用 24) ——
# 归班规则:start <= hour < end(晚班 0–8、早班 8–16、中班 16–24)。
SHIFTS = (
    ('night', '晚班', 0, 8, '00:00–08:00'),
    ('morning', '早班', 8, 16, '08:00–16:00'),
    ('middle', '中班', 16, 24, '16:00–24:00'),
)
_SHIFT_KEYS = {k for k, *_ in SHIFTS}
PARETO_CUTOFF = 80.0  # 帕累托「关键少数」累计占比阈值(%)


def shift_of_hour(hour):
    """把 0–23 的本地小时归到班次 key。"""
    for key, _label, start, end, _span in SHIFTS:
        if start <= hour < end:
            return key
    return 'night'  # 兜底(理论不达)


def shift_label(key):
    for k, label, *_ in SHIFTS:
        if k == key:
            return label
    return key


def _base_qs(window, line):
    qs = Inspection.objects.filter(_window_filter(window))
    if line:
        qs = qs.filter(station__line=line)
    return qs


def compute_shift_trace(window='all', line='', top=6):
    """按班次汇总不良,并给出 班次→工位、班次→缺陷 的下钻明细。

    返回 shifts 列表(按 SHIFTS 顺序),每项:
      key/label/span、total/bad/good/rate/level、share(占全部不良比重)、
      stations(该班各工位不良,降序)、defects(该班缺陷 TOP,降序,含严重度)、
      worst(该班头号缺陷,做徽标)。另附全局 total/bad 便于占比。
    """
    if window not in _WINDOW_KEYS:
        window = 'all'

    base = _base_qs(window, line)
    st_name = dict(Station.objects.values_list('id', 'name'))
    st_code = dict(Station.objects.values_list('id', 'code'))
    st_op = dict(Station.objects.values_list('id', 'operator'))
    sev_label = dict(Defect.SEVERITY_CHOICES)

    # 初始化各班次累加桶
    buckets = {}
    for key, label, _s, _e, span in SHIFTS:
        buckets[key] = {
            'key': key, 'label': label, 'span': span,
            'total': 0, 'bad': 0,
            '_st': {},   # station_id -> {total,bad}
            '_df': {},   # (name,code,severity,category) -> n
        }

    # 单遍扫描:按班次归桶(数据量为演示级,Python 内聚合最稳最清晰)
    rows = base.values('inspected_at', 'is_qualified', 'quantity', 'station_id',
                       'defect__name', 'defect__code', 'defect__severity',
                       'defect__category')
    for r in rows:
        hour = timezone.localtime(r['inspected_at']).hour
        b = buckets[shift_of_hour(hour)]
        q = r['quantity'] or 0
        b['total'] += q
        sid = r['station_id']
        st = b['_st'].setdefault(sid, {'total': 0, 'bad': 0})
        st['total'] += q
        if not r['is_qualified']:
            b['bad'] += q
            st['bad'] += q
            dkey = (r['defect__name'] or '(未归类)', r['defect__code'] or '',
                    r['defect__severity'] or 'major', r['defect__category'] or '')
            b['_df'][dkey] = b['_df'].get(dkey, 0) + q

    total_all = sum(b['total'] for b in buckets.values())
    bad_all = sum(b['bad'] for b in buckets.values())

    shifts = []
    for key, label, _s, _e, span in SHIFTS:
        b = buckets[key]
        rate = _rate(b['bad'], b['total'])

        stations = []
        for sid, v in b['_st'].items():
            srate = _rate(v['bad'], v['total'])
            stations.append({
                'name': st_name.get(sid, f'#{sid}'),
                'code': st_code.get(sid, ''),
                'operator': st_op.get(sid, '') or '',
                'total': v['total'], 'bad': v['bad'], 'good': v['total'] - v['bad'],
                'rate': srate, 'level': _level(srate) if v['total'] else 'good',
            })
        stations.sort(key=lambda s: (s['bad'], s['rate']), reverse=True)

        defects = []
        for (name, code, severity, category), n in b['_df'].items():
            defects.append({
                'name': name, 'code': code, 'category': category,
                'severity': severity, 'severity_display': sev_label.get(severity, '一般'),
                'n': n, 'share': _rate(n, b['bad']),
            })
        defects.sort(key=lambda d: d['n'], reverse=True)

        shifts.append({
            'key': key, 'label': label, 'span': span,
            'total': b['total'], 'bad': b['bad'], 'good': b['total'] - b['bad'],
            'rate': rate, 'level': _level(rate) if b['total'] else 'good',
            'share': _rate(b['bad'], bad_all),
            'stations': stations,
            'defects': defects[:top],
            'defect_kind': len(defects),
            'worst': defects[0] if defects else None,
        })

    # 头号班次(不良率最高、有样本)——追溯页顶部结论
    ranked = [s for s in shifts if s['total']]
    worst_shift = max(ranked, key=lambda s: (s['rate'], s['bad'])) if ranked else None

    return {
        'window': window,
        'window_label': dict((k, l) for k, l in WINDOWS).get(window, '全部'),
        'line': line,
        'total': total_all,
        'bad': bad_all,
        'good': total_all - bad_all,
        'rate': _rate(bad_all, total_all),
        'shifts': shifts,
        'worst_shift': worst_shift,
        'generated_at': timezone.localtime().strftime('%Y-%m-%d %H:%M:%S'),
    }


def compute_pareto(window='all', line='', shift='', top=12):
    """缺陷帕累托:按不良数降序 + 累计占比,标出累计达 80% 的关键少数。

    shift 可选(限定某班次);不传则全部班次合计。
    返回 items(含 n/share/cum(累计不良数)/cum_share(累计占比)/vital(是否关键少数)),
    及 cutoff_index(第一次累计≥80% 的序号,1 基;0 表示无数据)。
    """
    if window not in _WINDOW_KEYS:
        window = 'all'
    if shift and shift not in _SHIFT_KEYS:
        shift = ''

    base = _base_qs(window, line).filter(is_qualified=False)

    # 班次过滤:按小时归班后取该班的记录
    if shift:
        ids = []
        for r in base.values('id', 'inspected_at'):
            if shift_of_hour(timezone.localtime(r['inspected_at']).hour) == shift:
                ids.append(r['id'])
        base = base.filter(id__in=ids)

    sev_label = dict(Defect.SEVERITY_CHOICES)
    raw = (base.values('defect__name', 'defect__code', 'defect__severity',
                       'defect__category')
           .annotate(n=Sum('quantity'))
           .order_by('-n'))

    rows = list(raw)
    grand = sum(r['n'] or 0 for r in rows)

    items = []
    cum = 0
    cutoff_index = 0
    for i, r in enumerate(rows, start=1):
        n = r['n'] or 0
        cum += n
        cum_share = _rate(cum, grand)
        vital = cum_share <= PARETO_CUTOFF or cutoff_index == 0
        if cutoff_index == 0 and cum_share >= PARETO_CUTOFF:
            cutoff_index = i  # 第一个把累计推过 80% 的缺陷,含它即达标
        items.append({
            'rank': i,
            'name': r['defect__name'] or '(未归类)',
            'code': r['defect__code'] or '',
            'category': r['defect__category'] or '',
            'severity': r['defect__severity'] or 'major',
            'severity_display': sev_label.get(r['defect__severity'], '一般'),
            'n': n,
            'share': _rate(n, grand),
            'cum': cum,
            'cum_share': cum_share,
            'vital': i <= cutoff_index if cutoff_index else True,
        })

    # 上一轮 vital 用 cutoff_index 兜准(cutoff 未定时全体都算 vital)
    if cutoff_index:
        for it in items:
            it['vital'] = it['rank'] <= cutoff_index

    return {
        'window': window,
        'line': line,
        'shift': shift,
        'shift_label': shift_label(shift) if shift else '全部班次',
        'grand': grand,
        'cutoff': PARETO_CUTOFF,
        'cutoff_index': cutoff_index,
        'vital_count': cutoff_index,
        'items': items[:top],
        'kind': len(rows),
    }

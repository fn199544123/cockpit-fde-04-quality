"""SPC 超阈值/异常预警 —— 从各工位不良率里自动挑出「该管的」。

两条判据,任一命中即出预警(可同时命中):
  1) 阈值预警:工位不良率超过「预警线」(BAD_RATE)→ 超标;落在关注区(WARN..BAD)→ 关注。
  2) SPC 失控:以「全线综合不良率」为中心线(p̄),按 p 控制图算每个工位的 3σ 控制上限
     UCL = p̄ + 3·√(p̄(1-p̄)/n);工位不良率超过自己的 UCL 即判为「统计失控」(超出正常波动)。
     样本量过小(< MIN_SAMPLES)时控制限不可靠,不判失控,只走阈值判据。

严重度:失控 或 超预警线 → critical(红,大屏高亮);仅落在关注区 → warning(黄)。
输出结构同时供模板首屏渲染与 /api/stats/ 轮询刷新,口径唯一。
脱敏铁律:一切数据虚构(某企业 / 一·二·三工位 / 层压·焊接·EL检 / 师傅化名)。
"""
import math

# SPC 控制限在样本过少时不稳定,低于此样本量不判「失控」(仍走阈值判据)。
MIN_SAMPLES = 20


def build_alerts(stations, overall_rate, thresholds):
    """从 compute_stats 的各工位明细里生成预警列表 + 计数。

    stations   —— compute_stats() 里的工位明细(含 total/bad/rate/level 等)。
    overall_rate —— 全线综合不良率(%),作为 SPC 控制图中心线 p̄。
    thresholds —— {'warn': WARN_RATE, 'bad': BAD_RATE}。
    """
    warn = thresholds['warn']
    bad = thresholds['bad']
    center = round(overall_rate, 2)
    pbar = overall_rate / 100.0  # 中心线(分数)

    items = []
    for s in stations:
        n = s['total']
        rate = s['rate']
        if not n:
            continue

        # —— SPC p 控制图上限(样本充足才算) ——
        ucl = None
        if n >= MIN_SAMPLES and 0 < pbar < 1:
            sigma = math.sqrt(pbar * (1 - pbar) / n)
            ucl = round((pbar + 3 * sigma) * 100, 2)

        spc_ooc = ucl is not None and rate > ucl
        over_bad = rate > bad
        over_warn = warn < rate <= bad

        reasons = []
        if spc_ooc:
            reasons.append({
                'type': 'spc', 'label': 'SPC失控',
                'detail': f'不良率 {rate}% 超 3σ 控制上限 {ucl}%(中心线 {center}%)',
            })
        if over_bad:
            reasons.append({
                'type': 'over_bad', 'label': '超预警线',
                'detail': f'不良率 {rate}% 超预警线 {bad}%',
            })
        elif over_warn:
            reasons.append({
                'type': 'over_warn', 'label': '进入关注区',
                'detail': f'不良率 {rate}% 高于良好线 {warn}%(尚未超预警线 {bad}%)',
            })

        if not reasons:
            continue

        severity = 'critical' if (spc_ooc or over_bad) else 'warning'
        items.append({
            'station': s['name'],
            'code': s['code'],
            'line': s['line'],
            'operator': s['operator'] or '',
            'n': n,
            'bad': s['bad'],
            'rate': rate,
            'ucl': ucl,
            'center': center,
            'severity': severity,
            'reasons': reasons,
            'headline': reasons[0]['label'],   # 最要紧的一条,做徽标
            'detail': reasons[0]['detail'],
            'spc_ooc': spc_ooc,
        })

    # critical 在前,再按不良率从高到低
    order = {'critical': 0, 'warning': 1}
    items.sort(key=lambda a: (order[a['severity']], -a['rate']))

    critical = sum(1 for a in items if a['severity'] == 'critical')
    warning = sum(1 for a in items if a['severity'] == 'warning')
    return {
        'items': items,
        'count': len(items),
        'critical': critical,
        'warning': warning,
        'center': center,
        # 大屏总体状态:red=有失控/超标, amber=仅关注, calm=全部受控
        'status': 'red' if critical else ('amber' if warning else 'calm'),
    }

"""生成脱敏演示数据(让看板与各页面饱满好看)。

运行:  .venv/bin/python scripts/seed_demo.py

脱敏铁律:全部为虚构数据 —— 企业只写「某企业」,工位用 一/二/三工位,
缺陷用 层压/焊接/EL检 三大类,人名一律「张师傅/李师傅…(化名)」,编号全为虚构。
严禁出现任何真实企业/人名/地名。

设计要点(与看板各功能对齐):
- **两条产线 × 三工位**(共 6 工位)→ 各工位不良率柱状 / 产线下拉 / 台账都饱满;
- **9 种缺陷、按大类加权**(每类一个「头号缺陷」)→ 缺陷 TOP 排行 / 帕累托「关键少数」明显;
- **批次铺满近 18 天**(每线每天 1 批)→ 14 天趋势折线连续、无空日;
- **检验时间整天铺开覆盖三班**,叠加班次不良倍率(晚班疲劳偏高)→ 班次追溯有区分度;
- **一号线·二工位·焊接** 不良率刻意调高(0.13)→ 同时触发「超预警线 + SPC 3σ 失控」双重预警。
可重复运行(先清空 board 数据再灌)。
"""
import os
import sys
import random
from datetime import timedelta

import django
from django.utils import timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')
django.setup()

from board.models import Station, Defect, Batch, Inspection  # noqa: E402

# 固定随机种子,保证演示可复现
random.seed(20260923)

# —— 覆盖天数 & 单工位单批检验条数(数据量) ——
DAYS = 18          # 铺满近 18 天(> 14,确保趋势折线整段有数据)
PER_STATION = 55   # 每工位每批约 55 条检验


def run():
    Inspection.objects.all().delete()
    Batch.objects.all().delete()
    Defect.objects.all().delete()
    Station.objects.all().delete()

    # —— 工位:两条产线,各三工位(层压 / 焊接 / EL检) ——
    stations = [
        # 一号线
        Station.objects.create(code='WS-01', name='一工位·层压', line='一号线',
                               operator='张师傅(化名)', order=1),
        Station.objects.create(code='WS-02', name='二工位·焊接', line='一号线',
                               operator='李师傅(化名)', order=2),
        Station.objects.create(code='WS-03', name='三工位·EL检', line='一号线',
                               operator='王师傅(化名)', order=3),
        # 二号线
        Station.objects.create(code='WS-11', name='一工位·层压', line='二号线',
                               operator='赵师傅(化名)', order=1),
        Station.objects.create(code='WS-12', name='二工位·焊接', line='二号线',
                               operator='孙师傅(化名)', order=2),
        Station.objects.create(code='WS-13', name='三工位·EL检', line='二号线',
                               operator='周师傅(化名)', order=3),
    ]

    # —— 缺陷类型:三大类各 3 种(共 9 种) ——
    defects = [
        Defect.objects.create(code='DF-L1', name='层压气泡', category='层压',
                              severity='major', description='EVA 内可见气泡(虚构)'),
        Defect.objects.create(code='DF-L2', name='层压划痕', category='层压',
                              severity='minor', description='表面轻微划痕(虚构)'),
        Defect.objects.create(code='DF-L3', name='层压错位', category='层压',
                              severity='major', description='版图偏移超差(虚构)'),
        Defect.objects.create(code='DF-W1', name='焊接虚焊', category='焊接',
                              severity='critical', description='焊点未熔合(虚构)'),
        Defect.objects.create(code='DF-W2', name='焊带偏移', category='焊接',
                              severity='major', description='焊带偏离主栅(虚构)'),
        Defect.objects.create(code='DF-W3', name='焊接漏焊', category='焊接',
                              severity='critical', description='漏焊接点缺失(虚构)'),
        Defect.objects.create(code='DF-E1', name='EL隐裂', category='EL检',
                              severity='critical', description='EL 图像隐裂(虚构)'),
        Defect.objects.create(code='DF-E2', name='EL黑斑', category='EL检',
                              severity='major', description='EL 图像黑斑(虚构)'),
        Defect.objects.create(code='DF-E3', name='EL碎片', category='EL检',
                              severity='minor', description='边缘微碎片(虚构)'),
    ]
    # 各类缺陷按「头号缺陷」加权(权重越大越常出现)→ 帕累托「关键少数」明显
    defect_weights = {
        'DF-L1': 6, 'DF-L2': 2, 'DF-L3': 3,   # 层压:气泡为主
        'DF-W1': 7, 'DF-W2': 3, 'DF-W3': 2,   # 焊接:虚焊为主
        'DF-E1': 6, 'DF-E2': 3, 'DF-E3': 2,   # EL检:隐裂为主
    }
    by_cat = {}
    for d in defects:
        by_cat.setdefault(d.category, []).append(d)

    def pick_defect(category):
        pool = by_cat[category]
        weights = [defect_weights[d.code] for d in pool]
        return random.choices(pool, weights=weights, k=1)[0]

    # 工位 → 该工位对应缺陷大类(按工序:层压/焊接/EL检)
    station_cat = {
        'WS-01': '层压', 'WS-02': '焊接', 'WS-03': 'EL检',
        'WS-11': '层压', 'WS-12': '焊接', 'WS-13': 'EL检',
    }
    # 各工位基线不良率(演示用,给柱状/预警制造层次)
    # 一号线·二工位·焊接(WS-02)刻意偏高 → 触发「超预警线 + SPC 3σ 失控」双重预警。
    bad_rate = {
        'WS-01': 0.045, 'WS-02': 0.130, 'WS-03': 0.060,
        'WS-11': 0.038, 'WS-12': 0.075, 'WS-13': 0.052,
    }

    # 班次不良倍率(演示用):晚班疲劳 → 不良偏高,早班最稳。用于「按班次追溯」。
    # 班次按检验时间的本地小时归:晚班 00–08 / 早班 08–16 / 中班 16–24。
    def shift_factor(hour):
        if 8 <= hour < 16:      # 早班
            return 0.85
        if 16 <= hour < 24:     # 中班
            return 1.05
        return 1.45             # 晚班(0–8)不良偏高

    # 质检员化名池(与工位负责师傅区分开,演示更真实)
    inspectors = ['质检员·小陈(化名)', '质检员·小林(化名)',
                  '质检员·小郑(化名)', '质检员·小吴(化名)']

    today = timezone.localdate()
    lines = ['一号线', '二号线']
    line_stations = {ln: [s for s in stations if s.line == ln] for ln in lines}

    # —— 批次:每线每天 1 批,铺满近 DAYS 天 ——
    batches = []
    for i in range(DAYS):
        d = today - timedelta(days=i)
        for ln in lines:
            code = f'B{ln[0]}{d.strftime("%y%m%d")}'  # 例 B一260923 / B二260923(虚构)
            batches.append(Batch.objects.create(
                code=code, product='某型光伏组件(虚构)',
                line=ln, planned_qty=random.choice([180, 200, 220, 240]),
                produced_at=d, remark='演示批次(数据全虚构)'))

    total = 0
    bulk = []
    for batch in batches:
        # 该批投产日的本地 0 点,作为检验时间基准(整天铺开,覆盖三班)
        day_start = timezone.make_aware(
            timezone.datetime.combine(batch.produced_at, timezone.datetime.min.time()))
        for st in line_stations[batch.line]:
            cat = station_cat[st.code]
            for _ in range(PER_STATION):
                minute = random.randint(0, 24 * 60 - 1)  # 全天任意时刻
                inspected_at = day_start + timedelta(minutes=minute)
                hour = timezone.localtime(inspected_at).hour
                rate = min(0.9, bad_rate[st.code] * shift_factor(hour))
                is_bad = random.random() < rate
                defect = pick_defect(cat) if is_bad else None
                bulk.append(Inspection(
                    batch=batch, station=st, defect=defect,
                    is_qualified=not is_bad, quantity=1,
                    serial=f'SN-{batch.code}-{random.randint(10000, 99999)}',
                    inspector=random.choice(inspectors),
                    inspected_at=inspected_at,
                    note='' if not is_bad else f'{defect.name}·待复判(虚构)'))
                total += 1
    Inspection.objects.bulk_create(bulk, batch_size=1000)

    print(f'已生成: {Station.objects.count()} 工位(2 线×3 工位), '
          f'{Defect.objects.count()} 缺陷类型, '
          f'{Batch.objects.count()} 批次({DAYS} 天×2 线), '
          f'{Inspection.objects.count()} 条质检记录。')
    # 概览:综合不良率 & 头号预警工位,便于确认演示效果
    from board.stats import compute_stats  # noqa: E402
    s = compute_stats(window='all')
    print(f'综合不良率={s["rate"]}% | 预警条目={s["alerts"]["count"]} '
          f'(失控/超标 {s["alerts"]["critical"]}, 关注 {s["alerts"]["warning"]}) '
          f'| 缺陷种类={s["defect_kind_count"]}')


if __name__ == '__main__':
    run()

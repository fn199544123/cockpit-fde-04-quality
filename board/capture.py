"""数据录入 / 采集 —— 质检记录(Inspection)的快速录入与流水查看。

这是看板的「进数据」入口:台账(ledger.py)管的是主数据(工位/缺陷/批次),
本模块管的是**业务流水**——每一条质检判定。设计目标是「快」:
- 快录页 `/capture/`:一屏一表单,下拉都是可用主数据,检验时间缺省当前;
  提交走 AJAX(`/capture/save/`),不刷新整页,录完即回填、光标归位,可连续录;
- 连续录入时沿用上一条的 批次/工位/质检员(前端记忆),只改判定与数量;
- 侧栏实时显示「本次已录入」流水与计数;整页也带「最近录入」DB 流水兜底(无 JS 也能用)。
- 流水页 `/capture/records/`:全部质检记录的分页 + 关键字 + 合格/不良筛选。

脱敏铁律:一切演示数据虚构(某企业 / 一·二·三工位 / 层压·焊接·EL检 / 师傅化名)。
"""
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Station, Defect, Batch, Inspection
from .forms import InspectionForm


def _recent(limit=15):
    """最近 N 条质检流水,供快录页右侧与整页兜底展示。"""
    qs = (Inspection.objects
          .select_related('batch', 'station', 'defect')
          .order_by('-inspected_at', '-id')[:limit])
    return [_row(i) for i in qs]


def _row(ins):
    """把一条质检记录拍平成模板/JSON 通用的字典。"""
    return {
        'id': ins.id,
        'batch': ins.batch.code,
        'station': ins.station.name,
        'qualified': ins.is_qualified,
        'defect': (ins.defect.name if ins.defect else ''),
        'quantity': ins.quantity,
        'serial': ins.serial or '',
        'inspector': ins.inspector or '',
        'time': timezone.localtime(ins.inspected_at).strftime('%m-%d %H:%M'),
    }


def capture(request):
    """快速录入页:表单 + 最近流水。非 AJAX 的 POST 也能正常落库(渐进增强)。"""
    if request.method == 'POST':
        form = InspectionForm(request.POST)
        if form.is_valid():
            form.save()
            # 连续录入:保留上下文,清掉本条易变字段
            keep = {k: request.POST.get(k, '') for k in ('batch', 'station', 'inspector')}
            url = reverse('capture')
            qs = '&'.join(f'{k}={v}' for k, v in keep.items() if v)
            return redirect(f'{url}?{qs}&ok=1' if qs else f'{url}?ok=1')
    else:
        initial = {}
        for k in ('batch', 'station', 'inspector'):
            v = request.GET.get(k)
            if v:
                initial[k] = v
        form = InspectionForm(initial=initial)

    ctx = {
        'form': form,
        'recent': _recent(),
        'has_master': Batch.objects.exists() and Station.objects.filter(is_active=True).exists(),
        'today_count': Inspection.objects.filter(
            inspected_at__date=timezone.localdate()).count(),
        'saved': request.GET.get('ok') == '1',
    }
    return render(request, 'board/capture.html', ctx)


@require_POST
def capture_save(request):
    """AJAX 快录端点:成功返回该条记录 JSON,失败返回字段错误 JSON。"""
    form = InspectionForm(request.POST)
    if form.is_valid():
        ins = form.save()
        return JsonResponse({'ok': True, 'row': _row(ins),
                             'today_count': Inspection.objects.filter(
                                 inspected_at__date=timezone.localdate()).count()})
    return JsonResponse({'ok': False, 'errors': form.errors}, status=400)


def records(request):
    """质检流水:分页 + 关键字 + 合格/不良筛选,便于回看与核对。"""
    qs = (Inspection.objects
          .select_related('batch', 'station', 'defect')
          .order_by('-inspected_at', '-id'))
    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(batch__code__icontains=q) | Q(station__name__icontains=q) |
            Q(defect__name__icontains=q) | Q(serial__icontains=q) |
            Q(inspector__icontains=q))
    verdict = request.GET.get('v') or ''
    if verdict == 'good':
        qs = qs.filter(is_qualified=True)
    elif verdict == 'bad':
        qs = qs.filter(is_qualified=False)

    paginator = Paginator(qs, 30)
    page = paginator.get_page(request.GET.get('page') or 1)
    ctx = {
        'rows': [_row(i) for i in page.object_list],
        'page': page,
        'q': q,
        'verdict': verdict,
        'total': paginator.count,
    }
    return render(request, 'board/records.html', ctx)

"""按班次不良追溯 + 缺陷帕累托分析 —— 视图层。

- trace:追溯分析页(首屏服务端渲染,无 JS 也能看)。
- trace_api:JSON 接口,前端轮询刷新班次卡片与帕累托,支持按班次过滤帕累托。

统计口径统一收敛在 board.shifts,与大屏(board.stats)同源同阈值。
"""
from django.http import JsonResponse
from django.shortcuts import render

from .shifts import compute_shift_trace, compute_pareto, SHIFTS
from .stats import WINDOWS, line_choices


def trace(request):
    """按班次不良追溯 + 缺陷帕累托 页面。"""
    window = request.GET.get('window') or 'all'
    line = request.GET.get('line') or ''
    shift = request.GET.get('shift') or ''

    ctx = compute_shift_trace(window=window, line=line)
    ctx['pareto'] = compute_pareto(window=window, line=line, shift=shift)
    ctx['windows'] = WINDOWS
    ctx['shift_defs'] = [{'key': k, 'label': l, 'span': s}
                         for k, l, _a, _b, s in SHIFTS]
    ctx['shift'] = shift
    ctx['lines'] = line_choices()
    return render(request, 'board/trace.html', ctx)


def trace_api(request):
    """追溯 JSON 接口:班次汇总 + 帕累托,供页面轮询刷新。"""
    window = request.GET.get('window') or 'all'
    line = request.GET.get('line') or ''
    shift = request.GET.get('shift') or ''
    data = compute_shift_trace(window=window, line=line)
    data['pareto'] = compute_pareto(window=window, line=line, shift=shift)
    return JsonResponse(data)

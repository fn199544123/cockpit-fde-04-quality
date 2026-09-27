"""看板视图。

- dashboard:大屏首页,首屏服务端渲染(无 JS 也能看)。
- stats_api:实时统计 JSON 接口,前端定时轮询,不刷新整页即更新各工位不良率与缺陷 TOP。

统计口径统一收敛在 board.stats.compute_stats(),首屏与轮询共用同一份逻辑。
"""
from django.http import JsonResponse
from django.shortcuts import render

from .stats import compute_stats, line_choices, WINDOWS


def dashboard(request):
    """产线质检不良率大屏首页。"""
    window = request.GET.get('window') or 'all'
    line = request.GET.get('line') or ''
    ctx = compute_stats(window=window, line=line)
    ctx['windows'] = WINDOWS
    ctx['lines'] = line_choices()
    return render(request, 'board/dashboard.html', ctx)


def stats_api(request):
    """实时统计接口:返回 compute_stats() 的完整 JSON,供大屏轮询刷新。"""
    window = request.GET.get('window') or 'all'
    line = request.GET.get('line') or ''
    return JsonResponse(compute_stats(window=window, line=line))

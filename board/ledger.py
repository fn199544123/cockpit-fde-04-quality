"""基础台账管理:工位 / 缺陷类型 / 产品批次 三类主数据的 列表 / 新增 / 编辑。

三类主数据结构相似,用一个「台账登记表」LEDGERS 驱动同一套通用视图,避免重复代码。
每个台账登记项声明:slug、标题、模型、表单、列表列(取值函数)、搜索字段。
"""
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from .models import Station, Defect, Batch
from .forms import StationForm, DefectForm, BatchForm


class Ledger:
    """一类主数据台账的元信息。"""

    def __init__(self, slug, title, icon, model, form, columns, search_fields, order=None):
        self.slug = slug
        self.title = title
        self.icon = icon
        self.model = model
        self.form = form
        self.columns = columns          # [(表头, 取值函数)]
        self.search_fields = search_fields
        self.order = order

    def rows(self, qs):
        """把 queryset 渲染成 [{obj, cells:[...]}]，供模板通用渲染。"""
        data = []
        for obj in qs:
            data.append({'obj': obj, 'cells': [fn(obj) for _, fn in self.columns]})
        return data


def _yn(v):
    return '✔ 启用' if v else '✖ 停用'


def _sev(obj):
    return obj.get_severity_display()


# ————————————— 三类台账登记 —————————————
LEDGERS = {
    'station': Ledger(
        slug='station', title='工位台账', icon='🏭', model=Station, form=StationForm,
        columns=[
            ('工位编号', lambda o: o.code),
            ('工位名称', lambda o: o.name),
            ('所属产线', lambda o: o.line),
            ('负责师傅', lambda o: o.operator or '—'),
            ('工序顺序', lambda o: o.order),
            ('状态', lambda o: _yn(o.is_active)),
        ],
        search_fields=['code', 'name', 'line', 'operator'],
    ),
    'defect': Ledger(
        slug='defect', title='缺陷类型台账', icon='⚠', model=Defect, form=DefectForm,
        columns=[
            ('缺陷编号', lambda o: o.code),
            ('缺陷名称', lambda o: o.name),
            ('缺陷大类', lambda o: o.category or '—'),
            ('严重度', _sev),
            ('说明', lambda o: o.description or '—'),
            ('状态', lambda o: _yn(o.is_active)),
        ],
        search_fields=['code', 'name', 'category'],
    ),
    'batch': Ledger(
        slug='batch', title='产品批次台账', icon='📦', model=Batch, form=BatchForm,
        columns=[
            ('批次号', lambda o: o.code),
            ('产品型号', lambda o: o.product),
            ('产线', lambda o: o.line),
            ('计划数量', lambda o: o.planned_qty),
            ('投产日期', lambda o: o.produced_at.strftime('%Y-%m-%d')),
            ('备注', lambda o: o.remark or '—'),
        ],
        search_fields=['code', 'product', 'line'],
    ),
}


def _get_ledger(slug):
    led = LEDGERS.get(slug)
    if led is None:
        from django.http import Http404
        raise Http404('未知台账类型')
    return led


def ledger_index(request):
    """台账管理首页:三类主数据的入口卡片 + 各自条目数。"""
    cards = []
    for led in LEDGERS.values():
        cards.append({
            'slug': led.slug,
            'title': led.title,
            'icon': led.icon,
            'count': led.model.objects.count(),
        })
    return render(request, 'board/ledger_index.html',
                  {'cards': cards, 'ledgers': LEDGERS.values(), 'active': 'index'})


def ledger_list(request, slug):
    """某类台账的列表页,支持关键字搜索。"""
    led = _get_ledger(slug)
    q = (request.GET.get('q') or '').strip()
    qs = led.model.objects.all()
    if q:
        cond = Q()
        for f in led.search_fields:
            cond |= Q(**{f'{f}__icontains': q})
        qs = qs.filter(cond)
    ctx = {
        'led': led,
        'headers': [h for h, _ in led.columns],
        'rows': led.rows(qs),
        'q': q,
        'total': qs.count(),
        'ledgers': LEDGERS.values(),
    }
    return render(request, 'board/ledger_list.html', ctx)


def ledger_edit(request, slug, pk=None):
    """新增(pk 为空)或编辑某条台账记录。"""
    led = _get_ledger(slug)
    obj = get_object_or_404(led.model, pk=pk) if pk else None
    if request.method == 'POST':
        form = led.form(request.POST, instance=obj)
        if form.is_valid():
            saved = form.save()
            messages.success(request, f'已保存:{saved}')
            return redirect(reverse('ledger_list', args=[slug]))
    else:
        form = led.form(instance=obj)
    ctx = {
        'led': led,
        'form': form,
        'obj': obj,
        'is_new': obj is None,
        'ledgers': LEDGERS.values(),
    }
    return render(request, 'board/ledger_edit.html', ctx)

from django.contrib import admin
from django.urls import path

from board.views import dashboard, stats_api
from board.ledger import ledger_index, ledger_list, ledger_edit
from board.capture import capture, capture_save, records
from board.trace import trace, trace_api

urlpatterns = [
    path('', dashboard, name='dashboard'),

    # 实时统计 JSON:各工位不良率 + 缺陷 TOP,前端轮询刷新
    path('api/stats/', stats_api, name='stats_api'),

    # 按班次不良追溯 + 缺陷帕累托分析
    path('trace/', trace, name='trace'),
    path('api/trace/', trace_api, name='trace_api'),

    # 数据录入 / 采集:质检记录快速录入 + 流水查看
    path('capture/', capture, name='capture'),
    path('capture/save/', capture_save, name='capture_save'),
    path('capture/records/', records, name='records'),

    # 基础台账管理:工位 / 缺陷类型 / 产品批次 的 列表·新增·编辑
    path('manage/', ledger_index, name='ledger_index'),
    path('manage/<slug:slug>/', ledger_list, name='ledger_list'),
    path('manage/<slug:slug>/new/', ledger_edit, name='ledger_new'),
    path('manage/<slug:slug>/<int:pk>/edit/', ledger_edit, name='ledger_edit'),

    path('admin/', admin.site.urls),
]

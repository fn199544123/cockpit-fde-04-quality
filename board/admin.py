from django.contrib import admin

from .models import Station, Defect, Batch, Inspection


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'line', 'operator', 'order', 'is_active')
    list_filter = ('line', 'is_active')
    search_fields = ('code', 'name', 'operator')


@admin.register(Defect)
class DefectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'severity', 'is_active')
    list_filter = ('severity', 'category', 'is_active')
    search_fields = ('code', 'name')


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ('code', 'product', 'line', 'planned_qty', 'produced_at')
    list_filter = ('line', 'product')
    search_fields = ('code', 'product')
    date_hierarchy = 'produced_at'


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = ('inspected_at', 'station', 'batch', 'is_qualified', 'defect', 'quantity', 'inspector')
    list_filter = ('is_qualified', 'station', 'defect')
    search_fields = ('serial', 'inspector', 'batch__code')
    date_hierarchy = 'inspected_at'

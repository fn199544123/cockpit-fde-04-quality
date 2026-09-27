"""基础台账主数据表单。给「工位 / 缺陷类型 / 产品批次」提供新增/编辑用的 ModelForm。

脱敏铁律:所有示例/占位一律虚构(某企业 / 一·二·三工位 / 层压·焊接·EL检 / 师傅化名)。
"""
from django import forms
from django.utils import timezone

from .models import Station, Defect, Batch, Inspection


_TEXT = {'class': 'fld'}


class StationForm(forms.ModelForm):
    class Meta:
        model = Station
        fields = ['code', 'name', 'line', 'operator', 'order', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={**_TEXT, 'placeholder': '如 ST-01'}),
            'name': forms.TextInput(attrs={**_TEXT, 'placeholder': '如 一工位·层压'}),
            'line': forms.TextInput(attrs={**_TEXT, 'placeholder': '如 一号线'}),
            'operator': forms.TextInput(attrs={**_TEXT, 'placeholder': '师傅化名，如 老张'}),
            'order': forms.NumberInput(attrs={**_TEXT}),
            'is_active': forms.CheckboxInput(attrs={'class': 'chk'}),
        }


class DefectForm(forms.ModelForm):
    class Meta:
        model = Defect
        fields = ['code', 'name', 'category', 'severity', 'description', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={**_TEXT, 'placeholder': '如 DF-201'}),
            'name': forms.TextInput(attrs={**_TEXT, 'placeholder': '如 隐裂'}),
            'category': forms.TextInput(attrs={**_TEXT, 'placeholder': '如 EL检缺陷'}),
            'severity': forms.Select(attrs={**_TEXT}),
            'description': forms.TextInput(attrs={**_TEXT, 'placeholder': '简要说明(可空)'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'chk'}),
        }


class BatchForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = ['code', 'product', 'line', 'planned_qty', 'produced_at', 'remark']
        widgets = {
            'code': forms.TextInput(attrs={**_TEXT, 'placeholder': '如 B20260901-01'}),
            'product': forms.TextInput(attrs={**_TEXT, 'placeholder': '如 某型组件'}),
            'line': forms.TextInput(attrs={**_TEXT, 'placeholder': '如 一号线'}),
            'planned_qty': forms.NumberInput(attrs={**_TEXT}),
            'produced_at': forms.DateInput(attrs={**_TEXT, 'type': 'date'}),
            'remark': forms.TextInput(attrs={**_TEXT, 'placeholder': '备注(可空)'}),
        }


class InspectionForm(forms.ModelForm):
    """质检记录录入表单 —— 业务数据采集的核心。

    交互约定(前端 capture.html 配合):
    - 合格 时 defect 允许为空;不合格 时 defect 必填(在 clean 中校验)。
    - 只列「启用中」的工位/缺陷,批次按投产日期倒序,方便快速下拉选取。
    - 检验时间缺省填当前时刻,支持连续快录时沿用上一条的批次/工位/质检员。
    """

    # 明确的二选一(合格/不良),比裸 checkbox 更适合快录与前端联动
    is_qualified = forms.TypedChoiceField(
        label='判定',
        choices=[('1', '✔ 合格'), ('0', '✖ 不良')],
        coerce=lambda v: v in ('1', 'true', 'True', True),
        initial='1',
        widget=forms.RadioSelect(attrs={'class': 'judge-radio'}),
    )

    class Meta:
        model = Inspection
        fields = ['batch', 'station', 'is_qualified', 'defect',
                  'quantity', 'serial', 'inspector', 'inspected_at', 'note']
        widgets = {
            'batch': forms.Select(attrs={**_TEXT}),
            'station': forms.Select(attrs={**_TEXT}),
            'defect': forms.Select(attrs={**_TEXT}),
            'quantity': forms.NumberInput(attrs={**_TEXT, 'min': 1, 'value': 1}),
            'serial': forms.TextInput(attrs={**_TEXT, 'placeholder': '产品/工单编号(可空,虚构)'}),
            'inspector': forms.TextInput(attrs={**_TEXT, 'placeholder': '质检员化名,如 小李'}),
            'inspected_at': forms.DateTimeInput(
                attrs={**_TEXT, 'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'note': forms.TextInput(attrs={**_TEXT, 'placeholder': '备注(可空)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 下拉只给可用主数据,减少快录时的干扰项
        self.fields['batch'].queryset = Batch.objects.all()
        self.fields['station'].queryset = Station.objects.filter(is_active=True)
        self.fields['defect'].queryset = Defect.objects.filter(is_active=True)
        self.fields['defect'].required = False
        self.fields['inspected_at'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S']
        # 缺省检验时间 = 现在(本地时区),方便一键录入
        if not self.instance.pk and not self.initial.get('inspected_at'):
            self.initial['inspected_at'] = timezone.localtime().strftime('%Y-%m-%dT%H:%M')

    def clean(self):
        cleaned = super().clean()
        is_qualified = cleaned.get('is_qualified')
        defect = cleaned.get('defect')
        if is_qualified:
            # 合格记录不挂缺陷,避免脏数据
            cleaned['defect'] = None
        elif not defect:
            self.add_error('defect', '判定为不良时必须选择缺陷类型。')
        if cleaned.get('quantity') is not None and cleaned['quantity'] <= 0:
            self.add_error('quantity', '检验数量必须大于 0。')
        return cleaned

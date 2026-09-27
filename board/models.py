"""产线质检不良率看板 —— 核心数据模型。

脱敏说明:所有演示数据均为虚构(某企业 / 一工位·二工位·三工位 /
层压·焊接·EL检 缺陷 / 师傅化名 / 虚构编号),严禁出现真实企业、人名、地名。
"""
from django.db import models


class Station(models.Model):
    """工位:产线上的一道质检/加工环节。"""

    code = models.CharField('工位编号', max_length=32, unique=True)
    name = models.CharField('工位名称', max_length=64)
    line = models.CharField('所属产线', max_length=64, default='一号线')
    operator = models.CharField('负责师傅(化名)', max_length=64, blank=True)
    order = models.PositiveIntegerField('工序顺序', default=0)
    is_active = models.BooleanField('启用中', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '工位'
        verbose_name_plural = '工位'
        ordering = ['order', 'code']

    def __str__(self):
        return f'{self.name}({self.code})'


class Defect(models.Model):
    """缺陷类型:质检不合格时归类的缺陷名目。"""

    SEVERITY_CHOICES = [
        ('minor', '轻微'),
        ('major', '一般'),
        ('critical', '严重'),
    ]

    code = models.CharField('缺陷编号', max_length=32, unique=True)
    name = models.CharField('缺陷名称', max_length=64)
    category = models.CharField('缺陷大类', max_length=64, blank=True)
    severity = models.CharField('严重度', max_length=16, choices=SEVERITY_CHOICES, default='major')
    description = models.CharField('说明', max_length=255, blank=True)
    is_active = models.BooleanField('启用中', default=True)

    class Meta:
        verbose_name = '缺陷类型'
        verbose_name_plural = '缺陷类型'
        ordering = ['code']

    def __str__(self):
        return f'{self.name}({self.get_severity_display()})'


class Batch(models.Model):
    """产品批次:一次投产的产品集合,是质检的抽检/全检对象。"""

    code = models.CharField('批次号', max_length=48, unique=True)
    product = models.CharField('产品型号', max_length=64, default='某型组件')
    line = models.CharField('产线', max_length=64, default='一号线')
    planned_qty = models.PositiveIntegerField('计划数量', default=0)
    produced_at = models.DateField('投产日期')
    remark = models.CharField('备注', max_length=255, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '产品批次'
        verbose_name_plural = '产品批次'
        ordering = ['-produced_at', 'code']

    def __str__(self):
        return f'{self.code}·{self.product}'


class Inspection(models.Model):
    """质检记录:某工位对某批次某个产品的一次检验结果。

    合格时 defect 为空;不合格时必须归到一个缺陷类型。
    """

    batch = models.ForeignKey(
        Batch, on_delete=models.CASCADE, related_name='inspections', verbose_name='批次')
    station = models.ForeignKey(
        Station, on_delete=models.PROTECT, related_name='inspections', verbose_name='工位')
    defect = models.ForeignKey(
        Defect, on_delete=models.PROTECT, related_name='inspections',
        null=True, blank=True, verbose_name='缺陷类型')
    is_qualified = models.BooleanField('是否合格', default=True)
    quantity = models.PositiveIntegerField('本条记录数量', default=1)
    serial = models.CharField('产品/工单编号(虚构)', max_length=64, blank=True)
    inspector = models.CharField('质检员(化名)', max_length=64, blank=True)
    inspected_at = models.DateTimeField('检验时间')
    note = models.CharField('备注', max_length=255, blank=True)
    created_at = models.DateTimeField('录入时间', auto_now_add=True)

    class Meta:
        verbose_name = '质检记录'
        verbose_name_plural = '质检记录'
        ordering = ['-inspected_at']
        indexes = [
            models.Index(fields=['station', 'inspected_at']),
            models.Index(fields=['batch', 'is_qualified']),
        ]

    def __str__(self):
        state = '合格' if self.is_qualified else f'不良-{self.defect}'
        return f'{self.station}·{self.batch.code}·{state}'

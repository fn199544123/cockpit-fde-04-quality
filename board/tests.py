"""质检数据录入 / 采集的核心行为测试。"""
from django.test import TestCase
from django.urls import reverse

from .models import Station, Defect, Batch, Inspection


class CaptureTests(TestCase):
    def setUp(self):
        self.batch = Batch.objects.create(
            code='B-TEST-01', product='某型组件', line='一号线',
            planned_qty=100, produced_at='2026-09-23')
        self.station = Station.objects.create(code='WS-T1', name='一工位·层压', order=1)
        self.defect = Defect.objects.create(code='DF-T1', name='隐裂', severity='critical')

    def _post(self, **over):
        data = {'batch': self.batch.id, 'station': self.station.id,
                'is_qualified': '1', 'quantity': '2',
                'inspected_at': '2026-09-23T10:00'}
        data.update(over)
        return self.client.post(reverse('capture_save'), data,
                                HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_pages_load(self):
        self.assertEqual(self.client.get(reverse('capture')).status_code, 200)
        self.assertEqual(self.client.get(reverse('records')).status_code, 200)

    def test_save_qualified(self):
        r = self._post()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['ok'])
        self.assertEqual(Inspection.objects.count(), 1)
        self.assertTrue(Inspection.objects.get().is_qualified)

    def test_bad_requires_defect(self):
        r = self._post(is_qualified='0')
        self.assertEqual(r.status_code, 400)
        self.assertIn('defect', r.json()['errors'])
        self.assertEqual(Inspection.objects.count(), 0)

    def test_bad_with_defect_clears_on_qualified(self):
        # 不良+缺陷:落库并挂缺陷
        self._post(is_qualified='0', defect=self.defect.id)
        ins = Inspection.objects.latest('id')
        self.assertFalse(ins.is_qualified)
        self.assertEqual(ins.defect_id, self.defect.id)
        # 合格即便误传缺陷,也应被清空,避免脏数据
        self._post(is_qualified='1', defect=self.defect.id)
        self.assertIsNone(Inspection.objects.latest('id').defect_id)

    def test_records_filter(self):
        self._post()
        self._post(is_qualified='0', defect=self.defect.id)
        bad = self.client.get(reverse('records'), {'v': 'bad'})
        self.assertContains(bad, '隐裂')

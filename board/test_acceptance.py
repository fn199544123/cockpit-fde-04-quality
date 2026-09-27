from django.test import TestCase
from django.utils import timezone
from .models import Station,Defect,Batch,Inspection

class QualityAcceptance(TestCase):
    def setUp(self):
        self.station=Station.objects.create(code='AC-S1',name='一工位',line='一号线')
        self.defect=Defect.objects.create(code='AC-D1',name='某缺陷',severity='critical')
        self.batch=Batch.objects.create(code='AC-B1',product='某产品',line='一号线',produced_at=timezone.localdate())
    def post(self,**over):
        data=dict(batch=self.batch.pk,station=self.station.pk,defect='',is_qualified='1',quantity=2,serial='AC-0001',inspector='化名甲',inspected_at=timezone.localtime().strftime('%Y-%m-%dT%H:%M'))
        return self.client.post('/capture/save/',dict(data,**over),HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    def test_capture_stats_trace_and_errors(self):
        for quantity in [0,-1,'']:
            self.assertEqual(self.post(quantity=quantity).status_code,400)
        self.assertEqual(self.post(is_qualified='0').status_code,400)
        self.assertEqual(Inspection.objects.count(),0)
        self.assertEqual(self.post().status_code,200)
        self.assertEqual(self.post(is_qualified='0',defect=self.defect.pk,quantity=3).status_code,200)
        self.assertEqual(Inspection.objects.count(),2)
        stats=self.client.get('/api/stats/?window=today').json()
        self.assertEqual(stats['total'],5);self.assertEqual(stats['bad'],3);self.assertEqual(stats['rate'],60)
        self.assertEqual(stats['defects'][0]['name'],'某缺陷')
        self.assertGreater(stats['alerts']['count'],0)
        trace=self.client.get('/api/trace/?window=today').json()
        self.assertTrue(trace)
        for path in ['/','/capture/','/capture/records/?q=AC-0001','/trace/','/manage/']:
            self.assertEqual(self.client.get(path).status_code,200,path)
        self.assertContains(self.client.get('/capture/records/?q=AC-0001'),'AC-0001')

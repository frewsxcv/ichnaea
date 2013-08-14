from datetime import datetime
from datetime import timedelta
from uuid import uuid4

from ichnaea.db import Cell
from ichnaea.db import CellMeasure
from ichnaea.db import Measure
from ichnaea.db import Score
from ichnaea.db import User
from ichnaea.db import WifiMeasure
from ichnaea.decimaljson import encode_datetime
from ichnaea.decimaljson import loads
from ichnaea.tests.base import AppTestCase


class TestSearch(AppTestCase):

    def test_ok(self):
        app = self.app
        session = self.db_session
        cell = Cell()
        cell.lat = 123456781
        cell.lon = 234567892
        cell.radio = 2
        cell.mcc = 123
        cell.mnc = 1
        cell.lac = 2
        cell.cid = 1234
        session.add(cell)
        session.commit()

        res = app.post_json('/v1/search',
                            {"radio": "gsm",
                             "cell": [{"radio": "umts", "mcc": 123, "mnc": 1,
                                       "lac": 2, "cid": 1234}]},
                            status=200)
        self.assertEqual(res.content_type, 'application/json')
        self.assertEqual(res.body, '{"status": "ok", "lat": 12.3456781, '
                                   '"lon": 23.4567892, "accuracy": 35000}')

    def test_not_found(self):
        app = self.app
        res = app.post_json('/v1/search',
                            {"cell": [{"mcc": 1, "mnc": 2,
                                       "lac": 3, "cid": 4}]},
                            status=200)
        self.assertEqual(res.content_type, 'application/json')
        self.assertEqual(res.body, '{"status": "not_found"}')

    def test_wifi_not_found(self):
        app = self.app
        res = app.post_json('/v1/search', {"wifi": [
                            {"key": "abcd"}, {"key": "cdef"}]},
                            status=200)
        self.assertEqual(res.content_type, 'application/json')
        self.assertEqual(res.body, '{"status": "not_found"}')

    def test_error(self):
        app = self.app
        res = app.post_json('/v1/search', {"cell": []}, status=400)
        self.assertEqual(res.content_type, 'application/json')
        self.assertTrue('errors' in res.json)
        self.assertFalse('status' in res.json)

    def test_error_unknown_key(self):
        app = self.app
        res = app.post_json('/v1/search', {"foo": 0}, status=400)
        self.assertEqual(res.content_type, 'application/json')
        self.assertTrue('errors' in res.json)

    def test_error_no_mapping(self):
        app = self.app
        res = app.post_json('/v1/search', [1], status=400)
        self.assertEqual(res.content_type, 'application/json')
        self.assertTrue('errors' in res.json)

    def test_no_json(self):
        app = self.app
        res = app.post('/v1/search', "\xae", status=400)
        self.assertTrue('errors' in res.json)


class TestSubmit(AppTestCase):

    def test_ok_cell(self):
        app = self.app
        cell_data = [
            {"radio": "umts", "mcc": 123, "mnc": 1, "lac": 2, "cid": 1234}]
        res = app.post_json(
            '/v1/submit', {"items": [{"lat": 12.3456781,
                                      "lon": 23.4567892,
                                      "accuracy": 10,
                                      "altitude": 123,
                                      "altitude_accuracy": 7,
                                      "radio": "gsm",
                                      "cell": cell_data}]},
            status=204)
        self.assertEqual(res.body, '')
        session = self.db_session
        result = session.query(Measure).all()
        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertEqual(item.lat, 123456781)
        self.assertEqual(item.lon, 234567892)
        self.assertEqual(item.accuracy, 10)
        self.assertEqual(item.altitude, 123)
        self.assertEqual(item.altitude_accuracy, 7)
        # colander schema adds default value
        cell_data[0]['psc'] = 0
        cell_data[0]['asu'] = 0
        cell_data[0]['signal'] = 0
        cell_data[0]['ta'] = 0

        wanted = loads(item.cell)
        self.assertTrue(len(wanted), 1)
        self.assertTrue(len(cell_data), 1)
        self.assertDictEqual(wanted[0], cell_data[0])
        self.assertTrue(item.wifi is None)

        result = session.query(CellMeasure).all()
        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertEqual(item.lat, 123456781)
        self.assertEqual(item.lon, 234567892)
        self.assertEqual(item.accuracy, 10)
        self.assertEqual(item.altitude, 123)
        self.assertEqual(item.altitude_accuracy, 7)
        self.assertEqual(item.radio, 2)
        self.assertEqual(item.mcc, 123)
        self.assertEqual(item.mnc, 1)
        self.assertEqual(item.lac, 2)
        self.assertEqual(item.cid, 1234)

    def test_ok_wifi(self):
        app = self.app
        wifi_data = [{"key": "ab12"}, {"key": "cd34"}]
        res = app.post_json(
            '/v1/submit', {"items": [{"lat": 12.3456781,
                                      "lon": 23.4567892,
                                      "accuracy": 17,
                                      "wifi": wifi_data}]},
            status=204)
        self.assertEqual(res.body, '')
        session = self.db_session
        result = session.query(Measure).all()
        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertEqual(item.lat, 123456781)
        self.assertEqual(item.lon, 234567892)
        self.assertEqual(item.accuracy, 17)
        self.assertEqual(item.altitude, 0)
        self.assertEqual(item.altitude_accuracy, 0)
        self.assertTrue('"key": "ab12"' in item.wifi)
        self.assertTrue('"key": "cd34"' in item.wifi)
        self.assertTrue(item.cell is None)

        result = session.query(WifiMeasure).all()
        self.assertEqual(len(result), 2)
        item = result[0]
        self.assertEqual(item.lat, 123456781)
        self.assertEqual(item.lon, 234567892)
        self.assertEqual(item.accuracy, 17)
        self.assertEqual(item.altitude, 0)
        self.assertEqual(item.altitude_accuracy, 0)
        self.assertTrue(item.key in ("ab12", "cd34"))
        self.assertEqual(item.channel, 0)
        self.assertEqual(item.signal, 0)

    def test_ok_wifi_frequency(self):
        app = self.app
        wifi_data = [
            {"key": "99"},
            {"key": "aa", "frequency": 2427},
            {"key": "bb", "channel": 7},
            {"key": "cc", "frequency": 5200},
            {"key": "dd", "frequency": 5700},
            {"key": "ee", "frequency": 3100},
            {"key": "ff", "frequency": 2412, "channel": 9},
        ]
        res = app.post_json(
            '/v1/submit', {"items": [{"lat": 12.345678,
                                      "lon": 23.456789,
                                      "wifi": wifi_data}]},
            status=204)
        self.assertEqual(res.body, '')
        session = self.db_session
        result = session.query(Measure).all()
        self.assertEqual(len(result), 1)
        item = result[0]
        measure_wifi = loads(item.wifi)
        measure_wifi = dict([(m['key'], m) for m in measure_wifi])
        for k, v in measure_wifi.items():
            self.assertFalse('frequency' in v)
        self.assertEqual(measure_wifi['99']['channel'], 0)
        self.assertEqual(measure_wifi['aa']['channel'], 4)
        self.assertEqual(measure_wifi['bb']['channel'], 7)
        self.assertEqual(measure_wifi['cc']['channel'], 40)
        self.assertEqual(measure_wifi['dd']['channel'], 140)
        self.assertEqual(measure_wifi['ee']['channel'], 0)
        self.assertEqual(measure_wifi['ff']['channel'], 9)

    def test_batches(self):
        app = self.app
        wifi_data = [{"key": "aa"}, {"key": "bb"}]
        items = [{"lat": 12.34, "lon": 23.45 + i, "wifi": wifi_data}
                 for i in range(10)]
        res = app.post_json('/v1/submit', {"items": items}, status=204)
        self.assertEqual(res.body, '')

        # let's add a bad one
        items.append({'whatever': 'xx'})
        res = app.post_json('/v1/submit', {"items": items}, status=400)

    def test_time(self):
        app = self.app
        # test two weeks ago and "now"
        time = (datetime.utcnow() - timedelta(14)).replace(microsecond=0)
        tstr = encode_datetime(time)
        app.post_json(
            '/v1/submit', {"items": [
                {"lat": 1.0, "lon": 2.0, "wifi": [{"key": "a"}], "time": tstr},
                {"lat": 2.0, "lon": 3.0, "wifi": [{"key": "b"}]},
            ]},
            status=204)
        session = self.db_session
        result = session.query(Measure).all()
        self.assertEqual(len(result), 2)
        for item in result:
            if '"key": "a"' in item.wifi:
                self.assertEqual(item.time, time)
            else:
                self.assertEqual(item.time.date(), datetime.utcnow().date())

    def test_time_future(self):
        app = self.app
        time = "2070-01-01T11:12:13.456Z"
        app.post_json(
            '/v1/submit', {"items": [
                {"lat": 1.0, "lon": 2.0, "wifi": [{"key": "a"}], "time": time},
                {"lat": 2.0, "lon": 3.0, "wifi": [{"key": "b"}]},
            ]},
            status=204)
        session = self.db_session
        result = session.query(Measure).all()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].time, result[1].time)

    def test_time_past(self):
        app = self.app
        time = "2011-01-01T11:12:13.456Z"
        app.post_json(
            '/v1/submit', {"items": [
                {"lat": 1.0, "lon": 2.0, "wifi": [{"key": "a"}], "time": time},
                {"lat": 2.0, "lon": 3.0, "wifi": [{"key": "b"}]},
            ]},
            status=204)
        session = self.db_session
        result = session.query(Measure).all()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].time, result[1].time)

    def test_token_nickname_header(self):
        app = self.app
        uid = uuid4().hex
        nickname = 'World Tr\xc3\xa4veler'
        app.post_json(
            '/v1/submit', {"items": [
                {"lat": 1.0, "lon": 2.0, "wifi": [{"key": "a"}]},
                {"lat": 2.0, "lon": 3.0, "wifi": [{"key": "b"}]},
            ]},
            headers={'X-Token': uid, 'X-Nickname': nickname},
            status=204)
        session = self.db_session
        result = session.query(User).all()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].token, uid)
        self.assertEqual(result[0].nickname, nickname.decode('utf-8'))
        result = session.query(Score).all()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].value, 2)

    def test_token_nickname_header_error(self):
        app = self.app
        app.post_json(
            '/v1/submit', {"items": [
                {"lat": 1.0, "lon": 2.0, "wifi": [{"key": "a"}]},
            ]},
            headers={'X-Token': "123.45", 'X-Nickname': "abcd"},
            status=204)
        session = self.db_session
        result = session.query(User).all()
        self.assertEqual(len(result), 0)
        result = session.query(Score).all()
        self.assertEqual(len(result), 0)

    def test_token_nickname_header_update(self):
        app = self.app
        uid = uuid4().hex
        nickname = 'World Tr\xc3\xa4veler'
        session = self.db_session
        user = User(id=1, token=uid, nickname=nickname.decode('utf-8'))
        session.add(user)
        score = Score(id=1, userid=1, value=2)
        session.add(score)
        session.commit()
        # request updating nickname
        nickname2 = "Tr\xc3\xa4veler's friend"
        app.post_json(
            '/v1/submit', {"items": [
                {"lat": 1.0, "lon": 2.0, "wifi": [{"key": "a"}]},
            ]},
            headers={'X-Token': uid, 'X-Nickname': nickname2},
            status=204)
        result = session.query(User).all()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].token, uid)
        self.assertEqual(result[0].nickname.encode('utf-8'), nickname2)
        result = session.query(Score).all()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].value, 3)

    def test_error(self):
        app = self.app
        res = app.post_json(
            '/v1/submit', {"items": [{"lat": 12.3, "lon": 23.4, "cell": []}]},
            status=400)
        self.assertEqual(res.content_type, 'application/json')
        self.assertTrue('errors' in res.json)
        self.assertFalse('status' in res.json)

    def test_error_unknown_key(self):
        app = self.app
        res = app.post_json(
            '/v1/submit', {"items": [{"lat": 12.3, "lon": 23.4, "foo": 1}]},
            status=400)
        self.assertTrue('errors' in res.json)

    def test_error_no_mapping(self):
        app = self.app
        res = app.post_json('/v1/submit', [1], status=400)
        self.assertTrue('errors' in res.json)

    def test_no_json(self):
        app = self.app
        res = app.post('/v1/submit', "\xae", status=400)
        self.assertTrue('errors' in res.json)


class TestHeartbeat(AppTestCase):

    def test_ok(self):
        app = self.app
        res = app.get('/__heartbeat__', status=200)
        self.assertEqual(res.content_type, 'application/json')
        self.assertEqual(res.json['status'], "OK")

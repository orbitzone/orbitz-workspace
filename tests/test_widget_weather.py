"""WX-01 forecast/geocoding contracts with synthetic responses and XDG only."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs,urlsplit

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
import weather_backend as weather

class Response(io.BytesIO):
    def __init__(self,value):super().__init__(json.dumps(value).encode())


class ForecastTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.env=patch.dict(os.environ,{'XDG_CACHE_HOME':folder.name+'/cache','XDG_CONFIG_HOME':folder.name+'/config','ORBITZ_LOCALE':'pt-BR'})
        self.env.start();self.addCleanup(self.env.stop)
        self.now=datetime.now(timezone.utc).replace(second=0,microsecond=0)
        self.selected=dict(latitude=0.0,longitude=0.0,name='Cidade externa {name}')

    def raw(self,unit='celsius'):
        symbol='°C' if unit=='celsius' else '°F';today=self.now.date()
        return dict(latitude=0.0,longitude=0.0,timezone='UTC',
                    current=dict(time=self.now.replace(tzinfo=None).isoformat(timespec='minutes'),temperature_2m=20,apparent_temperature=21,relative_humidity_2m=55,weather_code=0,is_day=1),
                    current_units=dict(temperature_2m=symbol,apparent_temperature=symbol,relative_humidity_2m='%'),
                    daily=dict(time=[(today+timedelta(days=i)).isoformat() for i in range(7)],temperature_2m_min=[10]*7,temperature_2m_max=[25]*7,precipitation_probability_max=[30]*7,weather_code=[1]*7,wind_speed_10m_max=[40]*7),
                    daily_units=dict(temperature_2m_min=symbol,temperature_2m_max=symbol,precipitation_probability_max='%',wind_speed_10m_max='km/h'))

    def test_solar_times_duration_validation_and_legacy_cache(self):
        raw=self.raw();dates=raw['daily']['time']
        raw['daily'].update(sunrise=[d+'T05:30' for d in dates],sunset=[d+'T18:15' for d in dates],daylight_duration=[45900]*7)
        raw['daily_units'].update(sunrise='iso8601',sunset='iso8601',daylight_duration='s')
        value=weather.parse_forecast(raw,self.selected,'celsius',now=self.now.timestamp())
        self.assertEqual(value['days'][0]['daylight_duration'],45900)
        self.assertEqual(value['days'][0]['sunrise'],dates[0]+'T05:30')
        raw['daily']['daylight_duration'][0]=90000
        with self.assertRaises(weather.WeatherError):weather.parse_forecast(raw,self.selected,'celsius',now=self.now.timestamp())
        self.assertNotIn('sunrise',weather.parse_forecast(self.raw(),self.selected,'celsius',now=self.now.timestamp())['days'][0])

    def opener(self,data=None):return Mock(return_value=Response(data if data is not None else self.raw()))

    def test_seven_days_and_request_units_timezone_limits_attribution(self):
        opener=self.opener(self.raw('fahrenheit'))
        value=weather.forecast(self.selected,'fahrenheit',opener=opener,now=self.now.timestamp())
        self.assertEqual(len(value['days']),7);self.assertEqual(value['unit'],'fahrenheit')
        self.assertEqual(value['current']['humidity'],55);self.assertFalse(value['stale'])
        self.assertEqual(value['location']['name'],self.selected['name'])
        self.assertEqual(value['attribution']['license'],'CC-BY-4.0')
        request=opener.call_args.args[0];query=parse_qs(urlsplit(request.full_url).query)
        self.assertEqual(urlsplit(request.full_url).hostname,'api.open-meteo.com')
        self.assertEqual(query['forecast_days'],['7']);self.assertEqual(query['temperature_unit'],['fahrenheit']);self.assertEqual(query['timezone'],['auto'])
        self.assertEqual(opener.call_args.kwargs['timeout'],8)

    def test_cache_is_partitioned_by_coordinates_and_unit_and_relabels_without_network(self):
        weather.forecast(self.selected,opener=self.opener(),now=self.now.timestamp())
        missing=Mock(side_effect=OSError('offline'))
        renamed={**self.selected,'name':'Another name'}
        cached=weather.forecast(renamed,opener=missing,now=self.now.timestamp())
        self.assertEqual(cached['location']['name'],'Another name');missing.assert_not_called()
        for selected,unit in ((self.selected,'fahrenheit'),({**self.selected,'latitude':1.0},'celsius')):
            with self.assertRaises(weather.WeatherError):weather.forecast(selected,unit,opener=missing,now=self.now.timestamp())
        self.assertNotEqual(weather.cache_name(self.selected,'celsius'),weather.cache_name(self.selected,'fahrenheit'))

    def test_daily_wind_kmh_request_serialization_ranges_and_cache_upgrade(self):
        for unit in ('celsius','fahrenheit'):
            raw=self.raw(unit);raw['daily']['wind_speed_10m_max']=[0,39.9,40,40.1,120,300,500]
            opener=self.opener(raw)
            value=weather.forecast(self.selected,unit,opener=opener,now=self.now.timestamp())
            self.assertEqual([d['wind_speed_max'] for d in value['days']],raw['daily']['wind_speed_10m_max'])
            params=parse_qs(urlsplit(opener.call_args.args[0].full_url).query)
            self.assertIn('wind_speed_10m_max',params['daily'][0].split(','))
            self.assertEqual(params['wind_speed_unit'],['kmh'])
            cached=weather.forecast(self.selected,unit,opener=Mock(side_effect=AssertionError('cache miss')),now=self.now.timestamp())
            self.assertEqual(cached['days'],value['days'])
        self.assertEqual(weather.WIND_ICON_THRESHOLD_KMH,40)
        name=weather.cache_name(self.selected,'celsius')
        self.assertTrue(name.startswith('weather-v2-'))
        old=self.raw();old['daily'].pop('wind_speed_10m_max');old['daily_units'].pop('wind_speed_10m_max')
        weather.save(name.replace('weather-v2-','weather-v1-'),dict(identity=[0.0,0.0,'celsius'],fetched=self.now.timestamp(),data=old))
        # Even a damaged v2 entry without wind must be rejected and refetched.
        weather.save(name,dict(identity=[0.0,0.0,'celsius'],fetched=self.now.timestamp(),data=old))
        opener=self.opener();weather.forecast(self.selected,opener=opener,now=self.now.timestamp());opener.assert_called_once()
        for values in ([-1]*7,[500.1]*7,[True]*7,[None]*7,[float('nan')]*7,[float('inf')]*7,[40]*6):
            raw=self.raw();raw['daily']['wind_speed_10m_max']=values
            with self.subTest(values=values),self.assertRaises(weather.WeatherError):
                weather.parse_forecast(raw,self.selected,'celsius',now=self.now.timestamp())
        for bad_unit in ('mph','m/s',None):
            raw=self.raw();raw['daily_units']['wind_speed_10m_max']=bad_unit
            with self.subTest(unit=bad_unit),self.assertRaises(weather.WeatherError):
                weather.parse_forecast(raw,self.selected,'celsius',now=self.now.timestamp())

    def test_manual_refresh_and_stale_cache_never_become_live_forecast_json(self):
        weather.forecast(self.selected,opener=self.opener(),now=self.now.timestamp())
        offline=Mock(side_effect=OSError('offline'))
        with self.assertRaises(weather.WeatherError):weather.forecast(self.selected,refresh=True,opener=offline,now=self.now.timestamp())
        later=self.now.timestamp()+600
        with self.assertRaises(weather.WeatherError):weather.forecast(self.selected,opener=offline,now=later)
        stale=weather.forecast(self.selected,opener=offline,now=later,allow_stale=True)
        self.assertTrue(stale['stale']);self.assertIn('última previsão salva',weather.render_summary(stale))
        with self.assertRaises(weather.WeatherError):weather.forecast(self.selected,opener=offline,now=self.now.timestamp()+90000,allow_stale=True)

    def test_invalid_ranges_types_dates_units_location_and_arrays_are_rejected(self):
        invalid=[]
        for field,value in [('temperature_2m',float('nan')),('relative_humidity_2m',101),('weather_code',1.5),('is_day',True),('time','not-a-date')]:
            item=self.raw();item['current'][field]=value;invalid.append(item)
        for field,value in [('temperature_2m_min',[0]*6),('temperature_2m_max',[0]*7),('precipitation_probability_max',[None]*7),('weather_code',[True]*7),('time',['2020-01-01']*7)]:
            item=self.raw();item['daily'][field]=value;invalid.append(item)
        for field,value in [('timezone','../../etc/passwd'),('latitude',50),('longitude',100)]:
            item=self.raw();item[field]=value;invalid.append(item)
        item=self.raw();item['current_units']['temperature_2m']='°F';invalid.append(item)
        for item in invalid:
            with self.subTest(item=item),self.assertRaises(weather.WeatherError):weather.parse_forecast(item,self.selected,'celsius',now=self.now.timestamp())

    def test_bounded_json_and_network_failures_are_sanitized(self):
        for raw in (b'x'*(weather.MAX_RESPONSE+1),b'['*1100+b'0'+b']'*1100,b'{"x":'+b'9'*5000+b'}',b'{"x":1e9999999}',b'not json'):
            opener=Mock(return_value=io.BytesIO(raw))
            with self.assertRaises(weather.WeatherError):weather.get_json(weather.API,opener)
        error=HTTPError(weather.API,429,'REMOTE_SECRET',{},None)
        with self.assertRaises(weather.WeatherError) as caught:weather.get_json(weather.API,Mock(side_effect=error))
        self.assertNotIn('REMOTE_SECRET',str(caught.exception));self.assertNotIn('http',str(caught.exception))

    def test_summary_humidity_locale_and_units(self):
        value=weather.parse_forecast(self.raw(),self.selected,'celsius',now=self.now.timestamp());value['stale']=False
        with patch.dict(os.environ,{'ORBITZ_LOCALE':'en-US'}):
            summary=weather.render_summary(value)
            self.assertIn('Humidity 55%',summary);self.assertIn('Feels like 21°C',summary);self.assertNotIn('Umidade',summary)
        self.assertEqual(len(summary.splitlines()),4)
        value['unit']='fahrenheit'
        self.assertIn('°F',weather.render_summary(value))

    def test_geocoding_is_fixed_host_country_encoded_locale_bounded_and_not_a_full_catalog(self):
        item=dict(id=1,name='São Paulo',admin1='São Paulo',country='Brasil',country_code='BR',latitude=-23.5,longitude=-46.6,timezone='America/Sao_Paulo')
        opener=self.opener({'results':[item]})
        with patch.dict(os.environ,{'ORBITZ_LOCALE':'en-US'}):result=weather.geocode('São & Paulo','br',opener=opener)
        self.assertEqual(result['results'][0]['name'],'São Paulo');self.assertFalse(result['complete'])
        parsed=urlsplit(opener.call_args.args[0].full_url);params=parse_qs(parsed.query)
        self.assertEqual(parsed.hostname,'geocoding-api.open-meteo.com');self.assertEqual(params['countryCode'],['BR']);self.assertEqual(params['name'],['São & Paulo']);self.assertEqual(params['language'],['en'])
        self.assertEqual(weather.geocode('Empty',opener=self.opener({}))['results'],[])
        for query in ('a','x'*101,'bad\nquery'):
            unused=Mock()
            with self.assertRaises(weather.WeatherError):weather.geocode(query,opener=unused)
            unused.assert_not_called()
        with self.assertRaises(weather.WeatherError):weather.geocode('City','BR&x=1',opener=Mock())
        with self.assertRaises(weather.WeatherError):weather.geocode('City',opener=self.opener({'results':[item]*11}))


    def test_no_redirects_are_followed(self):
        self.assertIsNone(weather.NoRedirect().redirect_request(None,None,302,'',{},'https://untrusted.invalid/'))


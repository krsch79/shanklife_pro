# BalleTour GPS Survey

Separat intern webapp for å måle opp og lagre GPS-koordinater på Ballerud.

Appen står i egen mappe og deler bare database med Shanklife Pro/BalleTour. Den oppretter sin egen tabell, `balletour_survey_features`, i samme database som `DATABASE_URL` peker på. Uten `DATABASE_URL` bruker den `instance/shanklife_pro.db`, samme lokale fallback som hovedappen.

## Kjør lokalt

```bash
./run_balletour_survey.sh
```

Åpne `http://127.0.0.1:5060` på mobilen eller maskinen. Mobil-GPS krever normalt HTTPS eller `localhost`; ved faktisk bruk på telefon bør appen kjøres bak HTTPS/reversproxy eller åpnes via en sikker tunnel.

## API

- `GET /api/features` viser lagrede features.
- `POST /api/features` lagrer Point, LineString eller Polygon som GeoJSON-geometri.
- `DELETE /api/features/<id>` sletter en feature.
- `GET /api/export.geojson` eksporterer alt som GeoJSON FeatureCollection.

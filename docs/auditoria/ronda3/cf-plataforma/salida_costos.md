## Horas activas supuestas

- 24/7 (720 h; hoy, por el cron */10): 720,00 h/mes
- Horario comercial 12 h x 26 d (312 h): 312,00 h/mes
- A demanda, sleepAfter 10 min: 155,33 h/mes
- A demanda, sleepAfter 15 min: 189,00 h/mes
- A demanda, sleepAfter 30 min: 290,00 h/mes

## Costo mensual en USD (contenedor + DO + $5 del plan)

| Patron | Horas | Tipo | CPU 3 % | CPU 10 % | CPU 25 % | de ello memoria | disco |
|---|---|---|---|---|---|---|---|
| 24/7 (720 h; hoy, por el cron */10) | 720,00 | basic | 11,93 | 12,78 | 14,72 | 6,26 | 0,68 |
| 24/7 (720 h; hoy, por el cron */10) | 720,00 | standard-1 | 32,42 | 34,24 | 38,13 | 25,70 | 1,40 |
| 24/7 (720 h; hoy, por el cron */10) | 720,00 | standard-2 | 46,89 | 50,52 | 58,29 | 38,66 | 2,13 |
| Horario comercial 12 h x 26 d (312 h) | 312,00 | basic | 7,85 | 7,96 | 8,80 | 2,58 | 0,26 |
| Horario comercial 12 h x 26 d (312 h) | 312,00 | standard-1 | 16,59 | 17,26 | 18,94 | 11,01 | 0,58 |
| Horario comercial 12 h x 26 d (312 h) | 312,00 | standard-2 | 22,74 | 24,31 | 27,68 | 16,62 | 0,89 |
| A demanda, sleepAfter 10 min | 155,33 | basic | 6,28 | 6,28 | 6,53 | 1,17 | 0,11 |
| A demanda, sleepAfter 10 min | 155,33 | standard-1 | 10,63 | 10,74 | 11,58 | 5,37 | 0,26 |
| A demanda, sleepAfter 10 min | 155,33 | standard-2 | 13,58 | 14,25 | 15,93 | 8,16 | 0,42 |
| A demanda, sleepAfter 15 min | 189,00 | basic | 6,62 | 6,62 | 7,02 | 1,48 | 0,14 |
| A demanda, sleepAfter 15 min | 189,00 | standard-1 | 11,91 | 12,14 | 13,16 | 6,58 | 0,33 |
| A demanda, sleepAfter 15 min | 189,00 | standard-2 | 15,50 | 16,41 | 18,45 | 9,98 | 0,52 |
| A demanda, sleepAfter 30 min | 290,00 | basic | 7,63 | 7,70 | 8,48 | 2,39 | 0,24 |
| A demanda, sleepAfter 30 min | 290,00 | standard-1 | 15,75 | 16,34 | 17,91 | 10,22 | 0,53 |
| A demanda, sleepAfter 30 min | 290,00 | standard-2 | 21,44 | 22,90 | 26,03 | 15,44 | 0,83 |

## Desglose 24/7 standard-2 (configuracion actual de edge/wrangler.jsonc)

- CPU 3 %: memoria 38,66 + CPU 1,11 + disco 2,13 + DO 0,00 = 41,89 -> con plan 46,89
- CPU 10 %: memoria 38,66 + CPU 4,73 + disco 2,13 + DO 0,00 = 45,52 -> con plan 50,52
- CPU 25 %: memoria 38,66 + CPU 12,51 + disco 2,13 + DO 0,00 = 53,29 -> con plan 58,29

## Horas que un cron mantiene despierto el contenedor (sin contar trafico)

| Intervalo del cron | sleepAfter 10 min | 15 min | 30 min |
|---|---|---|---|
| cada 10 min | 720,00 | 720,00 | 720,00 |
| cada 30 min | 288,00 | 408,00 | 720,00 |
| cada 60 min | 144,00 | 204,00 | 384,00 |
| cada 180 min | 48,00 | 68,00 | 128,00 |
| cada 360 min | 24,00 | 34,00 | 64,00 |
| cada 1440 min | 6,00 | 8,50 | 16,00 |

## Costo del cron solo (standard-2, CPU 10 %, sin trafico), USD/mes con plan

- cron cada 10 min, sleepAfter 30 min: 720,00 h -> 50,52
- cron cada 60 min, sleepAfter 10 min: 144,00 h -> 13,52
- cron cada 360 min, sleepAfter 10 min: 24,00 h -> 6,09
- cron cada 1440 min, sleepAfter 10 min: 6,00 h -> 5,10

## Punto en que se agota lo incluido (horas/mes)

- basic: memoria 25,00 h, disco 50,00 h, CPU 3 % -> 833,33 h, 10 % -> 250,00 h, 25 % -> 100,00 h
- standard-1: memoria 6,25 h, disco 25,00 h, CPU 3 % -> 416,67 h, 10 % -> 125,00 h, 25 % -> 50,00 h
- standard-2: memoria 4,17 h, disco 16,67 h, CPU 3 % -> 208,33 h, 10 % -> 62,50 h, 25 % -> 25,00 h

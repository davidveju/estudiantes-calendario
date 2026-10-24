# 🏀 Movistar Estudiantes 26/27 — Calendario

Todos los partidos del Movistar Estudiantes masculino 26/27 —liga Primera FEB,
Copa España y playoffs— directos en tu calendario. Te suscribes una vez y se
actualiza solo: los partidos jugados aparecen con el resultado, sin que tengas
que hacer nada.

| | |
|---|---|
| 📅 Fichero | [`estudiantes.ics`](estudiantes.ics) — 34 jornadas de liga + Copa España (y playoffs si se clasifica) |
| 📡 Fuentes | Liga en [competiciones.feb.es](https://competiciones.feb.es/estadisticas/Calendario.aspx) · Copa en [feb.es](https://www.feb.es/competiciones/resultados/copaespaa/73/2026) |
| 🔄 Actualización | Automática, lunes, miércoles y viernes 12:00 UTC (vía GitHub Actions) |

> La Copa España ya está incluida. Los playoffs se añadirán si el equipo se clasifica.

## 📲 Suscribirse

### Google Calendar

1. Abre [Google Calendar](https://calendar.google.com) en el navegador.
2. En `Otros calendarios`, pulsa `+` → `Desde URL`.
3. Pega esta URL y pulsa `Añadir calendario`:

   ```text
   https://raw.githubusercontent.com/davidveju/estudiantes-calendario/main/estudiantes.ics
   ```

> Google refresca los calendarios suscritos cada 12–24 h: los horarios y
> resultados llegan con ese retardo. No vale para seguir el directo.

### Apple Calendar (iPhone / Mac)

1. Ajustes → Calendario → Cuentas → Añadir cuenta → Otra → Añadir calendario suscrito.
2. Pega la misma URL de arriba y pulsa Siguiente.

### Outlook

1. Calendario → Añadir calendario → Suscribirse desde la web.
2. Pega la URL, ponle nombre (p. ej. `Estudiantes 26/27`) e importa.

## 🔍 Cómo se ven los eventos

| Estado | Ejemplo |
|---|---|
| Pendiente (liga) | 🏀 Fibwi Mallorca - Estu (J5) — hora real de Madrid |
| Victoria fuera | 🏀 Caja Rural CB Zamora - Estu (J2: 73-80 ✅) |
| Derrota (formato) | 🏀 Rival - Estu (J7: 85-78 ❌) |
| Copa | 🏆 Caceres Patrimonio de la Humanidad - Estu (Copa 1/8, fecha por confirmar) |

- Cada evento lleva la sede (pabellón + dirección) y el enlace al acta oficial de la FEB.
- Los partidos no bloquean tu disponibilidad (se marcan como libres).

## ⚙️ Cómo funciona

- [`scripts/scrape.py`](scripts/scrape.py) (solo librería estándar de Python, sin dependencias)
  lee la liga en [competiciones.feb.es](https://competiciones.feb.es/estadisticas/Calendario.aspx)
  y la Copa en [feb.es](https://www.feb.es/competiciones/resultados/copaespaa/73/2026),
  y regenera [`datos/partidos.json`](datos/partidos.json)
  y [`estudiantes.ics`](estudiantes.ics), con identificadores estables por jornada y ronda
  para que tu calendario actualice cada partido en su sitio, sin duplicados.
- El workflow [`.github/workflows/update.yml`](.github/workflows/update.yml) lo ejecuta
  lunes, miércoles y viernes; si no hay cambios (ni horarios nuevos ni resultados),
  no se publica nada.
- La Copa conserva las rondas anteriores aunque la FEB ya solo muestre la fase actual.
- Los tests de los parsers y del ICS se ejecutan en cada actualización
  (`python3 -m unittest discover -s scripts -p "test_*.py"`), y el ICS se valida
  a nivel de bytes (CRLF y plegado RFC 5545) antes de publicarlo.

```
estudiantes-calendario/
├── estudiantes.ics            ← el fichero al que te suscribes (siempre aquí)
├── scripts/scrape.py          ← genera el calendario desde la FEB
├── scripts/validate_ics.py    ← valida CRLF, plegado y estructura del ICS
├── scripts/test_scrape.py     ← tests sin red de parsers e ICS
├── scripts/update.sh          ← regenera + commit + push en local
├── datos/partidos.json        ← estado: horarios, resultados, actas
├── datos/sedes.json           ← caché de pabellones por partido
├── datos/fechas_reales.json   ← horas verificadas que mandan sobre la FEB
└── .github/workflows/         ← actualización automática lun/mié/vie 12:00 UTC
```

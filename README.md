# Movistar Estudiantes 26/27 — calendario .ics

Calendario del Movistar Estudiantes masculino (Primera FEB 26/27) en formato
iCalendar. Se actualiza solo: los partidos jugados muestran el resultado.

- Fichero: [`estudiantes.ics`](estudiantes.ics) (34 jornadas de liga regular)
- Fuente: [FEB – Competiciones](https://competiciones.feb.es/estadisticas/Calendario.aspx)
- Copa España y playoffs: se añadirán cuando la FEB publique sus calendarios.

## Suscribirse en Google Calendar

1. Abre [Google Calendar](https://calendar.google.com) en el navegador.
2. `Otros calendarios` → `+` → `Desde URL`.
3. Pega la URL raw de este repo:
   `https://raw.githubusercontent.com/<USUARIO>/<REPO>/main/estudiantes.ics`
4. `Añadir calendario`.

Google refresca los calendarios suscritos cada 12–24 h: horarios y resultados
llegan con ese retardo (no vale para seguir el directo).

## Formato de los eventos

- Pendiente: `🏀 Estu vs Rival en casa/fuera (J12)` — hora real de Madrid.
- Jugado: `🏀 Estu 78-65 Rival ✅/❌ (J12)` — resultado desde la web FEB, con
  enlace al acta en la descripción.
- Los eventos no bloquean disponibilidad (`TRANSPARENT`).

## Actualización

`scrape.py` (solo stdlib) regenera `datos/partidos.json` y `estudiantes.ics`
con UIDs estables por jornada. Cron previsto: lunes y viernes 12:00 UTC.

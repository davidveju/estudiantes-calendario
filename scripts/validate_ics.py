#!/usr/bin/env python3
"""Valida el ICS generado sin dependencias: CRLF, plegado RFC 5545 y estructura."""
import re
import sys
from pathlib import Path


def validar(path: Path) -> list[str]:
    data = path.read_bytes()
    errores: list[str] = []
    if not data:
        return ["el fichero esta vacio"]
    if not data.endswith(b"\r\n"):
        errores.append("el fichero no termina en CRLF")
    if b"\r\r\n" in data:
        errores.append("hay secuencias CR CR LF")
    resto = data.replace(b"\r\n", b"")
    if b"\r" in resto:
        errores.append("hay CR sin LF")
    if b"\n" in resto:
        errores.append("hay LF sin CR")

    lineas = data.split(b"\r\n")
    if lineas and lineas[-1] == b"":
        lineas.pop()
    for i, linea in enumerate(lineas, 1):
        if len(linea) > 75:
            errores.append(f"linea {i}: {len(linea)} octetos (>75)")
        if b"\r" in linea or b"\n" in linea:
            errores.append(f"linea {i}: salto de linea embebido")
        try:
            linea.decode("utf-8")
        except UnicodeDecodeError:
            errores.append(f"linea {i}: UTF-8 invalido")

    if not lineas or lineas[0] != b"BEGIN:VCALENDAR":
        errores.append("no empieza por BEGIN:VCALENDAR")
    if not lineas or lineas[-1] != b"END:VCALENDAR":
        errores.append("no termina por END:VCALENDAR")

    inicios = sum(1 for x in lineas if x == b"BEGIN:VEVENT")
    finales = sum(1 for x in lineas if x == b"END:VEVENT")
    if inicios != finales:
        errores.append(f"VEVENT desbalanceados: {inicios} BEGIN / {finales} END")
    uids = [x[4:].decode("utf-8", "replace") for x in lineas if x.startswith(b"UID:")]
    if len(uids) != inicios:
        errores.append(f"UIDs ({len(uids)}) != VEVENT ({inicios})")
    if len(set(uids)) != len(uids):
        errores.append("hay UIDs duplicados")
    for prefijo in (b"DTSTART:", b"DTEND:"):
        n = sum(1 for x in lineas if x.startswith(prefijo))
        if n != inicios:
            errores.append(f"{prefijo.decode()} ({n}) != VEVENT ({inicios})")
    for i, linea in enumerate(lineas, 1):
        if linea.startswith((b"DTSTART:", b"DTEND:")) and not re.fullmatch(
                rb"DT(?:START|END):\d{8}T\d{6}Z", linea):
            errores.append(f"linea {i}: fecha no UTC/ISO basica ({linea[:40]!r})")
    return errores


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "estudiantes.ics")
    if not path.exists():
        print(f"ERROR: no existe {path}")
        return 1
    errores = validar(path)
    if errores:
        for e in errores:
            print(f"ERROR: {e}")
        return 1
    lineas = path.read_bytes().count(b"\r\n")
    print(f"ICS OK: {path} ({lineas} lineas, plegado <=75 octetos, CRLF)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

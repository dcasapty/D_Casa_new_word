#!/usr/bin/env python3
"""Sustituto de /usr/bin/time -v: ejecuta un comando y escribe en stderr tiempo real, CPU y pico RSS."""
import resource
import subprocess
import sys
import time

t = time.time()
rc = subprocess.call(sys.argv[1:])
r = resource.getrusage(resource.RUSAGE_CHILDREN)
print(f'Elapsed {time.time() - t:.2f}\nUser time {r.ru_utime:.2f}\nSystem time {r.ru_stime:.2f}\n'
      f'Maximum resident set size (kbytes): {r.ru_maxrss}', file=sys.stderr)
sys.exit(rc)

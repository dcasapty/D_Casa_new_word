#!/usr/bin/env python3
"""Inventario del bucket S3 local: bytes totales, objetos y tamaño de segmentos WAL archivados.
Uso: s3_inventario.py [desde_epoch] [hasta_epoch]  (filtra segmentos WAL por LastModified)
"""
import sys, statistics, boto3, warnings
warnings.filterwarnings("ignore")
s = boto3.client("s3", endpoint_url="https://127.0.0.1:9100", verify=False, region_name="us-east-1",
                 aws_access_key_id="x", aws_secret_access_key="x")
desde = float(sys.argv[1]) if len(sys.argv) > 1 else 0; hasta = float(sys.argv[2]) if len(sys.argv) > 2 else 9e12
tot = n = 0; wal = []; backup = 0
for page in s.get_paginator("list_objects_v2").paginate(Bucket="dcasa-pg"):
    for o in page.get("Contents", []):
        tot += o["Size"]; n += 1
        k = o["Key"]
        if "/backup/" in k: backup += o["Size"]
        if "/archive/" in k and k.endswith(".zst") and "-" in k.rsplit("/", 1)[-1]:
            t = o["LastModified"].timestamp()
            if desde <= t <= hasta: wal.append(o["Size"])
print(f"bucket: {n} objetos, {tot/1e6:.1f} MB (respaldos base {backup/1e6:.1f} MB)")
if wal:
    print(f"segmentos WAL en ventana: {len(wal)}; mediana {statistics.median(wal)/1024:.1f} KiB; "
          f"media {statistics.mean(wal)/1024:.1f} KiB; max {max(wal)/1024:.1f} KiB; total {sum(wal)/1e6:.2f} MB")

"""Offline SQLite backup/restore. Stop the service before using either command."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def transfer(source: Path, destination: Path):
    source=source.resolve();destination=destination.resolve()
    if source==destination: raise ValueError('备份目标不能与来源相同')
    sources=[source/name for name in ('kitchen.db','checkpoints.db') if (source/name).is_file()]
    if not sources: raise ValueError('来源没有项目数据库')
    if any((destination/f.name).exists() for f in sources): raise ValueError('目标数据库已存在；请恢复到新目录，确认后再切换配置')
    destination.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for file in sources:
        with sqlite3.connect(file.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(destination/file.name) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('数据库完整性检查失败')
        output=destination/file.name
        manifest.append({'name':file.name,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()})
    (destination/'backup-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['backup','restore'])
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--service-stopped',action='store_true')
    args=parser.parse_args()
    if not args.service_stopped: parser.error('请先停止服务，然后明确提供 --service-stopped')
    print(json.dumps(transfer(args.source,args.destination),indent=2))

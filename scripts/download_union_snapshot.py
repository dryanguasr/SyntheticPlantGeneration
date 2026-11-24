"""Materialize only image URLs in an already downloaded Ultralytics NDJSON.

No credentials are read. Source annotations and split assignments stay intact.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlsplit
from urllib.request import urlopen


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    root = args.source.resolve().parent
    rows = [json.loads(line) for line in args.source.read_text(encoding='utf-8').splitlines() if line.strip()]
    images = [row for row in rows if row['type'] == 'image']
    for index, row in enumerate(images):
        row['source_row'] = index + 2
        name = row['file']
        if Path(name).name != name or ':' in name or row['split'] not in {'train', 'val', 'test'}:
            raise ValueError('Unsafe file or split')
        if urlsplit(row['url']).scheme != 'https' or urlsplit(row['url']).hostname != 'cdn.ul.run':
            raise ValueError('Unexpected download host')

    def download(row):
        path = root / 'images' / row['split'] / (f"{row['source_row']:04d}_" + row['file'])
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            partial = path.with_suffix(path.suffix + '.partial')
            for attempt in range(3):
                try:
                    with urlopen(row['url'], timeout=60) as response, partial.open('wb') as out:
                        for block in iter(lambda: response.read(1024 * 1024), b''):
                            out.write(block)
                    partial.replace(path)
                    break
                except Exception:
                    if attempt == 2:
                        return {'source_row': row['source_row'], 'file': row['file'], 'split': row['split'], 'error': 'download_failed'}
                    time.sleep(2)
        return {'source_row': row['source_row'], 'file': row['file'], 'split': row['split'], 'path': path.relative_to(root).as_posix(),
                'bytes': path.stat().st_size, 'sha256': sha(path)}

    records = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(download, row) for row in images]
        for future in as_completed(futures):
            records.append(future.result())
            if len(records) % 50 == 0:
                print(f'{len(records)}/{len(images)} images processed', flush=True)
    manifest = {'schema_version': 'union-local-snapshot/1.0', 'source_file': args.source.name,
                'source_sha256': sha(args.source), 'source_metadata': rows[0],
                'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                'license_reported_by_platform': 'CC BY 4.0',
                'attribution': 'Uchuva Naranja / Diego Amaya; submitted by Karen and Caroline per user',
                'images': sorted(records, key=lambda row: (row['split'], row['file']))}
    (root / 'download_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    failures = sum('error' in row for row in records)
    print(json.dumps({'images': len(records), 'failures': failures, 'bytes': sum(row.get('bytes', 0) for row in records)}))
    raise SystemExit(bool(failures))


if __name__ == '__main__':
    main()

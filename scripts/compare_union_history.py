"""Read-only exact-byte overlap audit against named local acquisition roots."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('history', nargs='+', type=Path)
    parser.add_argument('--perceptual', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((args.snapshot / 'download_manifest.json').read_text(encoding='utf-8'))
    hashes = defaultdict(list)
    sizes = set()
    for image in manifest['images']:
        if 'error' not in image:
            hashes[image['sha256']].append({'source_row': image['source_row'], 'split': image['split'], 'file': image['file']})
            sizes.add(image['bytes'])
    matches, roots, candidates = [], [], []
    reference = json.loads((args.snapshot / 'audit' / 'images.json').read_text()) if args.perceptual else []
    fingerprints = [(r, int(r['dhash64'], 16)) for r in reference]
    for root in args.history:
        paths = sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'})
        hashed = 0
        for index, path in enumerate(paths):
            if args.perceptual:
                with Image.open(path) as image:
                    tiny = np.asarray(image.convert('L').resize((9, 8), Image.Resampling.LANCZOS))
                value = int.from_bytes(np.packbits(tiny[:, 1:] > tiny[:, :-1]).tobytes(), 'big')
                close = [(r, (value ^ h).bit_count()) for r, h in fingerprints if (value ^ h).bit_count() <= 5]
                if close:
                    candidates.append({'historical_path': str(path), 'candidates': [
                        {'source_row': r['source_row'], 'split': r['split'], 'distance': d} for r, d in close]})
                if (index + 1) % 200 == 0:
                    print(f'Compared {root}: {index+1}/{len(paths)}', flush=True)
            if path.stat().st_size not in sizes:
                continue
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            hashed += 1
            if digest in hashes:
                matches.append({'historical_path': str(path), 'sha256': digest, 'snapshot_records': hashes[digest]})
        roots.append({'root': str(root), 'images_scanned': len(paths), 'images_size_matched_and_hashed': hashed})
    result = {'method': 'SHA-256 byte identity, size prefilter; absence does not exclude transformed/reencoded matches',
              'roots': roots, 'matches': matches,
              'perceptual_candidates_dhash_le_5': candidates,
              'matched_snapshot_rows': len({r['source_row'] for m in matches for r in m['snapshot_records']})}
    out = args.snapshot / 'audit' / 'historical_overlap.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'roots': roots, 'matching_historical_files': len(matches), 'matched_snapshot_rows': result['matched_snapshot_rows'], 'historical_images_with_perceptual_candidates': len(candidates)}))


if __name__ == '__main__':
    main()

"""Exact binary-mask overlap on CUDA using bounded packed-byte batches."""
import numpy as np


class CudaMaskOverlap:
    def __init__(self, batch_size=32):
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA requested but unavailable')
        self.torch = torch
        # Bound the shared process allocator instead of letting Windows spill
        # variable-sized CUDA reservations into host memory.
        torch.cuda.set_per_process_memory_fraction(0.5)
        self.batch_size = batch_size
        self.lookup = torch.tensor([i.bit_count() for i in range(256)],
                                   device='cuda', dtype=torch.uint8)
        self.calls = 0
        self.pairs = 0

    def __call__(self, old_masks, new_masks, pairs):
        if not pairs:
            return {}
        torch = self.torch
        # Pack each new mask once per frame, not once per candidate pair.
        new_packed = [mask.packed if hasattr(mask,'packed') else np.packbits(mask.reshape(-1)) for mask in new_masks]
        def upload(masks):
            packed = np.stack([mask.packed if hasattr(mask,'packed') else np.packbits(mask.reshape(-1)) for mask in masks])
            return torch.from_numpy(packed).to('cuda')
        with torch.inference_mode():
            result = {}
            for start in range(0, len(pairs), self.batch_size):
                chunk = pairs[start:start+self.batch_size]
                # Upload only this bounded batch, never the entire active set.
                a = upload([old_masks[i] for i, _ in chunk])
                b = torch.from_numpy(np.stack([new_packed[j] for _, j in chunk])).to('cuda')
                intersection = self.lookup[(a & b).long()].sum(dim=1)
                union = self.lookup[(a | b).long()].sum(dim=1)
                counts = torch.stack((intersection, union), dim=1).cpu().numpy()
                for pair, (inter, total) in zip(chunk, counts):
                    result[pair] = int(inter)/max(1, int(total))
        self.calls += 1
        self.pairs += len(pairs)
        return result

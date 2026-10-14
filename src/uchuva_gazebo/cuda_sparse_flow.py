"""Batched pyramidal Lucas-Kanade on CUDA; RGB-only, no learned weights.

This is a versioned numerical implementation, not bit-equivalent OpenCV LK.
Forward/backward rejection remains the caller's responsibility.
"""
import numpy as np


class CudaSparseFlow:
    def __init__(self, levels=2, radius=10, iterations=20):
        import torch
        import torch.nn.functional as F
        if not torch.cuda.is_available():raise RuntimeError('CUDA flow unavailable')
        self.torch=torch;self.F=F;self.levels=levels;self.iterations=iterations
        axis=torch.arange(-radius,radius+1,device='cuda',dtype=torch.float32)
        y,x=torch.meshgrid(axis,axis,indexing='ij')
        self.offset=torch.stack((x.flatten(),y.flatten()),dim=-1)
        self.calls=0

    def pyramid(self,gray):
        t=self.torch.from_numpy(np.ascontiguousarray(gray)).to(device='cuda',dtype=self.torch.float32)[None,None]/255
        result=[t]
        for _ in range(self.levels):result.append(self.F.avg_pool2d(result[-1],2))
        return result

    def sample(self,image,points):
        h,w=image.shape[-2:];grid=points[:,None,:]+self.offset[None,:,:]
        grid=grid*self.torch.tensor([2/(w-1),2/(h-1)],device='cuda')-1
        return self.F.grid_sample(image,grid[None],align_corners=True,padding_mode='border')[0,0]

    def solve(self,first,second,points):
        torch=self.torch
        p=torch.as_tensor(points.reshape(-1,2),device='cuda',dtype=torch.float32)
        q=p/(2**self.levels);valid=torch.ones(len(p),device='cuda',dtype=torch.bool)
        for level in range(self.levels,-1,-1):
            if level!=self.levels:q=q*2
            source=first[level];target=second[level];base=p/(2**level)
            gx=self.F.pad((source[:,:,:,2:]-source[:,:,:,:-2])*.5,(1,1,0,0),mode='replicate')
            gy=self.F.pad((source[:,:,2:,:]-source[:,:,:-2,:])*.5,(0,0,1,1),mode='replicate')
            template=self.sample(source,base);ix=self.sample(gx,base);iy=self.sample(gy,base)
            aa=(ix*ix).sum(1);ab=(ix*iy).sum(1);bb=(iy*iy).sum(1)
            det=aa*bb-ab*ab;good=det>1e-8;den=det.clamp_min(1e-8)
            for _ in range(self.iterations):
                residual=template-self.sample(target,q)
                bx=(ix*residual).sum(1);by=(iy*residual).sum(1)
                delta=torch.stack(((bb*bx-ab*by)/den,(aa*by-ab*bx)/den),1)
                q=q+torch.where(good[:,None],delta.clamp(-3,3),torch.zeros_like(delta))
            if level==0:valid &= good
        h,w=first[0].shape[-2:]
        valid &= torch.isfinite(q).all(1)&(q[:,0]>=0)&(q[:,0]<w)&(q[:,1]>=0)&(q[:,1]<h)
        return q,valid

    def __call__(self,previous,current,points):
        if not len(points):return points.copy(),np.zeros(0,bool)
        with self.torch.inference_mode():
            a=self.pyramid(previous);b=self.pyramid(current)
            outputs=[];validity=[]
            # Bound patch tensors even when many trajectories remain active.
            for start in range(0,len(points),256):
                chunk=points[start:start+256]
                forward,ok=self.solve(a,b,chunk)
                back,ok2=self.solve(b,a,forward)
                original=self.torch.as_tensor(chunk.reshape(-1,2),device='cuda')
                valid=ok&ok2&(self.torch.linalg.vector_norm(back-original,dim=1)<1.5)
                outputs.append(forward.cpu().numpy());validity.append(valid.cpu().numpy())
            self.calls+=1
            return np.concatenate(outputs).reshape(-1,1,2),np.concatenate(validity)

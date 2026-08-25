"""Phase-1 acoustic feature extraction for Stage-2 distress verification.

NumPy-only acoustic features plus the project's reproducible MFCC front-end.
"""
from __future__ import annotations
import numpy as np
from ml.mfcc import mfcc as project_mfcc
EPS=1e-10
DEFAULT_SR=16000
FRAME_S=0.032
HOP_S=0.016
ROUGHNESS_LOW_HZ=30.0
ROUGHNESS_HIGH_HZ=150.0
FEATURE_NAMES=("rms_mean","rms_std","rms_max","zcr_mean","zcr_std","spectral_centroid_mean","spectral_centroid_std","spectral_bandwidth_mean","spectral_bandwidth_std","spectral_rolloff_mean","spectral_rolloff_std","spectral_entropy_mean","spectral_entropy_std","spectral_flux_mean","spectral_flux_std","f0_mean","f0_std","f0_range","f0_voiced_fraction","roughness_30_150")+tuple(f"mfcc_{i:02d}_mean" for i in range(13))+tuple(f"mfcc_{i:02d}_std" for i in range(13))
def _mono_float(audio):
 x=np.asarray(audio,dtype=np.float32)
 if x.ndim==2: x=x.mean(axis=0 if x.shape[0]<x.shape[1] else 1)
 return np.nan_to_num(x,nan=0.0,posinf=0.0,neginf=0.0).astype(np.float32)
def _frames(x,sr):
 n=max(16,int(round(FRAME_S*sr))); hop=max(1,int(round(HOP_S*sr)))
 if x.size<n: x=np.pad(x,(0,n-x.size))
 count=1+(x.size-n)//hop
 return np.stack([x[i*hop:i*hop+n] for i in range(count)])
def _spectral(frames,sr):
 n=frames.shape[1]; window=np.hanning(n).astype(np.float32); mag=np.abs(np.fft.rfft(frames*window,axis=1)); power=mag*mag; freqs=np.fft.rfftfreq(n,1.0/sr).astype(np.float32); denom=power.sum(axis=1)+EPS
 centroid=(power*freqs[None,:]).sum(axis=1)/denom; bandwidth=np.sqrt((power*(freqs[None,:]-centroid[:,None])**2).sum(axis=1)/denom)
 csum=np.cumsum(power,axis=1); threshold=0.85*denom; rolloff=freqs[(csum>=threshold[:,None]).argmax(axis=1)]; prob=power/denom[:,None]; entropy=-(prob*np.log2(prob+EPS)).sum(axis=1)/np.log2(power.shape[1]); norm=mag/(mag.sum(axis=1,keepdims=True)+EPS)
 return centroid,bandwidth,rolloff,entropy,norm
def _spectral_flux(norm_spectra):
 if len(norm_spectra)<2:return np.zeros(len(norm_spectra),dtype=np.float32)
 delta=np.diff(norm_spectra,axis=0,prepend=norm_spectra[:1]); return np.sqrt((delta*delta).sum(axis=1)).astype(np.float32)
def _zcr(frames): return np.mean((frames[:,1:]>=0)!=(frames[:,:-1]>=0),axis=1).astype(np.float32)
def _rms(frames): return np.sqrt(np.mean(frames*frames,axis=1)+EPS).astype(np.float32)
def _f0(frames,sr):
 min_lag=max(1,int(sr/1000.0)); max_lag=min(frames.shape[1]-2,int(sr/70.0)); out=np.zeros(len(frames),dtype=np.float32)
 if max_lag<=min_lag:return out
 for i,frame in enumerate(frames):
  y=frame-frame.mean(); energy=float(np.dot(y,y))
  if energy<1e-7:continue
  corr=np.correlate(y,y,mode="full")[len(y)-1:]; corr[:min_lag]=0; lag=int(np.argmax(corr[:max_lag+1])); peak=float(corr[lag])
  if lag>0 and peak/(energy+EPS)>=0.30:out[i]=sr/lag
 return out
def modulation_roughness(audio,sr=DEFAULT_SR):
 x=_mono_float(audio)
 if x.size<max(256,sr//10):return 0.0
 env=np.abs(x); env-=env.mean()
 if np.allclose(env,0.0):return 0.0
 spec=np.abs(np.fft.rfft(env*np.hanning(len(env))))**2; freqs=np.fft.rfftfreq(len(env),1.0/sr); band=(freqs>=ROUGHNESS_LOW_HZ)&(freqs<=min(ROUGHNESS_HIGH_HZ,sr/2.0)); total=float(spec[1:].sum())+EPS
 return float(np.clip(spec[band].sum()/total,0.0,1.0))
def extract_frame_features(audio,sr=DEFAULT_SR):
 x=_mono_float(audio); frames=_frames(x,sr); centroid,bandwidth,rolloff,entropy,norm=_spectral(frames,sr)
 return {"rms":_rms(frames),"zcr":_zcr(frames),"spectral_centroid":centroid.astype(np.float32),"spectral_bandwidth":bandwidth.astype(np.float32),"spectral_rolloff":rolloff.astype(np.float32),"spectral_entropy":entropy.astype(np.float32),"spectral_flux":_spectral_flux(norm),"f0":_f0(frames,sr)}
def extract_features(audio,sr=DEFAULT_SR):
 x=_mono_float(audio); frame=extract_frame_features(x,sr); f0=frame["f0"]; voiced=f0[f0>0]; mf=project_mfcc(x)
 stats=[float(frame["rms"].mean()),float(frame["rms"].std()),float(frame["rms"].max()),float(frame["zcr"].mean()),float(frame["zcr"].std()),float(frame["spectral_centroid"].mean()),float(frame["spectral_centroid"].std()),float(frame["spectral_bandwidth"].mean()),float(frame["spectral_bandwidth"].std()),float(frame["spectral_rolloff"].mean()),float(frame["spectral_rolloff"].std()),float(frame["spectral_entropy"].mean()),float(frame["spectral_entropy"].std()),float(frame["spectral_flux"].mean()),float(frame["spectral_flux"].std()),float(voiced.mean()) if voiced.size else 0.0,float(voiced.std()) if voiced.size else 0.0,float(voiced.max()-voiced.min()) if voiced.size else 0.0,float((f0>0).mean()),modulation_roughness(x,sr)]
 stats.extend(mf.mean(axis=0).astype(float).tolist()); stats.extend(mf.std(axis=0).astype(float).tolist()); out=np.asarray(stats,dtype=np.float32)
 if out.shape!=(len(FEATURE_NAMES),):raise RuntimeError(f"unexpected Phase-1 feature shape: {out.shape}")
 return out
def feature_dict(audio,sr=DEFAULT_SR):return dict(zip(FEATURE_NAMES,extract_features(audio,sr).astype(float)))

import os
import json
import soxr
import torch
import argparse
import numpy as np
import soundfile as sf
from tqdm import tqdm
from module.model import Gvector
from scipy.special import softmax
from python_speech_features import logfbank

def parse_args():
    desc="parse model info"
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument('--vad_file', type=str, required=True)
    parser.add_argument('--model_dir', type=str, default='emo_model.pth')
    parser.add_argument('--data_dir', type=str, required=True, help="data directory to be labelled")
    parser.add_argument('--output_json', type=str, required=True)
    parser.add_argument('--process', type=int, default=6, help="multiprocess number")
    parser.add_argument('--device', type=str, default="cuda:4", help="choose from cpu/cuda:n, where n=0,1,2 ... ,7")
    return parser.parse_args()

# config (please keep the same settings with `conf/logfbank_train-emo.json`)
mdl_kwargs = {
    "channels": 16, 
    "block": "BasicBlock", 
    "num_blocks": [2,2,2,2], 
    "embd_dim": 1024, 
    "drop": 0.5, 
    "n_class": 5
}

fbank_kwargs = {
    "winlen": 0.025, 
    "winstep": 0.01, 
    "nfilt": 256, 
    "nfft": 1024, 
    "lowfreq": 0, 
    "highfreq": None, 
    "preemph": 0.97    
}


class SVExtractor():
    def __init__(self, mdl_kwargs, fbank_kwargs, resume, device):
        self.model = self.load_model(mdl_kwargs, resume, device)
        self.model.eval()
        self.device = device
        self.model = self.model.to(self.device)
        self.fbank_kwargs = fbank_kwargs

    def load_model(self, mdl_kwargs, resume, device):
        model = Gvector(**mdl_kwargs)
        state_dict = torch.load(resume,map_location=torch.device(device))
        if 'model' in state_dict.keys():
            state_dict = state_dict['model']
        model.load_state_dict(state_dict)
        return model

    def extract_fbank(self, y, sr, cmn=True):
        feat = logfbank(y, sr, **self.fbank_kwargs)
        if cmn:
            feat -= feat.mean(axis=0, keepdims=True)
        return feat.astype('float32')

    def __call__(self, y, sr):
        assert sr == 16000, "Support 16k wave only!"
        if len(y) > sr * 30:
            y = y[:int(sr*30)]  # truncate the maximum length of 30s.
        feat = self.extract_fbank(y, sr, cmn=True)
        feat = torch.from_numpy(feat).unsqueeze(0)
        feat = feat.float().to(self.device)
        self.model.eval()
        with torch.no_grad():
            embd = self.model.extractor(feat)
            rslt = self.model.forward(feat)
        embd = embd.squeeze(0).cpu().numpy()
        rslt = rslt.squeeze(0).cpu().numpy()
        return embd, rslt

def labeling(iii, args):
    isFirst = True
    
    pTotal = args.process
    model_dir = args.model_dir
    vad_path = args.vad_file
    output_json = args.output_json
    recording_dir = args.data_dir.rstrip('/') + '/'
    
    sv_extractor = SVExtractor(mdl_kwargs, fbank_kwargs, model_dir, device=args.device)
    with open(vad_path,'r') as f:
        vad_info = [line for line in f.read().split('\n') if line]
        
    with open('index/int2label.json','r') as f:
        identi = json.load(f)
        
    # loading vad results
    voiced_part = {}
    for line in tqdm(vad_info):
        line_info = line.split()
        start_time = float(line_info[3])
        end_time   = float(line_info[3]) + float(line_info[4])
        if not line_info[1] in voiced_part:
            voiced_part[line_info[1]] = []
        voiced_part[line_info[1]].append((start_time, end_time))
    
    recorders = os.listdir(recording_dir)
    all_recordings = []
    vad_result = {}
    for rec in recorders:
        all_recordings += [recording_dir+rec+'/'+r for r in os.listdir(recording_dir+rec) if r.endswith('.wav')]
#     all_recordings = [recording_dir + r for r in os.listdir(recording_dir) if r.endswith(".wav")]
    portion = len(all_recordings) // pTotal
    if iii == 0:
        all_recordings = all_recordings[:portion]
    elif iii == pTotal - 1:
        all_recordings = all_recordings[portion*iii:]
    else:
        all_recordings = all_recordings[portion*iii: portion*(iii+1)]
    
    # label the assigned portion
    for rcd in tqdm(all_recordings, desc="process_%d"%os.getpid()):
        if isFirst:
            with open('kill_label.sh','a') as f:
                f.write('kill -9 %d\n'%os.getpid())
            isFirst = False
            
        if not rcd.split('/')[-1] in vad_result:
            vad_result[rcd.split('/')[-1]] = {}
        try:
            rcd_data, sr = sf.read(rcd)
            if sr != 16000:
                rcd_data = soxr.resample(rcd_data, sr, 16000)
            rcd_voiced = voiced_part[rcd.split('/')[-1]]
            for (start_time, end_time) in rcd_voiced:
                if end_time - start_time <= 5:
                    tmp_clip = rcd_data[int(start_time * sr):int(end_time * sr)]
                    embd, result = sv_extractor(tmp_clip, sr)
                    probs = ["{0:0.4f}".format(i) for i in softmax(result)]
                    vad_result[rcd.split('/')[-1]]["(%.4f, %.4f)"%(start_time, end_time)] = dict(zip(list(identi.values()), probs))
                else:
                    time_shift = 1
                    curr_start = start_time
                    while end_time - curr_start >= 4:
                        curr_window = rcd_data[int(curr_start * sr):int((curr_start+5) * sr)]
                        embd, result = sv_extractor(curr_window, sr)
                        probs = ["{0:0.4f}".format(i) for i in softmax(result)]
                        vad_result[rcd.split('/')[-1]]["(%.4f, %.4f)"%(curr_start, curr_start+5)] = dict(zip(list(identi.values()), probs))
                        curr_start += 1
        except:
            with open('bad_file','a') as f:
                f.write(os.path.abspath(rcd)+'\n')
    with open(output_json,'r') as f:
        cache_dict = json.load(f)
    with open(output_json,'w') as f:
        json.dump({**cache_dict, **vad_result},f)
    
    

if __name__ == "__main__":
    with open('kill_label.sh','w') as f:
        f.write('')
    with open('bad_file', 'w') as f:
        f.write('')
    
    args = parse_args()
    
    with open(args.output_json,'w') as f:
        json.dump({},f)
    
    from multiprocessing import Process
    worker_count = args.process
    worker_pool = []
    for i in range(worker_count):
        p = Process(target=labeling, args=(i, args))
        p.start()
        worker_pool.append(p)
    for p in worker_pool:
        p.join()  # Wait for all of the workers to finish.

    # Allow time to view results before program terminates.
    a = input("Finished")
    os.remove('kill_label.sh')
    with open('bad_file','r') as f:
        bad_content = f.read()
        if not bad_content:
            os.remove('bad_file')

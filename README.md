# cleanTag
**CleanTag** helps you tag emotion labels in wav stream for Chinese audios.
## Environment
```bash
pip install -r requirements.txt
```
## Data
We used [Emotional Speech Dataset (ESD) for Speech Synthesis and Voice Conversion](https://github.com/HLTSingapore/Emotional-Speech-Data) from HLT Singapore.

## Infer labels
```bash
python infer_label.py
```
Adjust the `vad_file` param and code if necessary to adapt to new tasks. Specify the `output_file` for the result of inference. Specify the process number with `process`. 


`infer_label.py` adopted multiprocessing, increased cpu/gpu utilities rate and inference efficiency. See usage details below.
```
usage: infer_label.py [-h] --vad_file VAD_FILE --data_dir DATA_DIR --output_json OUTPUT_JSON [--model_dir MODEL_DIR] [--process PROCESS] [--device DEVICE]

parse model info

optional arguments:
  -h, --help            show this help message and exit
  --vad_file VAD_FILE
  --data_dir DATA_DIR   data directory to be labelled
  --output_json OUTPUT_JSON
  --model_dir MODEL_DIR
  --process PROCESS     multiprocess number
  --device DEVICE       choose from cpu/cuda:n, where n=0,1,2 ... ,7
```
`infer_label.py` automatically generates `kill_label.sh` script while running. Kill multiprocess labeling program simply by
```bash
bash kill_label.sh
```
Find inference failure log in `bad_file`.
`kill_label.sh` will be removed automatically after inference is done. `bad_file` will be automatically removed if empty.

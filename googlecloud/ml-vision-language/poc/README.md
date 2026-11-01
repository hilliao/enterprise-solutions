# Proofs of concept

Stand-alone experiments. The person detector and the `run_detector_*.sh` scripts in the parent folder do not use them.

| Script | What it does | Needs |
|---|---|---|
| `describe_camera_frames_with_ollama.py` | Grabs one frame at a time from an RTSP stream, saves it, asks a vision language model served by Ollama (`minicpm-v`) to describe it, and appends the answers to a log file. Usage is at the top of the file. | `pip install opencv-python ollama`, a running Ollama server |
| `answer_image_question_with_blip.py` | Answers a question about one image, local file or URL, with the Salesforce BLIP visual question answering model. Set `IMAGE_PATH` and `QUESTION`. | `transformers`, `torch`, `Pillow`, `requests` |
| `gpu_stress_test_resnet50.py` | Runs ResNet50 inference in a loop on a CUDA GPU and fills its memory to `--mem` MB, e.g. to check its cooling and memory. | `torch`, `torchvision`, a CUDA GPU |

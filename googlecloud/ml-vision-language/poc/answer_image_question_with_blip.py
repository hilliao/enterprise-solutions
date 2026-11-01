"""Answer a question about an image with the Salesforce BLIP visual question answering model.

Usage: IMAGE_PATH=/home/user/picture-dog-0.png QUESTION="how many dogs are in the picture?" \\
       python poc/answer_image_question_with_blip.py
"""
import requests
from PIL import Image
from transformers import BlipProcessor, BlipForQuestionAnswering
import torch
import os
import sys


def answer_image_question(image_path, question):
    """
    Processes an image and answers a question about it using the BLIP model.

    Args:
        image_path: The path to the image file (local path or URL).
        question: The question to ask about the image.
    """
    processor = BlipProcessor.from_pretrained("Salesforce/blip-vqa-base")
    model = BlipForQuestionAnswering.from_pretrained("Salesforce/blip-vqa-base")

    # Check for CUDA availability
    if torch.cuda.is_available():
        gpu_count = torch.cuda.device_count()
        print(f"CUDA is available, using {gpu_count} GPU(s).")
        for gpu_index in range(gpu_count):
            print(f"  GPU {gpu_index}: {torch.cuda.get_device_name(gpu_index)}")
            print(f"    Memory: {torch.cuda.get_device_properties(gpu_index).total_memory / 1e9:.2f} GB")

        model = model.to("cuda")  # Move the entire model to CUDA directly

    # Check if the input is a URL or a local file path
    if image_path.startswith('http://') or image_path.startswith('https://'):
        raw_image = Image.open(requests.get(image_path, stream=True).raw).convert('RGB')
    elif os.path.exists(image_path):
        raw_image = Image.open(image_path).convert('RGB')
    else:
        raise ValueError("Invalid image path. Please provide a valid URL or local file path.")

    model_inputs = processor(raw_image, question, return_tensors="pt")

    if torch.cuda.is_available():
        model_inputs = model_inputs.to("cuda")  # only move inputs to cuda if cuda is available

    answer_token_ids = model.generate(**model_inputs)
    return processor.decode(answer_token_ids[0], skip_special_tokens=True)


if __name__ == "__main__":
    # example: /home/user/picture-dog-0.png
    image_path = os.environ.get("IMAGE_PATH")
    # example: "how many dogs are in the picture?"
    question = os.environ.get("QUESTION")

    if not image_path:
        print("Error: IMAGE_PATH environment variable not set.", file=sys.stderr)
        sys.exit(1)

    if not question:
        print("Error: QUESTION environment variable not set.", file=sys.stderr)
        sys.exit(1)

    answer = answer_image_question(image_path, question)
    print(answer)

import requests
from PIL import Image
from transformers import BlipProcessor, BlipForQuestionAnswering
import torch
import os
import sys


def process_image_and_question(image_path, question):
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
        num_gpus = torch.cuda.device_count()
        print(f"CUDA is available, using {num_gpus} GPU(s).")
        for i in range(num_gpus):
            print(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
            print(f"    Memory: {torch.cuda.get_device_properties(i).total_memory / 1e9:.2f} GB")

        model = model.to("cuda")  # Move the entire model to CUDA directly

    # Check if the input is a URL or a local file path
    if image_path.startswith('http://') or image_path.startswith('https://'):
        raw_image = Image.open(requests.get(image_path, stream=True).raw).convert('RGB')
    elif os.path.exists(image_path):
        raw_image = Image.open(image_path).convert('RGB')
    else:
        raise ValueError("Invalid image path. Please provide a valid URL or local file path.")

    inputs = processor(raw_image, question, return_tensors="pt")

    if torch.cuda.is_available():
        inputs = inputs.to("cuda")  # only move inputs to cuda if cuda is available

    generated_ids = model.generate(**inputs)
    return processor.decode(generated_ids[0], skip_special_tokens=True)


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

    answer = process_image_and_question(image_path, question)
    print(answer)
